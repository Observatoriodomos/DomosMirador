# catalog-sync

Sync a product/inventory source into a Meta Commerce Catalog using the [Catalog Batch API](https://developers.facebook.com/docs/marketing-api/catalog-batch-api/).

## Inputs

- `source`: path to a CSV / JSON / DB query result with one row per SKU. Defaults to `../mocks/catalog-products.csv`.
- `catalog_id`: `META_CATALOG_ID` env var when live; ignored in mock mode.

## Required source columns

| Column | Meta field | Notes |
|---|---|---|
| `id` | `retailer_id` | Stable SKU. Never recycle. |
| `title` | `name` | Max 150 chars. |
| `description` | `description` | Plain text, max 5000 chars. |
| `availability` | `availability` | `in stock` / `out of stock` / `preorder` / `discontinued`. |
| `condition` | `condition` | `new` / `refurbished` / `used`. |
| `price` | `price` | Format: `"19.99 USD"` — value + space + ISO currency. |
| `link` | `url` | Canonical PDP URL. |
| `image_link` | `image_url` | HTTPS, 500×500 minimum, no watermarks. |
| `brand` | `brand` | Required for shopping ads. |

Optional but recommended: `sale_price`, `sale_price_effective_date`, `gtin`, `mpn`, `google_product_category`, `custom_label_0..4`.

## Sync strategy

1. Hash each row (excluding `id`) into a content fingerprint.
2. Compare against the last sync snapshot (stored locally — `../mocks/last-sync.json` in mock mode).
3. Build a batch with three lists:
   - `CREATE` — new `id`s.
   - `UPDATE` — same `id`, changed fingerprint.
   - `DELETE` — `id`s missing from current source.
4. Chunk into batches of 5000 (Meta's hard limit) and submit.
5. Poll the returned `handles` until `status: finished`; surface any per-item errors.

## Output shape

```json
{
  "summary": { "create": 12, "update": 3, "delete": 1, "errors": 0 },
  "errors": [],
  "batch_handles": ["AYZZ...", "AYZA..."]
}
```

## Dry run

Default mode is dry-run: prints the batch JSON to stdout, makes no API calls. Pass `--apply` (when live) to actually submit.

## TODO before going live

- Replace mock fingerprint store with a real snapshot table.
- Add image preflight (HEAD request, min-size check) before submission to avoid Meta-side rejections.
- Handle rate limits (catalog write QPS) with exponential backoff.
