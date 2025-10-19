import logging
from flask import jsonify, request, render_template
from datetime import datetime
from flask_cors import CORS

# Import configuration first
import config

from app import app, db
from models import ParsedFile, BasicSchedule, ScheduleLocation, Association

# Set up the area of interest from config
app.config['AREA_OF_INTEREST'] = config.AREA_OF_INTEREST

# Enable CORS using config settings
CORS(app, resources=config.CORS_CONFIG)

# Create all tables
with app.app_context():
    db.create_all()
    db.session.commit()  # Ensure tables are committed to the database

# Import CIF processor and ActiveTrains system
from cif_parser import process_cif_files
from active_trains import initialize_active_trains, get_active_trains_manager
from scheduler import start_scheduler

# Process CIF files and initialize ActiveTrains synchronously
with app.app_context():
    logging.info("Processing CIF files before server startup...")
    process_cif_files()
    logging.info("CIF processing completed, initializing ActiveTrains...")
    initialize_active_trains()
    logging.info("ActiveTrains initialization completed")

# Start the background scheduler for railway day rollover and CIF processing
scheduler = start_scheduler()
logging.info("Background scheduler started for railway day operations")

# API Routes
@app.route("/")
def root():
    """API server root - returns HTML interface or JSON based on Accept header."""
    
    # Check if browser is requesting HTML
    if 'text/html' in request.headers.get('Accept', ''):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>UK Railway Timetable API Server</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-left: 4px solid #007cba; }
                .method { background: #007cba; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; }
                .auth { background: #ff6b6b; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; }
                code { background: #e8e8e8; padding: 2px 5px; border-radius: 3px; }
                h1 { color: #333; }
                h2 { color: #007cba; border-bottom: 2px solid #007cba; padding-bottom: 5px; }
            </style>
        </head>
        <body>
            <h1>🚄 UK Railway Timetable API Server</h1>
            <p><strong>Version:</strong> 2.0.0 | <strong>Status:</strong> Online | <strong>Active Trains:</strong> 1,039</p>
            
            <h2>Core Timetable Endpoints</h2>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/schedules</code>
                <p>Get train schedules for a specific location and date</p>
                <strong>Example:</strong> <code>/api/schedules?location={list(config.AREA_OF_INTEREST)[0]}&date_str=2025-05-30</code>
            </div>
            
            <div class="endpoint">
                <span class="method">POST</span> <code>/api/platform_docker</code>
                <p>Get platform visualization data with train events timeline</p>
                <strong>Body:</strong> <code>{"location": "CHRX", "date": "2025-05-30"}</code>
            </div>
            
            <div class="endpoint">
                <span class="method">POST</span> <code>/api/train_graph_schedules</code>
                <p>Get schedules for multiple locations (train graph view)</p>
                <strong>Body:</strong> <code>{"locations": ["CHRX", "WLOE"], "date": "2025-05-30"}</code>
            </div>
            
            <h2>Active Trains System</h2>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/active_trains</code>
                <p>Get all active trains (external format for system integration)</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/active_trains/list</code>
                <p>Get paginated list of active trains</p>
                <strong>Example:</strong> <code>/api/active_trains/list?limit=50&offset=0</code>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/active_trains/train/&lt;uid&gt;</code>
                <p>Get detailed information about a specific train</p>
                <strong>Example:</strong> <code>/api/active_trains/train/A12345</code>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/active_trains/location/&lt;tiploc&gt;</code>
                <p>Get all trains passing through a specific location</p>
                <strong>Example:</strong> <code>/api/active_trains/location/CHRX</code>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/active_trains/status</code>
                <p>Active trains system status and health monitoring</p>
            </div>
            
            <h2>External Integration Endpoints</h2>
            
            <div class="endpoint">
                <span class="method">POST</span> <span class="auth">AUTH</span> <code>/api/realtime_update</code>
                <p>Submit real-time movement updates (requires API key)</p>
            </div>
            
            <div class="endpoint">
                <span class="method">POST</span> <code>/api/trains/forecast_update</code>
                <p>Submit forecast updates from external systems</p>
            </div>
            
            <h2>System Information</h2>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/health</code>
                <p>Health check endpoint for monitoring</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/db_status</code>
                <p>Database status with schedule and association counts</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/api/reset_database</code>
                <p>Reset database - removes all schedule and association data</p>
                <div class="alert alert-warning">⚠️ This will delete ALL data from the database</div>
            </div>
            
            <p><strong>Location Codes:</strong> CHRX=Charing Cross, WLOE=Waterloo East, CANONST=Cannon Street</p>
            <p><strong>Date Format:</strong> YYYY-MM-DD (e.g., 2025-05-30)</p>
            
            <hr>
            <p style="color: #666; font-size: 14px;">
                For JSON API documentation: <a href="/?format=json">View JSON Format</a> | 
                <a href="/debug">Debug Interface</a> | 
                <a href="/logs">API Logs</a> | 
                System serving live UK railway CIF data
            </p>
        </body>
        </html>
        """
    
    # Return JSON for API clients
    return jsonify({
        "service": "UK Railway Timetable API Server",
        "description": "Pure data API for railway schedule and train tracking information",
        "version": "2.0.0",
        
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/schedules",
                "description": "Get train schedules for a specific location and date",
                "example": "/api/schedules?location=CHRX&date=2025-05-30",
                "parameters": ["location (required)", "date (required)", "platform (optional)", "line (optional)", "path (optional)"]
            },
            {
                "method": "POST", 
                "path": "/api/platform_docker",
                "description": "Get platform visualization data with train events",
                "body_example": '{"location": "CHRX", "date": "2025-05-30", "page": 1, "per_page": 10}',
                "returns": "Platform layout with train arrival/departure times"
            },
            {
                "method": "POST",
                "path": "/api/train_graph_schedules", 
                "description": "Get schedules for multiple locations (train graph view)",
                "body_example": '{"locations": ["CHRX", "WLOE"], "date": "2025-05-30"}',
                "returns": "Combined schedule data for visualization"
            },
            {
                "method": "GET",
                "path": "/api/active_trains",
                "description": "Get all active trains (external format)",
                "example": "/api/active_trains",
                "returns": "Complete active trains data for external systems"
            },
            {
                "method": "GET", 
                "path": "/api/active_trains/status",
                "description": "Active trains system status",
                "returns": "System health and train count statistics"
            },
            {
                "method": "GET",
                "path": "/api/active_trains/list",
                "description": "Get paginated list of active trains",
                "example": "/api/active_trains/list?limit=50&offset=0",
                "returns": "Paginated list of active trains with summary information"
            },
            {
                "method": "GET",
                "path": "/api/active_trains/train/<uid>",
                "description": "Get detailed information about a specific train",
                "example": "/api/active_trains/train/A12345",
                "returns": "Complete train details including schedule and associations"
            },
            {
                "method": "GET",
                "path": "/api/active_trains/location/<tiploc>",
                "description": "Get all trains passing through a specific location",
                "example": "/api/active_trains/location/CHRX",
                "returns": "List of trains at the specified location"
            },
            {
                "method": "POST",
                "path": "/api/active_trains/refresh",
                "description": "Refresh active trains data",
                "parameters": ["date (optional, YYYY-MM-DD format)"],
                "returns": "Refresh status and train count"
            },
            {
                "method": "GET",
                "path": "/api/db_status", 
                "description": "Database status with schedule and association counts",
                "returns": "Statistics about loaded timetable data"
            },
            {
                "method": "GET",
                "path": "/health",
                "description": "Health check endpoint for monitoring", 
                "returns": "Server status and uptime information"
            },
            {
                "method": "POST",
                "path": "/api/trains/forecast_update",
                "description": "Submit forecast updates from external systems",
                "authentication": "X-API-Key header required",
                "body": "Darwin-format forecast data"
            },
            {
                "method": "POST", 
                "path": "/api/realtime_update",
                "description": "Submit real-time movement updates",
                "authentication": "X-API-Key header required",
                "body": "TD feed format movement data"  
            }
        ],
        
        "parameter_guide": {
            "location/tiploc": "4-letter location code (CHRX=Charing Cross, WLOE=Waterloo East)",
            "date": "ISO date format YYYY-MM-DD (e.g., 2025-05-30)", 
            "uid": "Unique train identifier from CIF data (e.g., A12345)",
            "platform": "Platform number or identifier (1, 2, A, B)",
            "limit": "Maximum records to return for pagination",
            "offset": "Records to skip for pagination"
        }
    })




    
@app.route("/api-info")
def api_info():
    """Endpoint that returns API information."""
    return jsonify({
        "name": "UK Railway CIF Data API",
        "description": "API for accessing UK railway schedule information from CIF files",
        "version": "1.0.0",
        "endpoints": {
            "schedules": "/api/schedules?location=TIPLOC&date_str=YYYY-MM-DD",
            "health": "/health"
        }
    })

@app.route("/debug")
def debug_interface():
    """Debug interface for testing forecast and actual updates."""
    return render_template('debug.html')

@app.route("/train_schedule")
def train_schedule_viewer():
    """Train schedule viewer for detailed schedule inspection."""
    return render_template('train_schedule.html')

@app.route("/logs")
def logs_viewer():
    """API logs viewer for monitoring system activity."""
    return render_template('logs.html')

@app.route("/health")
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok", "timestamp": str(datetime.now())})

@app.route("/api/reset_database")
def reset_database_endpoint():
    """Reset database tables - removes all schedule and association data."""
    try:
        from reset_db import reset_database
        result = reset_database()
        if result:
            return jsonify({
                "status": "success", 
                "message": "Database reset completed successfully",
                "timestamp": str(datetime.now())
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Database reset failed",
                "timestamp": str(datetime.now())
            }), 500
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Database reset failed: {str(e)}",
            "timestamp": str(datetime.now())
        }), 500

@app.route("/api/test_railway_rollover")
def test_railway_rollover():
    """Test endpoint to manually trigger railway day rollover for testing purposes."""
    try:
        from active_trains import get_active_trains_manager, get_london_now
        
        manager = get_active_trains_manager()
        london_now = get_london_now()
        
        # Get current state before rollover
        before_today_count = len(manager.trains)
        before_tomorrow_count = len(manager.trains_tomorrow)
        before_railway_date = manager.current_railway_date
        
        # Perform rollover
        manager.promote_tomorrow_trains()
        
        # Get state after rollover
        after_today_count = len(manager.trains)
        after_tomorrow_count = len(manager.trains_tomorrow)
        after_railway_date = manager.current_railway_date
        
        return jsonify({
            "status": "success",
            "message": "Railway day rollover test completed",
            "london_time": london_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
            "before_rollover": {
                "railway_date": str(before_railway_date),
                "today_trains": before_today_count,
                "tomorrow_trains": before_tomorrow_count
            },
            "after_rollover": {
                "railway_date": str(after_railway_date),
                "today_trains": after_today_count,
                "tomorrow_trains": after_tomorrow_count
            },
            "timestamp": str(datetime.now())
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Railway rollover test failed: {str(e)}",
            "timestamp": str(datetime.now())
        }), 500

# Import and register API routes
from api import api_bp
app.register_blueprint(api_bp, url_prefix='/api')

# Import and register consolidated ActiveTrains API
from api_active_trains import active_trains_bp
app.register_blueprint(active_trains_bp, url_prefix='/api/trains')

# Note: Core API endpoints now consolidated in api.py

if __name__ == "__main__":
    # Start server
    app.run(host="0.0.0.0", port=5000, debug=True)