"""
Server-side CAPI POST template for Purchase and Lead events.

Pair with templates/purchase-event-browser.html — `event_id` here MUST equal
the `eventID` set on the browser-side fbq call so Meta dedups them.

Requires env vars (do not commit):
    META_PIXEL_ID         e.g. "458979157007770"  (Domos Mirador Pixel Principal)
    META_ACCESS_TOKEN     long-lived system-user token with conversions_api scope
    META_API_VERSION      e.g. "v21.0"   (default if unset)

Run from your booking webhook handler (Stripe, Octorate, your own checkout).
"""
from __future__ import annotations

import hashlib
import os
import time
from typing import Optional

import requests  # add to requirements: requests>=2.31


META_GRAPH = "https://graph.facebook.com"


def sha256_lower(value: str) -> str:
    """Meta requires SHA-256 lowercase hex for em/ph/external_id."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def build_user_data(
    *,
    email: Optional[str] = None,
    phone_e164: Optional[str] = None,
    external_id: Optional[str] = None,
    fbc: Optional[str] = None,          # from `_fbc` cookie
    fbp: Optional[str] = None,          # from `_fbp` cookie
    client_ip: Optional[str] = None,    # request.remote_addr
    client_ua: Optional[str] = None,    # request.headers["User-Agent"]
) -> dict:
    """Build the user_data block. Include every field you have — more = better EMQ."""
    user_data: dict = {}
    if email:
        user_data["em"] = [sha256_lower(email)]
    if phone_e164:
        digits = "".join(c for c in phone_e164 if c.isdigit())
        if digits:
            user_data["ph"] = [sha256_lower(digits)]
    if external_id:
        user_data["external_id"] = [sha256_lower(external_id)]
    if fbc:
        user_data["fbc"] = fbc          # already in Meta's format, do NOT hash
    if fbp:
        user_data["fbp"] = fbp          # already in Meta's format, do NOT hash
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if client_ua:
        user_data["client_user_agent"] = client_ua
    return user_data


def send_purchase(
    *,
    event_id: str,
    booking_id: str,
    total_usd: float,
    room_type_id: str,
    nights: int,
    event_source_url: str,
    user_data: dict,
) -> requests.Response:
    """Fire a deduplicated Purchase via CAPI."""
    pixel_id = os.environ["META_PIXEL_ID"]
    token = os.environ["META_ACCESS_TOKEN"]
    version = os.environ.get("META_API_VERSION", "v21.0")

    payload = {
        "data": [
            {
                "event_name": "Purchase",
                "event_time": int(time.time()),
                "event_id": event_id,            # MUST match browser-side eventID
                "action_source": "website",
                "event_source_url": event_source_url,
                "user_data": user_data,
                "custom_data": {
                    "currency": "USD",
                    "value": float(total_usd),   # numeric, not string
                    "content_ids": [room_type_id],
                    "content_type": "product",
                    "contents": [{"id": room_type_id, "quantity": int(nights)}],
                    "num_items": int(nights),
                    "order_id": booking_id,
                },
            }
        ]
    }
    return requests.post(
        f"{META_GRAPH}/{version}/{pixel_id}/events",
        params={"access_token": token},
        json=payload,
        timeout=10,
    )


def send_lead(
    *,
    event_id: str,
    lead_source: str,
    event_source_url: str,
    user_data: dict,
) -> requests.Response:
    """Fire a deduplicated Lead via CAPI."""
    pixel_id = os.environ["META_PIXEL_ID"]
    token = os.environ["META_ACCESS_TOKEN"]
    version = os.environ.get("META_API_VERSION", "v21.0")

    payload = {
        "data": [
            {
                "event_name": "Lead",
                "event_time": int(time.time()),
                "event_id": event_id,
                "action_source": "website",
                "event_source_url": event_source_url,
                "user_data": user_data,
                "custom_data": {
                    "content_category": lead_source,
                },
            }
        ]
    }
    return requests.post(
        f"{META_GRAPH}/{version}/{pixel_id}/events",
        params={"access_token": token},
        json=payload,
        timeout=10,
    )


# -------- Example wiring (delete or adapt) -----------------------------------
if __name__ == "__main__":
    # In your real handler, read these from the booking webhook + request:
    booking_event_id = "evt_booking_12345"     # same value passed to fbq's eventID
    user_data = build_user_data(
        email="guest@example.com",
        phone_e164="+50688887777",
        external_id="customer_4242",
        fbc="fb.1.1717459200000.IwAR0...",      # from _fbc cookie
        fbp="fb.1.1717459200000.1234567890",    # from _fbp cookie
        client_ip="203.0.113.5",
        client_ua="Mozilla/5.0 ...",
    )
    response = send_purchase(
        event_id=booking_event_id,
        booking_id="12345",
        total_usd=189.00,
        room_type_id="domo_premium",
        nights=2,
        event_source_url="https://domosmirador.com/booking/confirmation/12345",
        user_data=user_data,
    )
    print(response.status_code, response.text)
