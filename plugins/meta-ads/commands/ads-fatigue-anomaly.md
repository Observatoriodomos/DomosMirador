# ads-fatigue-anomaly

Pull per-ad performance from the Meta Ads Insights API, compute trend signals, and flag creative fatigue and metric anomalies.

## Inputs

- `account_id`: `act_<id>`. From `META_AD_ACCOUNT_ID` when live.
- `lookback_days`: default 30.
- `level`: `ad` (default), `adset`, `campaign`.

In mock mode, reads `../mocks/insights-30d.json`.

## Fields requested

```
ad_id, ad_name, adset_id, campaign_id,
date_start, date_stop,
impressions, clicks, spend,
ctr, cpm, cpc, cpp,
actions, action_values, conversion_values
```

Breakdown: `date` (daily rows for `lookback_days`).

## Signals computed per ad

| Signal | How | Threshold |
|---|---|---|
| **Frequency creep** | 7-day rolling impressions / unique reach | > 3.5 |
| **CTR decay** | (CTR last 7d) / (CTR previous 7d) | < 0.7 → fatigue |
| **CPM spike** | (CPM today) / (CPM 7d median) | > 1.5 → anomaly |
| **CPA spike** | (CPA last 3d) / (CPA previous 14d) | > 1.5 → anomaly |
| **Spend without conversions** | spend > $X AND 0 conversions in 48h | configurable per account |
| **Auction overlap** | not from Insights — note that this requires Auction Overlap API | flag as TODO |

## Output shape

```json
{
  "window": { "lookback_days": 30, "as_of": "2026-06-04" },
  "fatigued": [
    {
      "ad_id": "1234567890",
      "ad_name": "Summer_Tee_v3",
      "signal": "ctr_decay",
      "current_7d_ctr": 0.0042,
      "previous_7d_ctr": 0.0091,
      "ratio": 0.46,
      "recommendation": "Refresh creative or pause; CTR dropped >50% week-over-week."
    }
  ],
  "anomalies": [
    {
      "ad_id": "9876543210",
      "signal": "cpm_spike",
      "current_cpm": 42.10,
      "median_7d_cpm": 18.30,
      "ratio": 2.30
    }
  ]
}
```

## TODO before going live

- Add per-account threshold overrides (some verticals run normal CPMs of $50+).
- Persist signals to a small store so we can show streaks (3 days of CTR decay is stronger than 1).
- Wire to Slack/email via a separate notifier — don't bake delivery into this skill.
