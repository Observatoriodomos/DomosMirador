# Pixel cleanup plan (Observatorio DOMOS Bosque Tropical business 977790985957267)

Pixel deletion in Meta is **permanent** and removes historical event data. This plan splits the 20 datasets into three tiers based on safety, with explicit dependencies checked.

## Safety check performed

- Main ad account `65859017` "Anuncios Observatorio": **0 WEBSITE custom audiences** found. → No retargeting audiences are sourced from any of these pixels in the main spending account.
- Active campaigns: not yet audited per-account. **Do this before deleting any pixel that has fired in the last 90 days.**

## Tier 1 — Safe to delete (dormant or empty, no risk)

These have either never fired or last fired in 2021–2023. Highest cleanup value, lowest risk.

| Dataset ID | Name | Last fired (browser) | Notes |
|---|---|---|---|
| `710840542915011` | Caverhill-Lodge-pixel | 2021-02-25 | Old property, not Domos. |
| `1340920862637534` | Wlady movie FEstival | 2023-03-16 | Personal/old project. |
| `1940678329626404` | El Mirador Simple Booking | never | Predecessor to current stack. |
| `2010151342512522` | Finca el Mirador's Pixel | never | Predecessor. |
| `564090479729034` | Observatorio DOMOS Bosque Tropical Event Data | never | Empty duplicate (1 of 3). |
| `1392887072090091` | Observatorio DOMOS Bosque Tropical Event Data | never | Empty duplicate (2 of 3). |
| `1833333393948566` | Observatorio DOMOS Bosque Tropical Event Data | never | Empty duplicate (3 of 3). |
| `830713622908938` | Catalog Domos Mirador | never | Catalog duplicate. Keep `960541546959116` "Catalog APi Domos" if any catalog feed is live. |
| `1580405806707200` | Domos Catalog | never | Catalog duplicate. |

## Tier 2 — Consolidate before deleting

These have signal but are duplicates or fragments of what should be a single pixel.

| Dataset ID | Name | Status | Plan |
|---|---|---|---|
| `1727298344968140` | Domos Mirador WhatsApp Extras Wapp | created 2026-06-01, never fired | Pick one of the two WhatsApp pixels, install only that one, delete the other. |
| `4323706314552040` | Domos Mirador WhatsApp v3 | created 2026-06-01, never fired | Same — pick one. |
| `1338450634126000` | Reserva Done! | browser-only, no CAPI | If meant as the booking-confirmation pixel: consolidate into `458979157007770` Pixel Principal via the dedup contract, then delete. Otherwise, fix its CAPI per `octorate-capi-wiring.md`. |

## Tier 3 — Do NOT delete (active or strategic)

| Dataset ID | Name | Why keep |
|---|---|---|
| `458979157007770` | Domos Mirador Pixel Principal | Main pixel, fires today. Fix the missing Purchase event instead. |
| `1140308951186601` | OctorateEnginDomos | Booking engine pixel. Fix CAPI per `octorate-capi-wiring.md` instead. |
| `1034751861376768` | Leads Domos | Has CAPI firing (rare). Verify whether still used; if yes, keep. |
| `1550641649041894` | Pixel Terminal Verde Hotel Link | Different property (Termianal Verde) — different business decision. |
| `263127732982931` | Pixel Mirador Hotel Link - Home page | Last fired Feb 2026; could be the Hotel Link page. Confirm with the property page owner. |
| `919289870908167` | AP | Created 2026-04-07, never fired. **Investigate intent before deleting.** Could be a planned integration. |
| `960541546959116` | Catalog APi Domos | Created 2026-05-16, never fired. Keep if catalog work is planned. |
| `1788060485488304` | Catalogo WE Com | Created 2026-04-06, never fired. **Investigate intent before deleting.** |

## How to delete (you must do this in Meta — there is no API tool)

1. Open https://business.facebook.com/events_manager2/list/dataset/<dataset_id>
2. ⋯ menu (top right) → **Delete Data Source** → confirm.
3. Meta will ask if you want to keep audiences derived from the dataset — there are none for the main account, so this is moot. **Other accounts: verify first.**
4. Repeat for each Tier 1 dataset.

## Before deleting any non-Tier-1 pixel

Run this in a new chat:

```
For each candidate pixel ID:
  ads_get_ad_account_custom_audiences for every queryable ad account in the business
  Filter audiences whose pixel_id == candidate
  If any active audience references it → DO NOT DELETE
```

Then check active campaigns:

```
ads_get_ad_entities to list active ad sets/campaigns
Search optimization_goal and tracking_specs for references to the candidate pixel
```

Only delete after both checks return empty.
