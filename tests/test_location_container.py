import os
import sys

# Set required environment variables
os.environ['API_SERVER_URL'] = 'http://localhost:5000'

if len(sys.argv) > 1:
    # Use location from command line argument if provided
    os.environ['LOCATION'] = sys.argv[1]
else:
    # Default to CHRX if no argument provided
    os.environ['LOCATION'] = 'CHRX'

print(f"Testing location container for {os.environ['LOCATION']}")
print(f"Make sure the main server is running on {os.environ['API_SERVER_URL']}")

# Import and run the app
from location_container import app
app.run(host='0.0.0.0', port=5001, debug=True)