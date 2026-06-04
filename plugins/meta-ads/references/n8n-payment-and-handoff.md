# n8n payment & reception handoff workflows

Three workflows triggered at/after payment confirmation. Together with PR #7's existing `n8n-capi-setup.md` and `lia-whatsapp-capi-setup.md`, these close the funnel from "guest accepts quote" through "reception handoff complete."

## Pre-work — one-time Kommo setup

You need these structures in Kommo before any of the workflows below work. Skip whichever already exist.

### Pipeline statuses

Add to the main Lia pipeline (or a new "Estancia" pipeline) **in this order**:

1. `Cotizado` — Lia sent quote
2. `Aceptado` — guest accepted, Octorate booking created
3. `Pago en revisión` — SINPE screenshot received, awaiting human bank check
4. `Pagado` — payment confirmed (Stripe webhook OR human marked SINPE as verified)
5. `Pre-llegada` — within 7 days of check-in, pre-arrival sequence active
6. `Recepción` — handoff sent, guest is reception's responsibility
7. `Activo` — checked in
8. `Concluido` — checked out
9. `Post-estancia` — review/return-guest sequence active

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
| `sinpe_screenshot_url` | URL | `sinpe_screenshot_url` | Link to the WhatsApp media file |
| `sinpe_extracted_amount` | Numeric | `sinpe_extracted_amount` | LLM-read amount from the image |
| `sinpe_extracted_reference` | Text | `sinpe_extracted_reference` | LLM-read SINPE reference code |
| `sinpe_extracted_sender` | Text | `sinpe_extracted_sender` | LLM-read sender name |
| `sinpe_amount_matches` | Checkbox | `sinpe_amount_matches` | True if extracted amount == total_amount |

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

#### SINPE screenshot pre-verification (before reaching `Pagado`)

For SINPE payments the guest sends a screenshot of their bank transfer via WhatsApp. Lia must extract data from the image, pre-validate it, and move the lead to `Pago en revisión` for human bank verification. Only after a human confirms the transfer in the bank does the lead advance to `Pagado` (which fires Trigger B above).

**Why human-in-the-loop:** SINPE screenshots are easily photoshopped — a common scam in CR. The vision LLM pre-screen catches typos and amount mismatches automatically; the human catches forgeries.

##### SINPE handler workflow — append to Lia's WhatsApp-inbound flow

Trigger condition: inbound WhatsApp message has an image attachment AND lead status is `Aceptado` (i.e. quote accepted, awaiting payment).

###### Node S1 — Download the image

If you're using WhatsApp Cloud API directly:

- **HTTP Request** GET `https://graph.facebook.com/v21.0/<media_id>` with `Authorization: Bearer {{ $env.META_ACCESS_TOKEN }}` → returns a temporary `url`.
- **HTTP Request** GET that `url` with the same header → binary image data.

If you're using Kommo's WhatsApp integration, the attachment URL comes through directly in the inbound message JSON.

###### Node S2 — Vision LLM extraction (Claude or GPT-4V)

**HTTP Request to Anthropic (Claude vision)**:

- Method: POST
- URL: `https://api.anthropic.com/v1/messages`
- Headers:
  - `x-api-key: {{ $env.ANTHROPIC_API_KEY }}`
  - `anthropic-version: 2023-06-01`
  - `content-type: application/json`
- Body:

```json
{
  "model": "claude-haiku-4-5-20251001",
  "max_tokens": 400,
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image",
          "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": "{{ $binary.data.toString('base64') }}"
          }
        },
        {
          "type": "text",
          "text": "This is a screenshot of a SINPE Móvil transaction from Costa Rica. Extract these fields and respond with ONLY valid JSON (no prose, no markdown fence):\n\n{\n  \"is_sinpe_screenshot\": boolean,\n  \"amount_crc\": number or null,\n  \"amount_usd\": number or null,\n  \"reference_code\": string or null,\n  \"sender_name\": string or null,\n  \"recipient_phone\": string or null,\n  \"transaction_datetime\": ISO8601 string or null,\n  \"bank_name\": string or null,\n  \"red_flags\": array of strings (anything suspicious: edited text, mismatched fonts, inconsistent shadows, blur over fields, etc.)\n}\n\nIf this is NOT a SINPE screenshot (e.g. random photo), set is_sinpe_screenshot=false and leave the rest null."
        }
      ]
    }
  ]
}
```

