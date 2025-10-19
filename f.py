import requests

# === Configuration ===
API_BASE = "http://localhost:5000"

forecast_payload = {
    "uid": "P17935",
    "train_id": "5N98",
    "forecasts": [{
        "tiploc": "CRFDSPR",
        "forecast_arrival": "10:38",
        "forecast_departure": "10:45",
        "platform": "1",
        "delay_minutes": 7
    }],
    "delay": 7
}

print("Posting forecast update...")
forecast_response = requests.post(
    f"{API_BASE}/api/trains/forecast_update",
    json=forecast_payload,
    headers={"Content-Type": "application/json"}
)
print("Forecast Response:", forecast_response.status_code, forecast_response.text)