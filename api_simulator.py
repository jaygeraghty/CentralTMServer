
from flask import current_app
from datetime import datetime
import json

# API Key for authentication
API_KEY = "AIL7DYIPyGKQVXNzCdjl5OvciXTdVzGBZ8R5TMUFFkbm8rmG2J7dCrmGNIRPKheWIHkzKA7J966e2VWPNYPX2eOrHPf2JMkj0pLN0p1YnhStKGEHmH1ly1LBu1IKpg8U"

def simulate_realtime_step():
    """Simulate a realtime step API call"""
    with current_app.test_client() as client:
        response = client.post(
            "/api/realtime_update",
            json={
                "headcode": "2A45",
                "tiploc": "LDYW",
                "event_type": "arr",
                "from_berth": "X2_1234",
                "to_berth": "X2_5678",
                "actual_step_time": datetime.utcnow().isoformat(),
                "calculated_event_time": datetime.utcnow().isoformat()
            },
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        print(f"Realtime Step Response: {response.status_code}, {response.get_json()}")
        return {
            "status_code": response.status_code,
            "response": response.get_json() if response.get_json() else response.get_data(as_text=True)
        }

def simulate_forecast_update():
    """Simulate a forecast update API call"""
    with current_app.test_client() as client:
        response = client.post(
            "/api/forecast_update",
            json={
                "uid": "A12345",
                "tiploc": "LDYW",
                "forecast": {
                    "arr_et": "12:47",
                    "platform": "2"
                },
                "timestamp": datetime.utcnow().isoformat()
            },
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        print(f"Forecast Update Response: {response.status_code}, {response.get_json()}")
        return {
            "status_code": response.status_code,
            "response": response.get_json() if response.get_json() else response.get_data(as_text=True)
        }
