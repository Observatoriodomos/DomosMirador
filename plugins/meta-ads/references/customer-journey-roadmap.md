# Customer journey roadmap & gap analysis — Domos Mirador

**Drafted 2026-06-04 from the audit of business `977790985957267` + conversation context. Items marked [verified] are confirmed from Meta data. Items marked [inferred] are educated guesses based on the stack you've described. Items marked [unknown] need your input — flagged inline where they block prioritization.**

## The journey, end-to-end

```
        DISCOVERY                     CONVERSATION                    BOOKING                       STAY                         AFTER

  ┌──────────────┐             ┌────────────────────┐         ┌──────────────────┐          ┌──────────────────┐         ┌──────────────────┐
  │  A. Meta ad  │             │ C. Lia qualifies   │         │ F. Octorate      │          │ I. Check-in /    │         │ K. Review        │
  │  or organic  │   ───►      │    dates/guests    │  ───►   │    booking       │   ───►   │    Reception     │  ───►   │    request       │
  │              │             │                    │         │    created       │          │    handoff       │         │                  │
  └──────┬───────┘             └─────────┬──────────┘         └─────────┬────────┘          └──────────┬───────┘         └──────────┬───────┘
         │                               │                              │                              │                            │
         ▼                               ▼                              ▼                              ▼                            ▼
  ┌──────────────┐             ┌────────────────────┐         ┌──────────────────┐          ┌──────────────────┐         ┌──────────────────┐
  │  B. First    │             │ D. Lia sends       │         │ G. Payment       │          │ J. In-stay       │         │ L. Repeat-booking│
  │  WhatsApp    │   ───►      │    quote + dates   │  ───►   │    (Stripe       │   ───►   │    requests &    │  ───►   │    nudge         │
  │  message     │             │                    │         │    or SINPE)     │          │    upsell        │         │                  │
  └──────────────┘             └─────────┬──────────┘         └─────────┬────────┘          └──────────────────┘         └──────────────────┘
                                         │                              │
                                         ▼                              ▼
                              ┌────────────────────┐         ┌──────────────────┐
                              │ E. Guest accepts   │         │ H. Pre-arrival   │
                              │    quote           │         │    info to guest │
                              └────────────────────┘         └──────────────────┘
```

## Stage-by-stage: what you have vs. what's missing

### A — Discovery (Meta ad or organic)

| State | Detail |
|---|---|
| ✅ Have | Active Meta ad accounts (`act_65859017` Anuncios Observatorio, plus 8 read-only) [verified]. Multiple pixels installed across sites [verified]. |
| ⚠️ Weak | Multiple pixels firing on the same surfaces (`www.domosmirador.com`, `directbookings.shop`, `reservar.domosmirador.com`) [verified]. Catalog datasets exist but **none have ever fired** [verified] — no dynamic product ads running. |
| ❌ Missing | **Click-to-WhatsApp (CTWA) campaigns** [confirmed in convo — planned but not running]. **`ctwa_clid` capture** in Lia's intake [confirmed missing — wired in PR #7]. Catalog feed populated → dynamic remarketing. |
| 📊 Signal gap | Top-of-funnel ad → click → message attribution is currently broken. No way to know which ad produced which booking. |

### B — First WhatsApp message [inferred — confirm flow]

| State | Detail |
|---|---|
| ✅ Have | Kommo + n8n + WhatsApp integration [verified from earlier project memory]. Inbound message creates a Kommo lead. |
| ⚠️ Weak | **No standard `Lead` event fires** when conversation starts — only `PageView` and unmapped custom events on the main pixel [verified — 0 Lead events in 7 days]. |
| ❌ Missing | CAPI `Lead` event from Lia's intake workflow with `action_source: 'chat'` (template in PR #7 `lia-whatsapp-capi-setup.md`). `ctwa_clid` + `ad_source_id` capture on first message. |
| 📊 Signal gap | Meta can't optimize ads for "people who message you" because that's not reported back. |

### C — Lia qualifies (dates, guests, preferences) [inferred]

