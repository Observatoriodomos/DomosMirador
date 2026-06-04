# n8n payment & reception handoff workflows

Three workflows triggered at/after payment confirmation. Together with PR #7's existing `n8n-capi-setup.md` and `lia-whatsapp-capi-setup.md`, these close the funnel from "guest accepts quote" through "reception handoff complete."

## Pre-work — one-time Kommo setup

You need these structures in Kommo before any of the workflows below work. Skip whichever already exist.

### Pipeline statuses

Add to the main Lia pipeline (or a new "Estancia" pipeline) **in this order**:

1. `Cotizado` — Lia sent quote
2. `Aceptado` — guest accepted, Octorate booking created
3. `Pagado` — payment confirmed (Stripe OR SINPE)
4. `Pre-llegada` — within 7 days of check-in, pre-arrival sequence active
5. `Recepción` — handoff sent, guest is reception's responsibility
6. `Activo` — checked in
7. `Concluido` — checked out
8. `Post-estancia` — review/return-guest sequence active

### Lead custom fields

| Field name | Type | Code | Purpose |
|---|---|---|---|
| `payment_method` | List (`stripe`, `sinpe`, `bank`) | `payment_method` | Distinguishes triggers |
| `payment_confirmed_at` | DateTime | `payment_confirmed_at` | Idempotency check (only fire Purchase once) |
| `octorate_booking_id` | Text | `octorate_booking_id` | CAPI dedup key |
| `room_type_id` | Text | `room_type_id` | CAPI content_ids |
| `nights` | Numeric | `nights` | CAPI num_items |
| `total_amount` | Numeric | `total_amount` | CAPI value |
| `check_in_date` | Date | `check_in_date` | Triggers pre-arrival + reception sequences |
| `reception_handoff_sent_at` | DateTime | `reception_handoff_sent_at` | Idempotency for handoff |

Plus the attribution fields from `lia-whatsapp-capi-setup.md` (`ctwa_clid`, `ad_source_id`, `ad_source_url`).

---

## Workflow 1 — Payment-confirmed → CAPI Purchase

**Goal:** fire one CAPI Purchase per booking, regardless of payment method. Dedup via `event_id = octorate_booking_id` so even if both triggers fire, Meta counts it once.

### Two trigger paths, one shared destination

```
  Stripe webhook ("payment_intent.succeeded")
        │
        ├──► Match metadata.booking_id → Kommo lead
        │    Set payment_confirmed_at, payment_method='stripe'
        │
        ▼
  ┌─────────────────────────────────────┐
  │ SHARED: Build CAPI Purchase payload │  ← also reached from below
  │ POST to graph.facebook.com          │
  │ Move lead to "Pagado" status        │
  └─────────────────────────────────────┘
        ▲
        │
  Kommo lead status changes to "Pagado" (manual mark after SINPE confirmation)
  AND payment_confirmed_at is NULL
```

### Trigger A — Stripe webhook

n8n **Webhook** node:
- HTTP Method: `POST`
- Path: `/stripe/payment-succeeded`
- Authentication: **HMAC** with your Stripe webhook signing secret (set in env, **not in workflow**)
- Configure Stripe to POST `payment_intent.succeeded` events to this URL

Then a **Code** node — extract Kommo lead lookup data:

```javascript
const event = $input.first().json;
const intent = event.data?.object;

// You MUST pass the Octorate booking ID into Stripe's metadata when creating
// the payment intent. Add metadata: { octorate_booking_id: "..." } in whichever
// workflow creates the Stripe payment link.
const bookingId = intent?.metadata?.octorate_booking_id;
const kommoLeadId = intent?.metadata?.kommo_lead_id;

if (!bookingId || !kommoLeadId) {
  throw new Error('Stripe webhook missing octorate_booking_id or kommo_lead_id in metadata');
}

return {
  json: {
    kommo_lead_id: kommoLeadId,
    octorate_booking_id: bookingId,
    amount_paid: intent.amount_received / 100,   // cents → dollars
    currency: intent.currency.toUpperCase(),
    payment_method: 'stripe',
  },
};
```

