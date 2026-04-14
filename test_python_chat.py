import requests
import json

python_url = "http://localhost:8001/client-chat"
internal_secret = "civicora-internal-secret"

payload = {
    "message": "Hello, how are you?",
    "all_projects": [
        {
            "project_id": "1",
            "project_name": "Test Project",
            "status": "PLANNING",
            "budget": 100000,
            "progress_percentage": 0,
            "start_date": "2026-04-14T00:00:00Z",
            "end_date": "2026-12-14T00:00:00Z",
            "location": "Chennai"
        }
    ]
}

headers = {
    "X-Internal-Key": internal_secret,
    "Content-Type": "application/json"
}

try:
    response = requests.post(python_url, json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
