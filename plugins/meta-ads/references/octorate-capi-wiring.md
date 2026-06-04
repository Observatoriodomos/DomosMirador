# Wire CAPI on `OctorateEnginDomos` (1140308951186601)

CAPI on this pixel has been silent since **2025-11-05** while the browser pixel keeps firing. Likely cause: the Octorate→Meta access token expired, or the integration was disabled. The browser→CAPI dedup contract also has to be re-established with a shared `event_id`.

## Symptoms confirmed (read-only from Meta side)

- Dataset `1140308951186601` `last_fired_time`: 2026-06-03 — **browser fine**.
- Dataset `1140308951186601` `server_last_fired_time`: **2025-11-05** — CAPI broken ~7 months.
- 7-day stats: `InitiateCheckout` firing browser-side (peak 7/hr on 2026-05-28 night) — these are exactly the events that should be deduplicated against CAPI.

## Fix — Octorate side

Do this in the Octorate Engine dashboard (not Meta):

1. **Settings → Integrations → Meta / Facebook Pixel** (path may differ by Octorate version).
2. Confirm the **Pixel ID** field is `1140308951186601`. Fix if it's pointing at a stale ID.
3. Generate a new **Meta system-user access token** (see "Token generation" below) and paste it into Octorate's CAPI field. The old token is almost certainly expired.
4. Toggle **"Send events via Conversions API"** ON (or whatever Octorate calls it — sometimes labelled "Server-side tracking").
5. Set **Event ID source** to "Use Octorate booking reference" — this becomes the dedup key. **Critical:** this same `event_id` must also be set on the browser side (step in next section).
6. Save → run a test booking → check Meta Events Manager → Test Events.

## Token generation (Meta side)

1. https://business.facebook.com/settings/system-users → pick or create a System User with the **`Advertiser` role** on `Observatorio DOMOS Bosque Tropical` business.
2. Assign the System User to the pixel: `1140308951186601` with **Manage** access.
3. Generate a token with scopes: `ads_management`, `business_management`, plus the **per-pixel "Conversions API"** scope if your version exposes it as a separate checkbox.
4. **Long-lived, no expiry** — pick "Never" for expiration. Store it in Octorate; do not commit.

## Browser-side dedup contract

For each `InitiateCheckout` / `Purchase` the browser sends, set `eventID` to the Octorate booking reference so CAPI's `event_id` matches:

```html
<!-- on the Octorate-rendered confirmation page -->
<script>
  fbq('track', 'Purchase', {
    currency: 'USD',
    value: {{ booking.total_usd }},
    content_ids: ['{{ booking.room_type_id }}'],
    content_type: 'product',
    contents: [{ id: '{{ booking.room_type_id }}', quantity: {{ booking.nights }} }]
  }, {
    eventID: '{{ booking.id }}'  // <-- must equal the CAPI event_id Octorate sends
  });
</script>
```

If Octorate doesn't render the page (they redirect off-site for some PMS configs), put the snippet on **your** thank-you page and pass the booking ID via the redirect URL.

## Verify the fix

After 24 hours, re-run:

```
ads_get_datasets(business_id="977790985957267")
```

`server_last_fired_time` for `1140308951186601` should be within the last hour. Then:

```
ads_get_dataset_quality(dataset_id="1140308951186601")
```

EMQ scores should appear once enough deduplicated events accumulate (typically 24–48h).

## TODO

- Repeat this checklist for `Reserva Done!` (1338450634126000) and `Pixel Mirador Hotel Link` (263127732982931) — they've **never** fired CAPI.
- If `Reserva Done!` is actually meant to be the booking-confirmation pixel, consider consolidating into `OctorateEnginDomos` instead of running two parallel ones.