Connect this into the **shared CAPI + Kommo update** chain below.

### Trigger B — Kommo lead moved to "Pagado"

n8n **Kommo Trigger** node (or webhook from Kommo automation):
- Event: `Lead status changed`
- Status: `Pagado`

Then a **Kommo Get Lead** node to fetch full lead data → **IF** node:

```
{{ $json.cf.payment_confirmed_at }} is empty
```

Only continue if `payment_confirmed_at` is empty (idempotency — prevents re-firing if someone bumps the status twice).

Then a **Set** node:

```
kommo_lead_id        = {{ $json.id }}
octorate_booking_id  = {{ $json.cf.octorate_booking_id }}
amount_paid          = {{ $json.cf.total_amount }}
currency             = USD
payment_method       = sinpe
```

Connect into the shared chain.

### Shared — CAPI Purchase + mark paid

**Code node — build the payload** (reuses the pattern from `n8n-capi-setup.md`):

```javascript
const crypto = require('crypto');
function sha256Lower(v) { return crypto.createHash('sha256').update(String(v).trim().toLowerCase()).digest('hex'); }

const item = $input.first().json;

// Fetch full lead from previous Kommo node (or pass through)
// For brevity, assume previous node populated these:
const lead = item.lead ?? item;

const user_data = {};
if (lead.email)       user_data.em = [sha256Lower(lead.email)];
if (lead.phone)       user_data.ph = [sha256Lower(String(lead.phone).replace(/\D/g, ''))];
if (lead.cf?.ctwa_clid) user_data.ctwa_clid = lead.cf.ctwa_clid;

return {
  json: {
    data: [{
      event_name: 'Purchase',
      event_time: Math.floor(Date.now() / 1000),
      event_id: String(item.octorate_booking_id),   // dedup across all triggers
      action_source: 'chat',                         // Lia closed the booking
      user_data,
      custom_data: {
        currency: item.currency,
        value: parseFloat(item.amount_paid),
        content_ids: [String(lead.cf?.room_type_id ?? 'unknown')],
        content_type: 'product',
        contents: [{ id: String(lead.cf?.room_type_id ?? 'unknown'), quantity: parseInt(lead.cf?.nights ?? 1, 10) }],
        num_items: parseInt(lead.cf?.nights ?? 1, 10),
        order_id: String(item.octorate_booking_id),
        messaging_channel: 'whatsapp',
        payment_method: item.payment_method,
      },
    }],
    _kommo_lead_id: item.kommo_lead_id,           // pass through for next nodes
    _payment_method: item.payment_method,
  },
};
```

**HTTP Request node — POST to Meta:**
- URL: `https://graph.facebook.com/v21.0/458979157007770/events`
- Query: `access_token={{ $env.META_ACCESS_TOKEN }}`
- Body: `{{ JSON.stringify({ data: $json.data }) }}`

**Kommo Update Lead node — mark paid + advance status:**
- Lead ID: `{{ $json._kommo_lead_id }}`
- Custom field `payment_confirmed_at`: `{{ $now.toISO() }}`
- Custom field `payment_method`: `{{ $json._payment_method }}`
- Status: `Pagado` (Trigger A path) or no change (Trigger B is already there)

Wire to **Workflow 2** (reception handoff) at the end of this chain.

---

## Workflow 2 — Reception handoff (two-number setup)

**Architecture assumed:** Lia uses WhatsApp number A (her own, connected to Kommo). Reception uses WhatsApp number B (also connected to Kommo). Both numbers post into the same Kommo lead, so reception can scroll up and see Lia's full conversation.

**Trigger:** end of Workflow 1 → reception handoff fires once payment is confirmed AND `reception_handoff_sent_at` is empty.

