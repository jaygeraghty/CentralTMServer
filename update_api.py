"""
Update API endpoints to use the new STP utility functions.

This script demonstrates how to update the existing API endpoints to use
the new modular STP indicator handling functions.
"""

from datetime import datetime
from flask import request, jsonify, Blueprint
import logging

from app import db
from apply_stp_changes import get_schedules_with_stp_applied

# Configure logging
logger = logging.getLogger(__name__)

# Example of updating the get_schedules API endpoint
def updated_get_schedules_endpoint():
    """
    Get schedules for a specific location and date with proper STP handling.
    
    Query Parameters:
        location: TIPLOC code of the location
        date_str: Date in YYYY-MM-DD format
        platform: Optional platform code to filter by
        line: Optional line code to filter by
        path: Optional path code to filter by
        
    Returns:
        JSON response with schedules after STP indicator processing
    """
    try:
        # Get query parameters
        location = request.args.get('location')
        date_str = request.args.get('date_str')
        platform = request.args.get('platform')
        line = request.args.get('line')
        path = request.args.get('path')
        
        if not location or not date_str:
            return jsonify({"error": "Missing required parameters. Use location and date_str"}), 400
        
        # Parse date
        try:
            search_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Get schedules with STP indicators applied
        schedules = get_schedules_with_stp_applied(
            search_date=search_date,
            location=location,
            platform=platform,
            line=line,
            path=path
        )
        
        # Convert to response format
        schedule_list = []
        for schedule in schedules:
            # Skip cancelled schedules if desired, or include with cancelled flag
            locations = []
            
            # Format locations
            for loc in schedule.get('locations', []):
                location_dict = {
                    'sequence': loc['sequence'],
                    'tiploc': loc['tiploc'],
                    'location_type': loc['location_type'],
                    'arr': loc['arr'],
                    'dep': loc['dep'],
                    'pass_time': loc['pass_time'],
                    'public_arr': loc['public_arr'],
                    'public_dep': loc['public_dep'],
                    'platform': loc['platform'],
                    'line': loc['line'],
                    'path': loc['path'],
                    'activity': loc['activity']
                }
                locations.append(location_dict)
                
            schedule_dict = {
                'uid': schedule['uid'],
                'stp_indicator': schedule['effective_stp_indicator'],  # Use effective indicator
                'train_status': schedule['train_status'],
                'train_category': schedule['train_category'],
                'train_identity': schedule['train_identity'],
                'service_code': schedule['service_code'],
                'power_type': schedule['power_type'],
                'speed': schedule['speed'],
                'operating_chars': schedule['operating_chars'],
                'days_run': schedule['days_run'],
                'runs_from': schedule['runs_from'].strftime("%Y-%m-%d") if schedule['runs_from'] else None,
                'runs_to': schedule['runs_to'].strftime("%Y-%m-%d") if schedule['runs_to'] else None,
                'is_cancelled': schedule.get('is_cancelled', False),
                'is_overlay': schedule.get('is_overlay', False),
                'locations': locations
            }
            schedule_list.append(schedule_dict)
        
        # Return formatted response
        return jsonify({
            "date": date_str,
            "location": location,
            "platform": platform,
            "line": line,
            "path": path,
            "schedules": schedule_list
        })
        
    except Exception as e:
        logger.exception(f"Error processing get_schedules request: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Example of how to register this updated endpoint
def register_updated_endpoints(app):
    """
    Register the updated API endpoints with the Flask app.
    
    Args:
        app: Flask application
    """
    # Create or get the API blueprint
    api_bp = Blueprint('api', __name__)
    
    # Register the updated endpoint
    api_bp.route("/schedules_v2")(updated_get_schedules_endpoint)
    
    # Register other endpoints as needed
    
    # Register the blueprint with the app
    app.register_blueprint(api_bp, url_prefix='/api')