Haiku is cheap enough that running it on every inbound image is fine (~$0.001 per screenshot). Use Sonnet only if you find Haiku misreads frequently.

###### Node S3 — Parse + validate

**Code node:**

```javascript
const lead = $('Kommo Get Lead').first().json;     // adjust to your node name
const raw = $input.first().json.content?.[0]?.text ?? '{}';

let extracted;
try { extracted = JSON.parse(raw); }
catch (e) {
  return { json: { action: 'ask_resend', reason: 'parse_failed' } };
}

if (!extracted.is_sinpe_screenshot) {
  return { json: { action: 'ignore', reason: 'not_a_sinpe_screenshot' } };
}

// Convert CRC to USD if only CRC was extracted (rough — use a real rate source for production).
const CRC_PER_USD = 525;
const amountUsd = extracted.amount_usd
  ?? (extracted.amount_crc ? extracted.amount_crc / CRC_PER_USD : null);

const expectedUsd = parseFloat(lead.cf.total_amount);
const tolerance = 0.5;                              // accept ±$0.50 rounding slop
const matches = amountUsd != null
  && Math.abs(amountUsd - expectedUsd) <= tolerance;

const hasRedFlags = (extracted.red_flags ?? []).length > 0;

return {
  json: {
    action: matches && !hasRedFlags ? 'advance_to_review' : 'flag_for_human',
    kommo_lead_id: lead.id,
    extracted,
    amount_usd_normalized: amountUsd,
    expected_usd: expectedUsd,
    matches,
    has_red_flags: hasRedFlags,
    red_flags: extracted.red_flags ?? [],
  },
};
```

###### Node S4 — Kommo Update Lead + post note

**Kommo Update Lead**:
- Lead ID: `{{ $json.kommo_lead_id }}`
- Status: `Pago en revisión` (always — even when extraction looks good, the human still does the bank check)
- Custom fields:
  - `sinpe_extracted_amount`: `{{ $json.amount_usd_normalized }}`
  - `sinpe_extracted_reference`: `{{ $json.extracted.reference_code }}`
  - `sinpe_extracted_sender`: `{{ $json.extracted.sender_name }}`
  - `sinpe_amount_matches`: `{{ $json.matches }}`
  - `payment_method`: `sinpe`

**Kommo Add Note** — what the human reviewer scans:

```
💸 *SINPE recibido — verificar en banco*

*Esperado:* ${expected_usd} USD
*Extraído del screenshot:* ${amount_usd_normalized} USD ${matches ? '✅ coincide' : '⚠️ NO coincide'}
*Referencia:* ${reference_code}
*De:* ${sender_name}
*Banco:* ${bank_name}
*Fecha:* ${transaction_datetime}

${has_red_flags ? '⚠️ *Alertas:* ' + red_flags.join(', ') : ''}

→ Verificar en banco. Si está, mover a Pagado.
```

###### Node S5 — Lia reply to guest

If `action == 'advance_to_review'`:
> ¡Gracias! Recibimos tu comprobante. Lo estamos verificando con el banco y te confirmamos en breve (usualmente menos de 30 min).

If `action == 'flag_for_human'`:
> ¡Gracias! Recibimos tu comprobante pero necesitamos validar algunos datos. Nuestro equipo te confirma muy pronto.

If `action == 'ask_resend'`:
> No logramos leer bien el comprobante. ¿Nos puedes reenviar la captura completa de SINPE, asegurándote de que se vean el monto, la referencia y el nombre? 🙏

If `action == 'ignore'`:
> (silent — pass to Lia's normal LLM reply path; she'll handle it as a regular message)

##### Human verification → `Pagado`

The reception/finance human opens the lead in Kommo, sees the structured SINPE note, checks the bank, and:
- If transfer is real → moves status to `Pagado` → triggers Workflow 1 Trigger B → CAPI Purchase fires + reception handoff begins.
- If transfer is fake or wrong amount → posts a note + Lia (or human) asks guest to clarify.

##### Optional Level-C upgrade — auto-confirm via bank notification

When BAC/BCR sends an SMS or email for each incoming SINPE, an n8n trigger can parse it (extract amount + reference) and match against open `Pago en revisión` leads. If a match is found, auto-advance to `Pagado`. This eliminates the human bank-check step entirely. Defer until you have ~2 weeks of Level-B data showing the extraction is reliable.

---

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