**What it does:**
1. Posts a structured handoff note on the Kommo lead (so reception has a one-glance summary).
2. Moves the lead to `Recepción` status (which also triggers Lia's "stop replying" filter — see below).
3. Reassigns the responsible user from Lia-bot to a designated reception Kommo user.
4. **From Lia's number (A):** sends the guest a bridging message — "Pago confirmado, recepción te contactará en breve desde [+506-XXXX-XXXX]" — so the guest expects the second number.
5. Notifies reception (in Kommo + optionally on their phone) that a new lead is waiting. Reception then manually sends the first message from their number — keeps WhatsApp template approval simple.

### Required env vars

```
RECEPTION_KOMMO_USER_ID    # numeric ID of the reception human in Kommo
RECEPTION_PHONE_DISPLAY    # the WhatsApp number to TELL the guest about, e.g. "+506 8888 7777"
                           # this is reception's number formatted for human reading
LIA_WA_PHONE_NUMBER_ID     # Meta phone_number_id for Lia's WhatsApp (for sending the bridging message)
```

### Node 1 — IF (idempotency)

```
{{ $json.lead.cf.reception_handoff_sent_at }} is empty
```

### Node 2 — Code (build all the handoff payloads at once)

```javascript
const lead = $input.first().json.lead;

const handoff = {
  booking_id: lead.cf.octorate_booking_id,
  guest_name: lead.name,
  guest_first_name: (lead.name || '').split(' ')[0],
  phone: lead.phone,
  email: lead.email ?? '—',
  room_type: lead.cf.room_type_id,
  check_in: lead.cf.check_in_date,
  nights: lead.cf.nights,
  total_paid: `${lead.cf.total_amount} USD (${lead.cf.payment_method})`,
  payment_method: lead.cf.payment_method,
  lead_source: lead.cf.ad_source_id ? `Meta ad ${lead.cf.ad_source_id}` : 'orgánico',
  special_requests: lead.cf.special_requests ?? '—',
  kommo_lead_url: `https://${process.env.KOMMO_SUBDOMAIN}.kommo.com/leads/detail/${lead.id}`,
  octorate_url: `https://app.octorate.com/booking/${lead.cf.octorate_booking_id}`,
};

// (1) Structured note for the Kommo lead — what reception scans
const handoffNote = `🏡 *Nueva llegada confirmada*

*Huésped:* ${handoff.guest_name}
*Tel:* ${handoff.phone}
*Email:* ${handoff.email}

*Reserva:* ${handoff.booking_id} → ${handoff.octorate_url}
*Domo:* ${handoff.room_type}
*Check-in:* ${handoff.check_in}
*Noches:* ${handoff.nights}
*Total pagado:* ${handoff.total_paid}

*Origen:* ${handoff.lead_source}
*Pedidos especiales:* ${handoff.special_requests}`;

// (2) Bridging message FROM Lia TO guest — tells them about the second number
const bridgingMessage = `¡${handoff.guest_first_name}, pago confirmado! 🎉

Tu reserva está lista. Nuestro equipo de recepción te contactará pronto desde *${process.env.RECEPTION_PHONE_DISPLAY}* para coordinar tu llegada y enviarte indicaciones.

Por favor agrega ese número a tus contactos como *Recepción Domos Mirador* para no perder el mensaje.

¡Nos vemos en ${handoff.check_in}!`;

