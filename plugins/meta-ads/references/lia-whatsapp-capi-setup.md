# Lia WhatsApp booking → CAPI setup

Lia (the WhatsApp agent in the Kommo/n8n stack) can now close bookings entirely inside WhatsApp without redirecting the guest to the Octorate engine page. These bookings bypass both:

- The browser Pixel (no page is loaded)
- Octorate's native CAPI (the booking is created via Octorate's API from n8n, not from the engine page)

So unless we fire CAPI from Lia's workflow, **the main pixel never sees these conversions** — and they're often the highest-intent ones.

## Which pixel?

Fire to the **main pixel** (`458979157007770` Domos Mirador Pixel Principal). Single source of truth for ad optimization. Keep the two WhatsApp-labelled pixels (`1727298344968140`, `4323706314552040`) only if you want a separate audience source — but in that case, only ever install one of them, not both.

## What's different vs. the engine-page CAPI

| Field | Engine page (n8n-capi-setup.md) | Lia WhatsApp |
|---|---|---|
| `action_source` | `"website"` | `"chat"` |
| `event_source_url` | the Octorate confirmation URL | omit, OR set to `"https://wa.me/<your_business_number>"` |
| `messaging_channel` | not set | `"whatsapp"` (lives inside `custom_data`) |
| `user_data.ctwa_clid` | not set | **set if the lead originated from a Click-to-WhatsApp ad** — see "Attribution" below |
| `user_data.em` / `ph` | from booking guest fields | from the Kommo lead — Lia already has the phone, often has email |
| `user_data.fbc` / `fbp` | from cookies passed through | **not available** — there's no browser |

## Two nodes to add to Lia's workflow

Append these after Lia confirms the booking in Kommo + Octorate (i.e., once you have a real Octorate booking ID). Same shape as `n8n-capi-setup.md`, just different field values.

### Node 1 — Code (JavaScript)

```javascript
const crypto = require('crypto');

function sha256Lower(value) {
  return crypto.createHash('sha256')
    .update(String(value).trim().toLowerCase())
    .digest('hex');
}

const lead = $input.first().json;

// Adjust paths to match Kommo lead + Octorate booking shape in your flow.
const bookingId    = lead.octorate_booking_id ?? lead.cf?.octorate_booking_id;
const totalAmount  = lead.price ?? lead.cf?.booking_total;
const currency     = lead.currency ?? 'USD';
const roomTypeId   = lead.cf?.room_type_id ?? 'unknown';
const nights       = lead.cf?.nights ?? 1;
const guestPhone   = lead.phone ?? lead.contact?.phone;
const guestEmail   = lead.email ?? lead.contact?.email;
const ctwaClid     = lead.cf?.ctwa_clid;   // Click-to-WhatsApp click ID, if any

const user_data = {};
if (guestEmail) user_data.em = [sha256Lower(guestEmail)];
if (guestPhone) {
  const digits = String(guestPhone).replace(/\D/g, '');
  if (digits) user_data.ph = [sha256Lower(digits)];
}
if (ctwaClid) user_data.ctwa_clid = ctwaClid;  // do NOT hash

return {
  json: {
    data: [
      {
        event_name: 'Purchase',
        event_time: Math.floor(Date.now() / 1000),
        event_id: String(bookingId),                  // same dedup key
        action_source: 'chat',
        user_data,
        custom_data: {
          currency,
          value: parseFloat(totalAmount),
          content_ids: [String(roomTypeId)],
          content_type: 'product',
          contents: [{ id: String(roomTypeId), quantity: parseInt(nights, 10) }],
          num_items: parseInt(nights, 10),
          order_id: String(bookingId),
          messaging_channel: 'whatsapp',
        },
      },
    ],
  },
};
```

### Node 2 — HTTP Request

Identical to the engine-page setup:

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://graph.facebook.com/v21.0/458979157007770/events` |
| Query Params | `access_token` = `{{ $env.META_ACCESS_TOKEN }}` |
| JSON Body | `{{ JSON.stringify($json) }}` |

## Lead-stage events (before the booking)

If you want Meta to optimize ads toward "people Lia eventually converts" — not just confirmed bookings — fire intermediate events too. Map them to standard names:

| Lia/Kommo stage | Fire CAPI event | `action_source` |
|---|---|---|
| New WhatsApp conversation starts | `Lead` | `chat` |
| Lia sends pricing + dates | `InitiateCheckout` | `chat` |
| Guest accepts quote | `AddToCart` | `chat` |
| Octorate booking created | `Purchase` | `chat` |

Use the Kommo lead ID as `event_id` for everything below `Purchase`. Use the Octorate booking ID for `Purchase`. This gives Meta a full funnel signal even when nothing ever touches a browser.

## Attribution — Click-to-WhatsApp ads

If you run **Click-to-WhatsApp** campaigns in Meta Ads, the click ID `ctwa_clid` comes through in the WhatsApp message metadata (the first inbound message from a CTWA lead). Capture it in Kommo as a custom field on the lead, then pass it as `user_data.ctwa_clid` (unhashed) on every CAPI event for that lead.

Without `ctwa_clid`, Meta can't attribute the booking back to the specific ad that drove the click. **This is the single biggest lift for CTWA campaign optimization** — bigger than EMQ.

### Where to grab `ctwa_clid` in Lia's flow

The first inbound message webhook from WhatsApp (via Meta Business API or your provider) has a `referral` object on conversation-start. Within it:

```json
{
  "referral": {
    "source_type": "ad",
    "source_id": "12345",
    "source_url": "https://fb.me/...",
    "ctwa_clid": "AbCdEf..."
  }
}
```

Save `ctwa_clid` and `source_id` on the Kommo lead the moment the conversation opens.

### Kommo custom fields to add (one-time setup)

In Kommo → Leads → Settings → Fields, add to the lead entity:

| Field name | Type | Code (for API access) |
|---|---|---|
| `ctwa_clid` | Text | `ctwa_clid` |
| `ad_source_id` | Text | `ad_source_id` |
| `ad_source_url` | URL | `ad_source_url` |

These hold per-lead attribution data. They're never edited by hand — only written by the intake node below.

### n8n intake node (in Lia's WhatsApp-inbound workflow)

Insert at the very first step **after** the WhatsApp webhook trigger, **before** any Lia-message-generation logic:

**Node: Set (rename to "Capture CTWA attribution")**

| Operation | Field | Value |
|---|---|---|
| Set | `ctwa_clid` | `={{ $json.referral?.ctwa_clid ?? '' }}` |
| Set | `ad_source_id` | `={{ $json.referral?.source_id ?? '' }}` |
| Set | `ad_source_url` | `={{ $json.referral?.source_url ?? '' }}` |

Then add an **IF** node: only update Kommo if `ctwa_clid` is non-empty (no point clobbering custom fields for organic chats). On the true branch, call your existing "update Kommo lead custom fields" node with the three values above mapped to the field codes.

In Lia's confirmation/booking node downstream, read the lead's stored `ctwa_clid` and pass it into the CAPI payload — it's already wired in the Code node above (`lead.cf?.ctwa_clid`).

## Verify

1. Have someone (or yourself) DM the WhatsApp number → go through Lia's flow → complete a booking.
2. Within ~1 minute, check https://business.facebook.com/events_manager2/list/dataset/458979157007770/test_events
3. You should see a Purchase event with `action_source: chat` and `custom_data.messaging_channel: whatsapp`.
4. If it was a CTWA-sourced lead, the event should be attributable to the originating ad in Ads Manager within 24h.
