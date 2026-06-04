# Custom → standard event mapping (Domos Mirador)

Observed via `ads_get_dataset_stats` over a 7-day window. Meta only optimizes campaigns against **standard** events — every custom event below is wasted signal unless mapped.

## Current event inventory

| Current event | Pixel(s) firing it | Volume (7d) | Standard? | Action |
|---|---|---|---|---|
| `PageView` | All active | very high | ✅ standard | Keep — but it's not enough on its own. |
| `ViewContent` | `458979157007770`, `1140308951186601` | medium | ✅ standard | Keep. Ensure `content_ids` + `content_type` are populated. |
| `ViewCategory` | `458979157007770` | low | ✅ standard | Keep. Ensure `content_category` is set. |
| `AddToCart` | `458979157007770` | medium (bursts up to 44/hr) | ✅ standard | Keep — but pair with downstream Purchase. AddToCart alone leaves the funnel orphaned. |
| `InitiateCheckout` | `1140308951186601` only | low–medium | ✅ standard | Keep. Move to **main pixel** as well via dedup `event_id`. |
| `dPageView` | `458979157007770`, `1140308951186601` | medium | ❌ custom | **Remap.** See decision rules below. |
| `scroll` | `458979157007770`, `1140308951186601` | low | ❌ custom | **Drop.** Doesn't optimize anything. |
| `click` | `458979157007770`, `1140308951186601` | low | ❌ custom | **Conditional remap.** CTA→Lead if it's an inquiry button; otherwise drop. |
| `socialLink` | `458979157007770` | low | ❌ custom | **Drop.** No campaign optimizes on social-link clicks. |
| `notificationClose` | `458979157007770`, `1140308951186601` | low | ❌ custom | **Drop.** Negative-signal-ish; no use. |
| `SubscribedButtonClick` | `1140308951186601` | low | ❌ custom | **Remap to `Lead`** with `content_category: 'newsletter'`. |
| **`Purchase`** | nowhere | **0** | ✅ standard | **Add.** This is the critical gap. |
| **`Lead`** | nowhere | **0** | ✅ standard | **Add.** For inquiries / form fills. |

## Decision rules for `dPageView`

`dPageView` looks like a dynamic/SPA route change. Map based on the route:

| URL pattern | Map to | Notes |
|---|---|---|
| `/booking/*` or `/checkout/*` | `InitiateCheckout` | When the user lands on the booking flow start. |
| `/confirmation/*` or `/thank-you/*` | `Purchase` (browser) **and** fire CAPI Purchase from server | Use the booking ID as `eventID` for dedup. |
| `/domos/*`, `/aptos/*`, `/odbt/*` (product detail) | `ViewContent` | Already standard — just use the standard name. |
| anything else | drop | `PageView` already covers it. |

## Decision rules for `click`

| Element | Map to | Notes |
|---|---|---|
| "Book now" / "Reservar" CTA | `InitiateCheckout` | Same dedup contract as `dPageView` on the booking page. |
| "WhatsApp" / inquiry buttons | `Lead` | `content_category: 'whatsapp'` |
| "Send" on contact form | `Lead` | `content_category: 'form'` |
| Phone-tap on mobile | `Lead` | `content_category: 'phone'` |
| Anything else | drop | |

## Implementation note

Each event must carry `eventID` (browser) / `event_id` (CAPI) for dedup. Generate one UUID per event server-side and pass it to both surfaces. See `../templates/purchase-event-browser.html` and `../templates/purchase-event-capi.py`.
