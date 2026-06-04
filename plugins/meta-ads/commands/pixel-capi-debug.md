# pixel-capi-debug

Compare a frontend Meta Pixel event stream against the matching backend Conversion API (CAPI) payloads and report mismatches.

## Inputs

- `pixel_events`: JSON array of Pixel events (from `fbq('track', ...)` capture, browser console, or Events Manager → Test Events).
- `capi_events`: JSON array of CAPI events (your server's outbound payload to `/v<api>/<pixel_id>/events`).

Both default to the fixtures in `../mocks/` when no path is provided.

## What to check

For each `(event_name, event_id)` pair, compare frontend vs. backend:

1. **Deduplication keys present** — both sides must carry the same `event_id` (or `eventID` on the Pixel side).
2. **Required parameters** — for `Purchase`: `currency`, `value`. For `AddToCart` / `InitiateCheckout`: `content_ids`, `content_type`, `value`, `currency`.
3. **User data hashing** — CAPI `user_data.em` / `ph` must be SHA-256 lowercase hex. Flag any plaintext.
4. **Action source** — CAPI must include `action_source` (`website`, `app`, etc.). Missing → events get downranked.
5. **Timestamp drift** — CAPI `event_time` must be within 7 days of now and within ~5 min of the Pixel-side timestamp.
6. **Duplicate event_ids within a 24h window** — flag.
7. **Currency code shape** — ISO 4217 uppercase three-letter (e.g., `USD`, not `usd` or `US$`).
8. **Value type** — numeric, not string. Flag `"99.00"` vs `99.00`.

## Output shape

```json
{
  "summary": { "pairs_checked": 12, "mismatches": 3, "warnings": 2 },
  "issues": [
    {
      "severity": "error",
      "event_id": "evt_abc123",
      "event_name": "Purchase",
      "field": "currency",
      "pixel_value": "USD",
      "capi_value": null,
      "message": "CAPI payload missing required 'currency' for Purchase"
    }
  ]
}
```

## Reference implementation

See `../scripts/diff-pixel-capi.py` — runs against the mocks and prints the report.

## TODO before going live

- Pull real events from Events Manager Test Events API instead of fixture files.
- Add ATT/consent signal checks (`data_processing_options`).
- Wire to a CI step that runs against canned synthetic traffic.
