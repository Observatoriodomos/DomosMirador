---
name: meta-ads
description: Diagnose Meta Pixel/CAPI tracking, sync product catalogs to Meta Commerce, and detect creative fatigue / anomalies in Meta Ads. Use when the user asks about Facebook/Instagram ads, Meta Pixel events, Conversion API (CAPI), Meta Catalog/Commerce feeds, ad fatigue, CPA/CPM/CTR anomalies, or anything in Meta Events Manager / Ads Manager.
license: MIT
compatibility: Scaffold stage. Designed against mock fixtures in ./mocks/. Live wiring requires a Meta access token with ads_management + catalog_management scopes (not included).
metadata:
  status: scaffold
  version: "0.1.0"
---

# Meta Ads

Three diagnostic and automation surfaces for Meta (Facebook/Instagram) advertising. This skill is at scaffold stage — interfaces and mocks are in place, live API calls are stubbed.

## Available Commands

| Command | What it does | Status |
|---------|-------------|--------|
| `pixel-capi-debug` | Compare frontend Pixel events vs. backend CAPI payloads; flag parameter mismatches, missing currency/value, duplicate event_ids, dropped fields. | Stub + mocks |
| `catalog-sync` | Read inventory from a source (DB/CSV/API), normalize to Meta Catalog schema, push create/update/delete batches. | Stub + mocks |
| `ads-fatigue-anomaly` | Pull 7d/30d Ads Insights, compute CTR/CPM/CPA trends per creative, flag fatigue and anomalies. | Stub + mocks |

## Layout

```
plugins/meta-ads/
├── SKILL.md
├── commands/
│   ├── pixel-capi-debug.md
│   ├── catalog-sync.md
│   └── ads-fatigue-anomaly.md
├── references/
│   ├── meta-apis.md                  # endpoints, payload shapes, required fields
│   ├── octorate-capi-wiring.md       # checklist to restore CAPI on Octorate-managed pixel
│   ├── n8n-capi-setup.md             # n8n nodes: Octorate engine-page booking → main pixel CAPI
│   ├── lia-whatsapp-capi-setup.md    # n8n nodes: Lia WhatsApp booking → main pixel CAPI (chat source)
│   ├── n8n-payment-and-handoff.md    # Stripe + SINPE → CAPI Purchase, reception handoff, rate-sheet InitiateCheckout
│   ├── customer-journey-roadmap.md   # end-to-end journey map + gap analysis + 80/20 sequence
│   ├── event-mapping.md              # current → standard event mapping (Domos-specific)
│   └── pixel-cleanup-plan.md         # tiered deletion plan with dependency checks
├── templates/
│   ├── purchase-event-browser.html   # drop-in fbq snippets (only for non-hosted booking pages)
│   └── purchase-event-capi.py        # generic Python CAPI POST template (Flask/FastAPI)
├── mocks/
│   ├── pixel-events.json
│   ├── capi-events.json
│   ├── catalog-products.csv
│   └── insights-30d.json
└── scripts/
    └── diff-pixel-capi.py
```

## Domos Mirador implementation guides

Real-account diagnostic + remediation deliverables, built from a live audit of business `977790985957267`:

- **`references/octorate-capi-wiring.md`** — fix CAPI on `OctorateEnginDomos` (1140308951186601), silent since 2025-11-05.
- **`references/n8n-capi-setup.md`** — append two nodes to the existing Octorate-booking n8n workflow to fire CAPI Purchase to the **main pixel** in parallel with Octorate's native CAPI.
- **`references/lia-whatsapp-capi-setup.md`** — same pattern for Lia's WhatsApp-driven bookings (`action_source: 'chat'`), including `ctwa_clid` attribution for Click-to-WhatsApp ads.
- **`templates/purchase-event-capi.py`** — generic Python reference if you ever move off n8n.
- **`templates/purchase-event-browser.html`** — only relevant if your confirmation page lives on your domain (not Octorate's).
- **`references/event-mapping.md`** — concrete current → standard event mapping for the custom events firing today (`dPageView`, `SubscribedButtonClick`, etc.).
- **`references/pixel-cleanup-plan.md`** — tiered deletion plan with safety check (audience references verified empty on main account).

## Going from scaffold to live

1. Choose one command to flesh out first.
2. Replace the relevant `mocks/*` fixture with a real export (or wire a live fetch).
3. Add credentials via env vars — never commit tokens. Expected vars:
   - `META_ACCESS_TOKEN` — long-lived system user token
   - `META_AD_ACCOUNT_ID` — `act_<id>`
   - `META_PIXEL_ID` — for CAPI
   - `META_CATALOG_ID` — for Commerce
4. Promote the script in `scripts/` from mock-driven to API-driven, keeping the same input/output shape.

## Out of scope

- Token acquisition / OAuth flows (do this via Meta Business Manager).
- Compliance review (CAPA, iOS 14.5 ATT signals, EEA consent) — flag these as TODO in the command output but don't block.
