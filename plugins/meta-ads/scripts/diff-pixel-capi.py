#!/usr/bin/env python3
"""
Diff Meta Pixel (frontend) events vs. Conversion API (backend) payloads.
Runs against the mock fixtures by default; pass --pixel and --capi to override.

Usage:
    python3 diff-pixel-capi.py
    python3 diff-pixel-capi.py --pixel pixel.json --capi capi.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MOCKS_DIR = SCRIPT_DIR.parent / "mocks"

REQUIRED_BY_EVENT = {
    "Purchase": {"currency", "value"},
    "AddToCart": {"currency", "value", "content_ids", "content_type"},
    "InitiateCheckout": {"currency", "value", "content_ids", "content_type"},
}

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def index_by_id(events: list[dict], key: str) -> dict[str, dict]:
    return {e[key]: e for e in events if key in e}


def check_pair(event_name: str, event_id: str, pixel: dict, capi: dict) -> list[dict]:
    issues: list[dict] = []
    p_params = pixel.get("params", {})
    c_custom = capi.get("custom_data", {})

    for field in REQUIRED_BY_EVENT.get(event_name, set()):
        c_val = c_custom.get(field)
        if c_val in (None, ""):
            issues.append({
                "severity": "error",
                "event_id": event_id,
                "event_name": event_name,
                "field": field,
                "pixel_value": p_params.get(field),
                "capi_value": c_val,
                "message": f"CAPI missing required '{field}' for {event_name}",
            })

    currency = c_custom.get("currency")
    if currency and not (isinstance(currency, str) and currency.isupper() and len(currency) == 3):
        issues.append({
            "severity": "error",
            "event_id": event_id,
            "event_name": event_name,
            "field": "currency",
            "pixel_value": p_params.get("currency"),
            "capi_value": currency,
            "message": "currency must be ISO 4217 uppercase three-letter",
        })

    value = c_custom.get("value")
    if value is not None and not isinstance(value, (int, float)):
        issues.append({
            "severity": "error",
            "event_id": event_id,
            "event_name": event_name,
            "field": "value",
            "pixel_value": p_params.get("value"),
            "capi_value": value,
            "message": "value must be numeric, not string",
        })

    if "action_source" not in capi:
        issues.append({
            "severity": "warning",
            "event_id": event_id,
            "event_name": event_name,
            "field": "action_source",
            "pixel_value": None,
            "capi_value": None,
            "message": "CAPI missing action_source — events may be downranked",
        })

    for hashed_field in ("em", "ph"):
        values = capi.get("user_data", {}).get(hashed_field, [])
        for v in values:
            if not SHA256_HEX.match(v or ""):
                issues.append({
                    "severity": "error",
                    "event_id": event_id,
                    "event_name": event_name,
                    "field": f"user_data.{hashed_field}",
                    "pixel_value": None,
                    "capi_value": v,
                    "message": f"user_data.{hashed_field} must be SHA-256 lowercase hex",
                })

    p_ts = pixel.get("timestamp")
    c_ts = capi.get("event_time")
    if p_ts and c_ts and abs(p_ts - c_ts) > 300:
        issues.append({
            "severity": "warning",
            "event_id": event_id,
            "event_name": event_name,
            "field": "event_time",
            "pixel_value": p_ts,
            "capi_value": c_ts,
            "message": f"timestamp drift {abs(p_ts - c_ts)}s exceeds 5min",
        })

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixel", default=str(MOCKS_DIR / "pixel-events.json"))
    parser.add_argument("--capi", default=str(MOCKS_DIR / "capi-events.json"))
    args = parser.parse_args()

    pixel_events = load(Path(args.pixel))
    capi_events = load(Path(args.capi))

    pixel_by_id = index_by_id(pixel_events, "eventID")
    capi_by_id = index_by_id(capi_events, "event_id")

    issues: list[dict] = []
    pairs_checked = 0
    for event_id, pixel in pixel_by_id.items():
        capi = capi_by_id.get(event_id)
        if not capi:
            issues.append({
                "severity": "error",
                "event_id": event_id,
                "event_name": pixel.get("event_name"),
                "field": "event_id",
                "pixel_value": event_id,
                "capi_value": None,
                "message": "Pixel event has no matching CAPI event (deduplication broken)",
            })
            continue
        pairs_checked += 1
        issues.extend(check_pair(pixel["event_name"], event_id, pixel, capi))

    for event_id in capi_by_id.keys() - pixel_by_id.keys():
        issues.append({
            "severity": "warning",
            "event_id": event_id,
            "event_name": capi_by_id[event_id].get("event_name"),
            "field": "event_id",
            "pixel_value": None,
            "capi_value": event_id,
            "message": "CAPI event has no matching Pixel event",
        })

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")

    report = {
        "summary": {
            "pairs_checked": pairs_checked,
            "mismatches": errors,
            "warnings": warnings,
        },
        "issues": issues,
    }
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
