import os
import requests

API_BASE = os.getenv("PROVIDER_API_BASE")
API_KEY = os.getenv("PROVIDER_API_KEY")


class Provider:

    @staticmethod
    def create_order(service_id: str, country_id: str):
        """
        Generic create order request
        """
        url = f"{API_BASE}/create-order"

        params = {
            "api_key": API_KEY,
            "service": service_id,
            "country": country_id
        }

        try:
            r = requests.get(url, params=params, timeout=20)
            return r.json()
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    @staticmethod
    def order_status(order_id: str):
        """
        Generic order status
        """
        url = f"{API_BASE}/order-status"

        params = {
            "api_key": API_KEY,
            "order_id": order_id
        }

        try:
            r = requests.get(url, params=params, timeout=20)
            return r.json()
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    @staticmethod
    def cancel_order(order_id: str):
        """
        Generic cancel order
        """
        url = f"{API_BASE}/cancel-order"

        params = {
            "api_key": API_KEY,
            "order_id": order_id
        }

        try:
            r = requests.get(url, params=params, timeout=20)
            return r.json()
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
