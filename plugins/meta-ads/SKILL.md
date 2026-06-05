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
│   └── meta-apis.md          # endpoints, payload shapes, required fields
├── mocks/
│   ├── pixel-events.json     # frontend Pixel events (browser)
│   ├── capi-events.json      # backend CAPI events (server) with a deliberate mismatch
│   ├── catalog-products.csv  # source inventory rows
│   └── insights-30d.json     # Ads Insights sample (per-ad, 30d daily)
└── scripts/
    └── diff-pixel-capi.py    # reference implementation against mocks
```

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