return {
  json: {
    handoff,
    handoffNote,
    bridgingMessage,
    kommo_lead_id: lead.id,
    guest_phone_e164: lead.phone,   // assumed already in E.164 like +50688887777
  },
};
```

### Node 3 — Kommo Add Note (structured summary for reception)

- Lead ID: `{{ $json.kommo_lead_id }}`
- Note text: `{{ $json.handoffNote }}`
- Note type: `service_message` (pinned, more visible than `common`)

### Node 4 — Kommo Update Lead (status + responsible user + timestamp)

- Lead ID: `{{ $json.kommo_lead_id }}`
- Status: `Recepción`
- Responsible user: `{{ $env.RECEPTION_KOMMO_USER_ID }}`
- Custom field `reception_handoff_sent_at`: `{{ $now.toISO() }}`

This single update does the **status change** + the **reassignment** in one API call.

### Node 5 — Send bridging message from Lia's number

**HTTP Request to WhatsApp Cloud API** (or your provider's equivalent):

- Method: POST
- URL: `https://graph.facebook.com/v21.0/{{ $env.LIA_WA_PHONE_NUMBER_ID }}/messages`
- Auth: Bearer `{{ $env.META_ACCESS_TOKEN }}` in header (NOT in query — this is WhatsApp API, different auth pattern from CAPI)
- Body:

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "{{ $json.guest_phone_e164 }}",
  "type": "text",
  "text": { "body": "{{ $json.bridgingMessage }}" }
}
```

Note: since the guest just paid, you're well within the 24-hour customer-service window, so a free-form text message works — no pre-approved template needed.

### Node 6 — (Optional) Notify reception on their phone

If you want reception to get a WhatsApp ping on number B when a new handoff drops, add a second HTTP Request similar to Node 5 but:
- URL uses `{{ $env.RECEPTION_WA_PHONE_NUMBER_ID }}` (different phone_number_id)
- `to` is reception's own number (set as env var)
- `body` is a compact summary: ``Nueva llegada: ${handoff.guest_name} – ${handoff.check_in} – ${handoff.kommo_lead_url}``

This needs reception's number to be a WhatsApp Business API number too. **Skip this if reception just monitors Kommo notifications on their phone** — the Kommo mobile app already pushes them when a lead is assigned.

### What the guest sees

```
[from Lia's number]
  ¡Juan, pago confirmado! 🎉
  Tu reserva está lista. Nuestro equipo de recepción te contactará pronto
  desde +506 8888 7777 para coordinar tu llegada...

  [10 minutes later — reception manually sends from her number]

[from Reception's number]
  Hola Juan, soy Carmen de Domos Mirador. ¡Bienvenido! Tu domo está listo
  para el viernes a las 3pm. ¿A qué hora estimas llegar?
```

The guest's phone now has **two threads**, but the bridging message + reception's manual intro make the transition natural.

---

## Stop Lia from replying after handoff

Lia must NOT keep responding once reception has taken over. Add this guard at the start of every Lia-reply workflow (the ones that handle inbound WhatsApp messages):

### Belt-and-suspenders IF node

Place this **immediately after** the WhatsApp inbound trigger, **before** any Lia LLM call:

```
Condition: continue ONLY if BOTH are true:
  AND  {{ $json.lead.status }} not in ['Pagado', 'Recepción', 'Pre-llegada', 'Activo', 'Concluido', 'Post-estancia']
  AND  {{ $json.lead.responsible_user_id }} == {{ $env.LIA_KOMMO_USER_ID }}
```

If either check fails → skip Lia's LLM call entirely. Optionally append the inbound message as a Kommo note so reception still sees it on the lead, and optionally notify the responsible user.

### Lia's "I'm handing off" final message (optional but recommended)

The *last* message Lia sends before status flips to `Recepción` is the bridging one above. That gives a clean conversational exit. After that, even if the guest sends "gracias" back to Lia's number, Lia's IF check above means she goes silent — Kommo still records the message on the lead so reception can choose to reply if it's important.

---



**Option A (recommended) — Kommo's WhatsApp API:**

If your Kommo WhatsApp integration exposes a send-message endpoint, use it. Send `whatsappBody` to reception's WhatsApp contact (you'll need their Kommo contact ID — store it once as an n8n env var `RECEPTION_KOMMO_CONTACT_ID`).

**Option B — direct WhatsApp Business API:**

If you have a separate WhatsApp Business API credential for sending to reception:
- URL: `https://graph.facebook.com/v21.0/<YOUR_WA_PHONE_NUMBER_ID>/messages`
- Body:
  ```json
  {
    "messaging_product": "whatsapp",
    "to": "<RECEPTION_PHONE_E164>",
    "type": "text",
    "text": { "body": "{{ $json.whatsappBody }}" }
  }
  ```

Either way, store reception's number / contact ID as an env var so the workflow stays generic.

---

## Workflow 3 — InitiateCheckout when Lia sends quote (fixed rate sheet)

This fires the missing mid-funnel event so Meta sees the full Lead → InitiateCheckout → Purchase progression.

### Trigger

In Lia's existing quote-generation workflow, immediately after she sends the price to the guest.

### Rate sheet — n8n Code node (single source of truth)

```javascript
// Update prices here. Source of truth for both Lia's quote logic AND CAPI value.
// Keep this in n8n only — don't duplicate in Kommo automations.
const RATE_SHEET_USD = {
  'domo-premium': 189,
  'domo-standard': 149,
  'apto-1br':     99,
  'apto-2br':     139,
  // Add seasonal multipliers / weekend uplift here if/when needed.
};

const lead = $input.first().json;
const roomTypeId = lead.cf.room_type_id;
const nights = parseInt(lead.cf.nights ?? 1, 10);
const nightly = RATE_SHEET_USD[roomTypeId];

if (!nightly) {
  throw new Error(`No rate for room_type_id=${roomTypeId}`);
}

const total = nightly * nights;

// Update the Kommo lead with the total so it's available later for Purchase.
// (Use the next Kommo Update Lead node — values pass through.)
return {
  json: {
    kommo_lead_id: lead.id,
    octorate_booking_id: lead.cf.octorate_booking_id ?? null,  // may not exist yet
    total_amount: total,
    room_type_id: roomTypeId,
    nights,
    // CAPI payload below
    capi_payload: {
      data: [{
        event_name: 'InitiateCheckout',
        event_time: Math.floor(Date.now() / 1000),
        event_id: `quote_${lead.id}_${Date.now()}`,   // not yet a booking ID
        action_source: 'chat',
        user_data: {
          // Same hashing helper as Workflow 1 — copy the function in.
        },
        custom_data: {
          currency: 'USD',
          value: total,
          content_ids: [String(roomTypeId)],
          content_type: 'product',
          contents: [{ id: String(roomTypeId), quantity: nights }],
          num_items: nights,
          messaging_channel: 'whatsapp',
        },
      }],
    },
  },
};
```

### Then

- **Kommo Update Lead** — write `total_amount`, `room_type_id`, `nights` to the lead.
- **HTTP Request** — POST `capi_payload` to the same Meta endpoint as Workflow 1.

---

## Test plan

After deploying:

1. **Trigger A (Stripe):** create a test payment intent with `metadata.octorate_booking_id` + `metadata.kommo_lead_id`, mark it succeeded in Stripe test mode. Verify: CAPI Purchase fires once, Kommo lead moves to `Pagado`, then to `Recepción`, reception receives WhatsApp.
2. **Trigger B (SINPE):** manually move a lead to `Pagado` in Kommo. Same chain runs. Verify: identical outcome.
3. **Dedup check:** fire both triggers for the same `octorate_booking_id` in sequence. Meta should show one Purchase, not two (dedup on `event_id`).
4. **Workflow 3:** send a test quote from Lia. Verify InitiateCheckout appears in Meta Events Manager → Test Events with `messaging_channel: whatsapp`.

## Idempotency safety net

If a Stripe webhook retries (network blip) or someone bumps a Kommo status twice, you don't want a second Purchase. The `payment_confirmed_at` check at the start of both triggers prevents this. Same pattern with `reception_handoff_sent_at` for Workflow 2.

If you ever need to **re-fire** intentionally (e.g., a previous fire failed), clear the relevant timestamp custom field in Kommo and bump the status. The workflow will re-process.
