# Meta APIs — quick reference

Endpoint shapes and required fields used by this skill. Use Graph API version `v21.0` or later; pin the version in code, don't accept the account default.

## Conversion API (CAPI)

**Endpoint**

```
POST https://graph.facebook.com/v21.0/<PIXEL_ID>/events
?access_token=<TOKEN>
```

**Minimum body for a Purchase**

```json
{
  "data": [
    {
      "event_name": "Purchase",
      "event_time": 1717459200,
      "event_id": "evt_abc123",
      "action_source": "website",
      "event_source_url": "https://shop.example.com/checkout/success",
      "user_data": {
        "em": ["7b17fb0bd173f625b58636fb796407c22b3d16fc78302d79f0fd30c2fc2fc068"],
        "client_ip_address": "203.0.113.5",
        "client_user_agent": "Mozilla/5.0 ..."
      },
      "custom_data": {
        "currency": "USD",
        "value": 99.00,
        "content_ids": ["sku_42"],
        "content_type": "product"
      }
    }
  ]
}
```

- `event_id` must match the Pixel-side `eventID` for deduplication.
- `user_data.em` / `ph` must be SHA-256 lowercase hex.
- `action_source` is required.

## Catalog Batch API

**Endpoint**

```
POST https://graph.facebook.com/v21.0/<CATALOG_ID>/batch
?access_token=<TOKEN>
```

**Body**

```json
{
  "requests": [
    {
      "method": "CREATE",
      "retailer_id": "sku_42",
      "data": {
        "name": "Summer Tee",
        "description": "...",
        "availability": "in stock",
        "condition": "new",
        "price": "19.99 USD",
        "url": "https://shop.example.com/p/summer-tee",
        "image_url": "https://cdn.example.com/summer-tee.jpg",
        "brand": "Example"
      }
    }
  ]
}
```

- Up to 5000 items per batch.
- Use `UPDATE` for changes, `DELETE` to remove. `id` (retailer_id) is the stable key.

## Ads Insights

**Endpoint**

```
GET https://graph.facebook.com/v21.0/act_<ACCOUNT_ID>/insights
?level=ad
&fields=ad_id,ad_name,impressions,clicks,spend,ctr,cpm,cpc,actions,action_values
&time_increment=1
&date_preset=last_30d
&limit=500
&access_token=<TOKEN>
```

- Paginate via the `paging.next` cursor.
- `actions` returns an array — filter by `action_type` (`purchase`, `add_to_cart`, etc.) to get conversions.

## Rate limits to remember

- Marketing API uses a per-app + per-ad-account points budget. Check `X-Business-Use-Case-Usage` response header.
- Catalog writes: ~200 QPS per catalog, bursty; back off on `error.code == 80004`.
- Insights reads: tier-dependent; long queries may return a job handle — poll `/<job_id>` until `async_status: Job Completed`.
