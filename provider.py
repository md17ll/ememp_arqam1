import os
import requests

API_BASE = (os.getenv("PROVIDER_API_BASE") or "").rstrip("/")
API_KEY = (os.getenv("PROVIDER_API_KEY") or "").strip()


class ProviderError(Exception):
    pass


def _check_config():
    if not API_BASE:
        raise ProviderError("PROVIDER_API_BASE is missing")
    if not API_KEY:
        raise ProviderError("PROVIDER_API_KEY is missing")


def create_order(service: str, country: str) -> dict:
    """
    Create an order.
    Expected response example:
    {"status":"success","id":"123","number":"+4477....","cost":0.5}
    """
    _check_config()

    url = f"{API_BASE}/create-order"
    params = {"api_key": API_KEY, "service": service, "country": country}

    r = requests.get(url, params=params, timeout=30)
    data = r.json()

    if str(data.get("status")).lower() not in ("success", "ok", "true"):
        raise ProviderError(f"create_order failed: {data}")

    provider_order_id = data.get("id") or data.get("order_id")
    number = data.get("number") or data.get("phone") or data.get("phone_number")
    cost = data.get("cost")

    if not provider_order_id or not number:
        raise ProviderError(f"create_order missing fields: {data}")

    return {"provider_order_id": str(provider_order_id), "number": str(number), "cost": cost}


def order_status(provider_order_id: str) -> dict:
    """
    Get order status / SMS code.
    Expected response example:
    {"status":"success","state":"waiting"} OR {"status":"success","state":"received","sms_code":"1234"}
    """
    _check_config()

    url = f"{API_BASE}/order-status"
    params = {"api_key": API_KEY, "order_id": provider_order_id}

    r = requests.get(url, params=params, timeout=30)
    data = r.json()
    return data


def cancel_order(provider_order_id: str) -> dict:
    """
    Cancel order.
    Expected response example:
    {"status":"success","state":"cancelled"}
    """
    _check_config()

    url = f"{API_BASE}/cancel-order"
    params = {"api_key": API_KEY, "order_id": provider_order_id}

    r = requests.get(url, params=params, timeout=30)
    data = r.json()
    return data
