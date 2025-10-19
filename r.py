import requests

# === Configuration ===
API_BASE = "http://localhost:5000"
API_KEY = "AIL7DYIPyGKQVXNzCdjl5OvciXTdVzGBZ8R5TMUFFkbm8rmG2J7dCrmGNIRPKheWIHkzKA7J966e2VWPNYPX2eOrHPf2JMkj0pLN0p1YnhStKGEHmH1ly1LBu1IKpg8U"  # Replace with your actual key

step_payload = {
    "headcode": "5N98",
    "tiploc": "CRFDSPR",
    "event_type": "step",
    "from_berth": "BT987",
    "to_berth": "CRFDSPR",
    "actual_step_time": "2025-05-30T10:36:00Z",
    "calculated_event_time": "2025-05-30T10:36:00Z"
}

print("Posting realtime step update...")
step_response = requests.post(
    f"{API_BASE}/api/trains/realtime_update",
    json=step_payload,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
)
print("Step Response:", step_response.status_code, step_response.text)