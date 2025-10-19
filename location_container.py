import os
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

# Create the Flask application
app = Flask(__name__, 
            static_folder='web/static',
            template_folder='web/templates')

# Configuration
API_SERVER_URL = os.environ.get('API_SERVER_URL', 'http://localhost:5000')
LOCATION = os.environ.get('LOCATION', '')  # Default empty, should be provided via env var

@app.route('/')
def home():
    """Home page showing schedules for this specific location."""
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    # Fetch data from API server for this location
    try:
        response = requests.get(
            f"{API_SERVER_URL}/api/schedules?location={LOCATION}&date_str={date_str}"
        )
        if response.status_code != 200:
            return render_template(
                'location_error.html', 
                error=f"API error: {response.status_code}",
                location=LOCATION
            )
        
        data = response.json()
        return render_template(
            'location.html',
            location=LOCATION,
            date=date_str,
            schedules=data['schedules'],
            associations=data['associations']
        )
    except Exception as e:
        return render_template(
            'location_error.html',
            error=str(e),
            location=LOCATION
        )

@app.route('/api/today')
def today_data():
    """API endpoint that returns today's data for this location."""
    date_str = datetime.now().strftime('%Y-%m-%d')
    try:
        response = requests.get(
            f"{API_SERVER_URL}/api/schedules?location={LOCATION}&date_str={date_str}"
        )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint."""
    if not LOCATION:
        return jsonify({"status": "error", "message": "No location configured"}), 500
    return jsonify({"status": "healthy", "location": LOCATION})

if __name__ == '__main__':
    if not LOCATION:
        print("ERROR: No location configured. Set the LOCATION environment variable.")
        exit(1)
    
    print(f"Starting location service for {LOCATION}")
    print(f"API server configured at: {API_SERVER_URL}")
    
    app.run(host='0.0.0.0', port=5001, debug=True)