| State | Detail |
|---|---|
| ✅ Have | Lia handles WhatsApp conversation autonomously [confirmed in convo]. |
| ❌ Missing | Mid-funnel events. No `InitiateCheckout` when Lia sends pricing. **Funnel goes dark between first message and booking.** |
| 📊 Signal gap | Meta sees Lead (if we wire it) and Purchase (if we wire it) but nothing between — so optimization is bimodal, less precise than full-funnel. |

### D — Lia sends quote [inferred — unclear if Lia generates dynamic pricing or sends fixed quotes]

| ❓ Unknown | Does Lia query Octorate availability in real-time? Where does the price come from — Octorate API, a Kommo custom field, or a fixed rate sheet? **Tell me — this affects how we wire `InitiateCheckout` value parameter.** |

### E — Guest accepts quote [inferred]

| State | Detail |
|---|---|
| ❌ Missing | `AddToCart` standard event on accept (with cart value). |

### F — Octorate booking created [verified via dataset stats — InitiateCheckout fires on OctorateEnginDomos]

| State | Detail |
|---|---|
| ✅ Have | OctorateEnginDomos pixel fires browser `InitiateCheckout` on booking start [verified, peaks 7/hr]. Octorate is wired to Kommo via n8n [verified from earlier memory]. |
| 🔴 Critical weak | **OctorateEnginDomos CAPI dead since 2025-11-05** [verified] — no server-side booking signal for ~7 months. |
| ❌ Missing | Purchase event on main pixel from Octorate webhook (PR #7 `n8n-capi-setup.md`). |

### G — Payment [unknown — confirm]

| ❓ Unknown | **Which payment method is live today?** Earlier memory referenced a Stripe vs. SINPE decision but didn't lock it. Tell me: Stripe / SINPE / bank transfer / mix? Each has a different webhook shape and a different "payment confirmed" trigger. **This blocks wiring a clean Purchase event** — we need to know what fires "booking is paid." |
| ⚠️ Likely weak | If payment confirmation is manual (someone marks "paid" in Kommo after seeing the bank transfer), there's a delay between Octorate booking creation and Purchase event — Meta's 7-day attribution window may close on slow payers. |

### H — Pre-arrival info to guest [unknown]

| ❓ Unknown | **Is there a pre-arrival sequence?** Typically: 7 days before → reminder, 2 days before → check-in time + location pin + WhatsApp number for reception, day-of → arrival window confirm. **Tell me what exists today** so I can identify gaps vs. recommend what to add. |
| ❌ Missing (probably) | Structured pre-arrival sequence in n8n. Without this, guests arrive with last-minute questions that consume reception time. |

### I — Check-in / Reception handoff [you mentioned this explicitly — "passing info to reception WhatsApp"]

| ❓ Unknown | **Who is "reception"?** A specific human's phone? A separate Kommo pipeline? A different n8n workflow? **This is the handoff design question** — without knowing the receiving end, I can't recommend the message format. |
| ❌ Missing (inferred) | A structured handoff payload (guest name, room type, check-in time, special requests, payment status, anniversary/birthday flag, allergies, languages, lead source) sent automatically from Lia's workflow to reception when booking is paid + check-in is within X hours. |
| 💡 Quick win | Even a templated WhatsApp message from n8n to reception's number with the booking JSON pretty-printed beats nothing. ~15 min to wire. |

### J — In-stay (requests, upsells) [unknown]

| ❓ Unknown | Does Lia handle in-stay (room service, extra night, late check-out)? Or is it pure reception once they arrive? |
| ❌ Missing (probably) | Upsell automation. Day-of-stay AddToCart events for ancillary purchases (transfers, tours, food/beverage) — these can flow back to CAPI on the WhatsApp/Lia pixel if you keep one of those active. |

### K — Review request [unknown]

| ❓ Unknown | Sent today? When (check-out day +1, +3)? On WhatsApp or email? |
| ❌ Missing (likely) | Standard event `Subscribe` or `CompleteRegistration` when a review is left — Meta uses these as optimization signals for repeat-business campaigns. |

### L — Repeat-booking nudge [unknown — likely missing]

| ❌ Missing (likely) | A "we'd love to host you again" sequence 30/90/180 days after check-out. This is the easiest forgotten dollar in hospitality. |
| 💡 Quick win | n8n cron: 60 days after check-out → WhatsApp template message with a returning-guest discount code. Even a 5% conversion at zero ad cost beats most paid campaigns. |

## Critical weak points, ranked

1. 🔴 **CAPI Purchase is missing on the main pixel** — biggest single signal gap. Ads can't optimize toward bookings. PR #7 `n8n-capi-setup.md` + `lia-whatsapp-capi-setup.md` fix this.
2. 🔴 **OctorateEnginDomos CAPI dead 7 months** — secondary signal gap. PR #7 `octorate-capi-wiring.md` fixes this.
3. 🔴 **No mid-funnel events (Lead, InitiateCheckout, AddToCart)** — bimodal optimization. Fix via Lia's n8n with `action_source: 'chat'` on each stage transition.
4. 🟠 **`ctwa_clid` not captured** — when you launch CTWA ads, attribution will be broken on day one without this. PR #7 `lia-whatsapp-capi-setup.md` includes the Kommo + n8n intake.
5. 🟠 **EMQ = 0 across all pixels** — user_data (em, ph, fbc, fbp) isn't being sent. Match rate is essentially zero. Same n8n fix.
6. 🟡 **Pre-arrival sequence unclear** — guest service quality + reception load. Need design once payment confirmation flow is known.
7. 🟡 **Reception handoff unclear** — Lia → reception data passing not designed. Easy quick win once we know the receiving channel.
8. 🟡 **No post-stay loop** — repeat bookings unautomated. Easy quick win.
9. 🟢 **Catalog feed unpopulated** — dynamic product ads not running. Lower priority until conversion tracking is fixed.
10. 🟢 **Pixel sprawl** — 20 datasets, ~9 dormant. Hygiene only; doesn't change funnel performance.

## Where to start — the 80/20 sequence

| Step | Why | Effort | Who |
|---|---|---|---|
| **1. Step A (Octorate native CAPI)** | Cheapest fix; restores Octorate's built-in CAPI to OctorateEnginDomos. | 30 min | You (Octorate dashboard) |
| **2. Step C (Lia → main pixel CAPI Purchase)** | Highest-leverage signal. Single biggest lift to ad optimization. | ~20 min | You (n8n workflow `kommo2`) |
| **3. ctwa_clid capture in Lia's intake** | Future-proofs for CTWA ads — when you launch, attribution works day one. | ~15 min | You (Kommo custom fields + n8n Set node) |
| **4. Tell me payment method + reception channel** | Unblocks everything in stages G, I, J. | 2 min | You (reply here) |
| **5. Reception handoff workflow** | Quick win + measurable service improvement. | ~30 min once #4 is answered | Me (write workflow) + you (deploy) |
| **6. Mid-funnel Lia events** | InitiateCheckout / AddToCart on quote-send / quote-accept. Bigger funnel resolution. | ~30 min | Me (writes) + you (deploy) |
| **7. Pre-arrival sequence** | Guest experience + reception load. | Design first, build second. | Joint design |
| **8. Post-stay return-guest nudge** | Cheap recurring revenue. | ~45 min | Me (write) + you (deploy) |

Don't try to do all 8 at once. Steps 1–3 are this week's work; they fix the diagnostic problem. Steps 5–8 are next week, once measurement is back online.

## What's blocking me

Three questions, listed by what they unblock:

1. **Payment method** (Stripe / SINPE / bank / mix) → unblocks payment confirmation event design.
2. **Reception channel** (a person's WhatsApp number, a Kommo pipeline, a separate n8n flow) → unblocks the handoff workflow.
3. **Does Lia query Octorate in real-time for pricing, or use a fixed rate sheet?** → unblocks the `InitiateCheckout` value parameter wiring.

Answer those three and I'll have everything I need to specify the remaining workflows.
