"""
Consolidated Active Trains API - All endpoints in one file.
Provides both internal management and external integration endpoints.
"""

import logging
from typing import Dict, List, Optional, Any
from flask import Blueprint, jsonify, request, current_app, make_response
from datetime import datetime, date
from functools import wraps

from active_trains import (
    ActiveTrain, get_active_trains_manager, initialize_active_trains,
    apply_forecast_update, find_active_train_by_headcode_and_detection
)
from time_utils import cif_time_to_iso_datetime, parse_cif_time

# Configure logging with file rotation
from log_manager import setup_api_logging, get_log_manager
logger = setup_api_logging()

# Hook for log rotation check on each request
def check_log_rotation():
    get_log_manager().check_and_rotate_by_lines()

# Import configuration
import config

# Create Blueprint for all active trains endpoints
active_trains_bp = Blueprint('active_trains', __name__)

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {config.API_KEY}":
            return jsonify({"error": "unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated

# ============================================================================
# EXTERNAL INTEGRATION ENDPOINTS (for external services)
# ============================================================================

@active_trains_bp.route('/active_trains', methods=['GET'])
def get_active_trains_for_external():
    """
    External API endpoint that provides active trains data in the format
    required by the ARS Prediction Cycle system.
    
    Returns:
        JSON array of ActiveTrain objects with complete schedule data
    """
    try:
        # Get the active trains manager
        manager = get_active_trains_manager()
        
        # Convert our active trains to the external format
        external_trains = []
        
        for uid, train in manager.trains.items():
            # Build the external train object
            train_data = {
                "train_id": train.headcode,
                "uid": train.uid,
                "headcode": train.headcode,
                "last_step_time": train.last_step_time.isoformat() if train.last_step_time else None,
                "schedule_start_date": date.today().strftime('%Y-%m-%d'),
                "current_berth_id": train.berth,
                "current_berth_entry_time": train.current_berth_entry_time.isoformat() if train.current_berth_entry_time else None,
                "previous_berth": train.previous_berth,
                "current_location": train.current_location,
                "detected": train.detected,
                "terminated": train.terminated,
                "cancelled": train.cancelled
            }
            
            # Add schedule data if available
            if train.schedule:
                schedule_data = {
                    "uid": train.schedule.uid,
                    "headcode": train.schedule.train_identity,
                    "service_code": train.schedule.service_code or "00000000",
                    "locations": [],
                    "start_date": train.schedule.runs_from.isoformat() if train.schedule.runs_from else date.today().isoformat(),
                    "end_date": train.schedule.runs_to.isoformat() if train.schedule.runs_to else date.today().isoformat(),
                    "days_run": train.schedule.days_run or "1111111",
                    "train_status": train.schedule.train_status or "P",
                    "train_category": train.schedule.train_category or "XX"
                }
                
                # Convert schedule locations to external format
                for location in train.schedule.locations:
                    location_data = {
                        "tiploc": location.tiploc,
                        "recurrence": location.recurrence_value,
                        "platform": location.platform or "",
                        "path": location.path or "",
                        "line": location.line or "",
                        "activities": location.activity or "",
                        "engineering_allowance": location.engineering_allowance or "",
                        "pathing_allowance": location.pathing_allowance or "",
                        "performance_allowance": location.performance_allowance or ""
                    }
                    
                    # Format times as ISO-8601 datetime strings using helper functions
                    today_str = date.today().strftime('%Y-%m-%d')
                    
                    # Debug: Log the raw time values to see what we're working with
                    if location.arr_time:
                        iso_time = cif_time_to_iso_datetime(location.arr_time, today_str)
                        if iso_time:
                            location_data["arrival_time"] = iso_time
                        else:
                            # Fallback: if ISO conversion fails, try direct time format
                            location_data["arrival_time"] = f"{today_str}T{location.arr_time}"
                    
                    if location.dep_time:
                        iso_time = cif_time_to_iso_datetime(location.dep_time, today_str)
                        if iso_time:
                            location_data["departure_time"] = iso_time
                        else:
                            # Fallback: if ISO conversion fails, try direct time format
                            location_data["departure_time"] = f"{today_str}T{location.dep_time}"
                    
                    if location.public_arr:
                        iso_time = cif_time_to_iso_datetime(location.public_arr, today_str)
                        if iso_time:
                            location_data["public_arrival"] = iso_time
                        else:
                            # Fallback: if ISO conversion fails, try direct time format
                            location_data["public_arrival"] = f"{today_str}T{location.public_arr}"
                    
                    if location.public_dep:
                        iso_time = cif_time_to_iso_datetime(location.public_dep, today_str)
                        if iso_time:
                            location_data["public_departure"] = iso_time
                        else:
                            # Fallback: if ISO conversion fails, try direct time format
                            location_data["public_departure"] = f"{today_str}T{location.public_dep}"
                    
                    if location.pass_time:
                        iso_time = cif_time_to_iso_datetime(location.pass_time, today_str)
                        if iso_time:
                            location_data["pass_time"] = iso_time
                        else:
                            # Fallback: if ISO conversion fails, try direct time format
                            location_data["pass_time"] = f"{today_str}T{location.pass_time}"
                    
                    # Add sequence number to preserve order and support duplicate TIPLOCs
                    location_data["sequence"] = location.sequence
                    location_data["arr_time"] = location.arr_time
                    location_data["dep_time"] = location.dep_time
                    location_data["pass_time"] = location.pass_time
                    location_data["public_arr"] = location.public_arr
                    location_data["public_dep"] = location.public_dep
                    
                    # Add predicted fields (will be None if no predictions available)
                    location_data["pred_arr"] = location.pred_arr
                    location_data["pred_dep"] = location.pred_dep
                    location_data["pred_pass"] = location.pred_pass
                    
                    # Add actual times from TD system real-time updates
                    location_data["actual_arr"] = location.actual_arr
                    location_data["actual_dep"] = location.actual_dep
                    location_data["actual_pass"] = location.actual_pass
                    
                    # Add smart prediction fields from AI prediction cycle
                    location_data["smart_pred_arr"] = location.smart_pred_arr
                    location_data["smart_pred_dep"] = location.smart_pred_dep
                    location_data["smart_pred_pass"] = location.smart_pred_pass
                    location_data["smart_pred_confidence"] = location.smart_pred_confidence
                    location_data["smart_pred_delay_min"] = location.smart_pred_delay_min
                    if location.smart_pred_timestamp:
                        location_data["smart_pred_timestamp"] = location.smart_pred_timestamp.isoformat()
                    else:
                        location_data["smart_pred_timestamp"] = None
                    
                    # Add associations at this location (if any)
                    if hasattr(location, 'associations') and location.associations:
                        location_data["associations"] = location.associations
                    else:
                        location_data["associations"] = {}
                    location_data["pred_delay_min"] = location.pred_delay_min
                    location_data["forecast_platform"] = location.forecast_platform
                    
                    # Append to list to preserve duplicates
                    schedule_data["locations"].append(location_data)
                
                
                train_data["schedule"] = schedule_data
            
            # Add forecast locations using prediction data from schedule locations
            train_data["forecast_locations"] = []
            
            # Iterate through all schedule locations and include those with prediction data
            if train.schedule and train.schedule.locations:
                for location in train.schedule.locations:
                    # Check if this location has any prediction data
                    if (location.pred_arr or location.pred_dep or location.pred_pass or 
                        location.pred_delay_min is not None):
                        
                        forecast_data = {
                            "location_id": location.tiploc,
                            "arr_time": location.pred_arr or "",
                            "dep_time": location.pred_dep or "", 
                            "pass_time": location.pred_pass or "",
                            "platform": location.forecast_platform or location.platform or "",
                            "delay_minutes": location.pred_delay_min
                        }
                        train_data["forecast_locations"].append(forecast_data)
            
            external_trains.append(train_data)
        
        logger.info(f"Serving {len(external_trains)} active trains to external API")

        
            
        return jsonify(external_trains)
        
    except Exception as e:
        logger.exception(f"Error serving active trains to external API: {str(e)}")
        return jsonify({
            "error": "Failed to retrieve active trains",
            "message": str(e)
        }), 500

@active_trains_bp.route('/status', methods=['GET'])
def get_active_trains_status():
    """
    Status endpoint for monitoring the active trains API.
    
    Returns:
        JSON object with system status and train counts
    """
    try:
        manager = get_active_trains_manager()
        
        status = {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "total_trains": len(manager.trains),
            "train_ids": list(manager.trains.keys()),
            "api_version": "1.0"
        }
        
        return jsonify(status)
        
    except Exception as e:
        logger.exception(f"Error getting active trains status: {str(e)}")
        return jsonify({
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }), 500


@active_trains_bp.route('/forecast_update', methods=['POST', 'OPTIONS'])
def update_forecast():
    """
    Accepts a forecast update payload and applies it to the relevant ActiveTrain.
    Includes logging for all request methods and headers for debugging.
    """
    check_log_rotation()  # Check for log rotation on each request
    
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
        return response

    try:
        from active_trains import is_server_ready, queue_update
        
        payload = request.get_json(force=True)
        
        # Check if server is ready
        if not is_server_ready():
            uid = payload.get("uid", "unknown")
            train_id = payload.get("train_id", "unknown")
            queue_update('forecast', payload)
            logger.info(f"Server not ready - queued forecast update for {train_id}/{uid}")
            return jsonify({"status": "queued", "reason": "server not ready"}), 202
        
        logger.info(f"Payload received: {payload}")
        manager = get_active_trains_manager()

        uid = payload.get("uid")
        train_id = payload.get("train_id")
        forecasts = payload.get("forecasts", [])

        if not forecasts:
            logger.warning("Forecast update missing forecast list")
            return jsonify({"status": "ignored", "reason": "no forecasts"}), 202

        # Grab first location for logging purposes
        f = forecasts[0]
        tiploc = f.get("tiploc")
        arr_et = f.get("forecast_arrival")
        dep_et = f.get("forecast_departure")
        pass_et = f.get("forecast_pass")
        platform = f.get("platform")

        if apply_forecast_update(manager, payload):
            train = manager.get_train_by_uid(uid) or manager.get_train_by_headcode(train_id)
            headcode = train.headcode if train else "unknown"
            forecast_time = arr_et or dep_et or pass_et or "unknown"
            forecast_type = "arr" if arr_et else ("dep" if dep_et else ("pass" if pass_et else "unknown"))
            logger.info(f"Forecast update: {headcode}/{uid} at {tiploc} forecast {forecast_type} {forecast_time}" +
                        (f" platform {platform}" if platform else ""))
            return jsonify({"status": "ok"}), 200
        else:
            logger.warning(f"Forecast update ignored: no matching train for {uid} at {tiploc}")
            return jsonify({"status": "ignored", "reason": "not matched"}), 202

    except Exception as e:
        logger.exception("Forecast update failed")
        return jsonify({"status": "error", "message": str(e)}), 500


@active_trains_bp.route("/realtime_update", methods=["POST", "OPTIONS"])
def realtime_update():
    check_log_rotation()  # Check for log rotation on each request
    
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
        return response
    
    from active_trains import is_server_ready, queue_update
    
    data = request.get_json()
    
    if not data:
        return jsonify({"status": "error", "message": "No JSON data provided"}), 400

    # Check if server is ready
    if not is_server_ready():
        headcode = data.get("headcode", "unknown")
        tiploc = data.get("tiploc", "unknown")
        queue_update('realtime', data)
        logger.info(f"Server not ready - queued realtime update for {headcode} at {tiploc}")
        return jsonify({"status": "queued", "reason": "server not ready"}), 202

    headcode = data.get("headcode")
    tiploc = data.get("tiploc")
    event_type = data.get("event_type")
    from_berth = data.get("from_berth")
    to_berth = data.get("to_berth")

    actual_step_time_str = data.get("actual_step_time")
    calculated_event_time_str = data.get("calculated_event_time")
    
    if actual_step_time_str:
        actual_step_time = datetime.fromisoformat(actual_step_time_str.replace("Z", "+00:00"))
        # Convert UTC to London time
        from active_trains import to_london_tz
        actual_step_time = to_london_tz(actual_step_time)
    else:
        from active_trains import get_london_now
        actual_step_time = get_london_now()
        
    if calculated_event_time_str:
        # Parse as UTC timestamp - don't convert to London time here
        # The apply_realtime_update method will handle timezone conversion internally
        calculated_event_time = datetime.fromisoformat(calculated_event_time_str.replace("Z", "+00:00"))
    else:
        calculated_event_time = actual_step_time
    logger.info(f"We are setting the calculated event time to {calculated_event_time}, with the actual time being {actual_step_time}")
    manager = get_active_trains_manager()

    # Find all trains matching headcode
    all_matching = [t for t in manager.trains.values() if t.headcode == headcode]
    activated_trains = [t for t in all_matching if t.detected]
    
    # Special handling for delete events - try alternative lookups if needed
    if event_type == "delete":
        logger.info(f"Processing delete event for {headcode} at {tiploc}")
        logger.info(f"Found {len(all_matching)} total trains, {len(activated_trains)} activated trains")
    
    if len(activated_trains) == 0:
        # No activated trains - use detection logic
        train = detect_train_if_needed(manager, headcode, from_berth, to_berth, actual_step_time)
        if event_type == "delete" and not train:
            # For delete events, try broader search if detection fails
            train = manager.get_train_by_headcode(headcode)
            if train:
                logger.info(f"Delete event: found train via headcode lookup {headcode} (UID: {train.uid})")
    elif len(activated_trains) == 1:
        # Exactly one activated train - use it
        train = activated_trains[0]
        logger.debug(f"Real-time update: using single activated train {headcode} (UID: {train.uid})")
    else:
        # Multiple activated trains - resolve using location
        train = find_active_train_by_headcode_and_detection(headcode, from_berth, activated_trains)
    
    if not train:
        if event_type == "delete":
            logger.warning(f"Delete event failed: no train found for {headcode} at {tiploc}")
        else:
            logger.warning(f"Realtime update: no matching train found for {headcode} {from_berth}->{to_berth}")
        return jsonify({"status": "train not found"}), 404
    
    # Log successful train selection for delete events
    if event_type == "delete":
        logger.info(f"Delete event: Found train {train.headcode} (UID: {train.uid}) for deletion")

    # Log the realtime update before applying it
    time_str = calculated_event_time.strftime("%H:%M:%S")
    if event_type == "step":
        logger.info(f"Realtime update: {headcode} stepped {from_berth}->{to_berth} at {time_str}")
    elif event_type in ["arrival", "departure", "pass"]:
        logger.info(f"Realtime update: {headcode} {event_type} at {tiploc} at {time_str}")
    elif event_type == "delete":
        logger.info(f"Realtime update: {headcode} deleted at {tiploc}")
    else:
        logger.info(f"Realtime update: {headcode} {event_type} at {tiploc} at {time_str}")

    train.apply_realtime_update(
        tiploc=tiploc,
        timestamp=calculated_event_time,
        event_type=event_type,
        from_berth=from_berth,
        to_berth=to_berth
    )

    return jsonify({"status": "ok"})

# ============================================================================
# INTERNAL MANAGEMENT ENDPOINTS (for system management)
# ============================================================================

@active_trains_bp.route('/refresh', methods=['POST'])
def refresh_active_trains():
    """Refresh the ActiveTrains system with current data."""
    try:
        date_str = request.args.get('date')
        target_date = None
        
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": f"Invalid date format: {date_str}. Use YYYY-MM-DD."
                }), 400
        
        manager = get_active_trains_manager()
        manager.refresh_data(target_date)
        
        return jsonify({
            "success": True,
            "message": f"Refreshed active trains data for {target_date}",
            "train_count": len(manager.trains)
        })
    except Exception as e:
        logger.exception(f"Error refreshing active trains: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@active_trains_bp.route("/smart_predictions", methods=["POST"])
def update_smart_predictions():
    """
    Accept smart predictions from the AI prediction cycle.
    
    Expected JSON payload:
    {
        "uid": "P12345",
        "predictions": [
            {
                "tiploc": "GRVPK",
                "sequence": 5,
                "smart_pred_arr": "14:25:30",
                "smart_pred_dep": "14:26:00", 
                "smart_pred_pass": null,
                "smart_pred_confidence": 0.85,
                "smart_pred_delay_min": 3
            }
        ]
    }
    """
    check_log_rotation()
    
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON data provided"}), 400

    uid = data.get("uid")
    predictions = data.get("predictions", [])
    
    if not uid or not predictions:
        return jsonify({"status": "error", "message": "UID and predictions required"}), 400

    manager = get_active_trains_manager()
    train = manager.get_train_by_uid(uid)
    
    if not train or not train.schedule:
        logger.warning(f"Smart predictions ignored: no train found for UID {uid}")
        return jsonify({"status": "ignored", "reason": "train not found"}), 202

    updated_locations = 0
    from active_trains import get_london_now
    london_now = get_london_now()
    
    for pred_data in predictions:
        tiploc = pred_data.get("tiploc")
        sequence = pred_data.get("sequence")
        
        if not tiploc:
            continue
            
        # Find the location to update
        target_location = None
        if sequence is not None:
            target_location = train.schedule.get_location_by_sequence(sequence)
        else:
            # Fallback: find by TIPLOC (first occurrence)
            target_location = train.schedule.get_first_location_at_tiploc(tiploc)
        
        if target_location:
            # Update smart prediction fields
            target_location.smart_pred_arr = pred_data.get("smart_pred_arr")
            target_location.smart_pred_dep = pred_data.get("smart_pred_dep")
            target_location.smart_pred_pass = pred_data.get("smart_pred_pass")
            target_location.smart_pred_confidence = pred_data.get("smart_pred_confidence")
            target_location.smart_pred_delay_min = pred_data.get("smart_pred_delay_min")
            target_location.smart_pred_timestamp = london_now
            
            updated_locations += 1
    
    logger.info(f"Smart predictions updated: {train.headcode}/{uid} - {updated_locations} locations")
    return jsonify({
        "status": "ok", 
        "updated_locations": updated_locations,
        "train": train.headcode
    }), 200

@active_trains_bp.route('/list', methods=['GET'])
def list_active_trains():
    """Get a list of all active trains."""
    try:
        # Get parameters
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', 0, type=int)
        
        manager = get_active_trains_manager()
        trains = list(manager.trains.values())
        
        # Apply pagination if requested
        total_count = len(trains)
        if limit:
            trains = trains[offset:offset+limit]
        
        # Convert train data to serializable format
        train_data = []
        for train in trains:
            train_data.append({
                "uid": train.uid,
                "headcode": train.headcode,
                "berth": train.berth,
                "last_location": train.last_location,
                "delay": train.delay,
                "forecast_delay": train.forecast_delay,
                "forecast_delay_at": train.forecast_delay_at.isoformat() if train.forecast_delay_at else None,
                "schedule_id": train.schedule.id if train.schedule else None,
                "stp_indicator": train.schedule.stp_indicator if train.schedule else None,
                "category": train.schedule.train_category if train.schedule else None,
                "location_count": len(train.get_all_locations()),
                "has_associations": True if train.associations else False
            })
        
        return jsonify({
            "success": True,
            "total_count": total_count,
            "returned_count": len(train_data),
            "offset": offset,
            "limit": limit if limit else total_count,
            "trains": train_data
        })
    except Exception as e:
        logger.exception(f"Error listing active trains: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@active_trains_bp.route('/train/<uid>', methods=['GET'])
def get_train_details(uid):
    """Get detailed information about a specific train by UID."""
    try:
        manager = get_active_trains_manager()
        train = manager.get_train_by_uid(uid)
        
        if not train:
            return jsonify({
                "success": False,
                "error": f"No active train found with UID: {uid}"
            }), 404
        
        # Convert schedule locations to serializable format
        locations = []
        if train.schedule:
            for loc in train.schedule.locations:
                locations.append({
                    "sequence": loc.sequence,
                    "tiploc": loc.tiploc,
                    "location_type": loc.location_type,
                    "arr_time": loc.arr_time,
                    "dep_time": loc.dep_time,
                    "pass_time": loc.pass_time,
                    "public_arr": loc.public_arr,
                    "public_dep": loc.public_dep,
                    "platform": loc.platform,
                    "line": loc.line,
                    "path": loc.path,
                    "activity": loc.activity,
                    "actual_arr": loc.actual_arr,
                    "actual_dep": loc.actual_dep,
                    "actual_platform": loc.actual_platform,
                    "delay_minutes": (loc.delay_seconds or 0) / 60,  # Convert seconds to minutes for API
                    "forecast_arr": loc.forecast_arr,
                    "forecast_dep": loc.forecast_dep,
                    "forecast_platform": loc.forecast_platform
                })
        
        # Sort locations by sequence
        locations.sort(key=lambda loc: loc["sequence"])
        
        # Convert associations to serializable format
        associations = []
        for location, assoc_list in train.associations.items():
            for assoc in assoc_list:
                associations.append({
                    "main_uid": assoc.main_uid,
                    "assoc_uid": assoc.assoc_uid,
                    "main_headcode": assoc.main_train.headcode if assoc.main_train else None,
                    "assoc_headcode": assoc.assoc_train.headcode if assoc.assoc_train else None,
                    "category": assoc.category,
                    "location": assoc.location,
                    "date_from": assoc.date_from.isoformat(),
                    "date_to": assoc.date_to.isoformat(),
                    "days_run": assoc.days_run,
                    "stp_indicator": assoc.stp_indicator
                })
        
        # Build response
        train_data = {
            "uid": train.uid,
            "headcode": train.headcode,
            "berth": train.berth,
            "last_location": train.last_location,
            "delay": train.delay,
            "forecast_delay": train.forecast_delay,
            "forecast_delay_at": train.forecast_delay_at.isoformat() if train.forecast_delay_at else None,
            "schedule": {
                "id": train.schedule.id if train.schedule else None,
                "stp_indicator": train.schedule.stp_indicator if train.schedule else None,
                "transaction_type": train.schedule.transaction_type if train.schedule else None,
                "runs_from": train.schedule.runs_from.isoformat() if train.schedule and train.schedule.runs_from else None,
                "runs_to": train.schedule.runs_to.isoformat() if train.schedule and train.schedule.runs_to else None,
                "days_run": train.schedule.days_run if train.schedule else None,
                "train_status": train.schedule.train_status if train.schedule else None,
                "train_category": train.schedule.train_category if train.schedule else None,
                "service_code": train.schedule.service_code if train.schedule else None,
                "power_type": train.schedule.power_type if train.schedule else None,
                "speed": train.schedule.speed if train.schedule else None,
                "operating_chars": train.schedule.operating_chars if train.schedule else None,
                "source_table": train.schedule.source_table if train.schedule else None
            },
            "locations": locations,
            "associations": associations
        }
        
        return jsonify({
            "success": True,
            "train": train_data
        })
    except Exception as e:
        logger.exception(f"Error getting train details: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@active_trains_bp.route('/location/<tiploc>', methods=['GET'])
def get_trains_at_location(tiploc):
    """Get all trains passing through a specific location."""
    try:
        manager = get_active_trains_manager()
        trains = manager.get_trains_at_location(tiploc)
        
        if not trains:
            return jsonify({
                "success": True,
                "message": f"No trains found at location: {tiploc}",
                "trains": []
            })
        
        # Convert train data to serializable format
        train_data = []
        for train in trains:
            location = train.schedule.get_first_location_at_tiploc(tiploc) if train.schedule else None
            
            train_data.append({
                "uid": train.uid,
                "headcode": train.headcode,
                "schedule_id": train.schedule.id if train.schedule else None,
                "category": train.schedule.train_category if train.schedule else None,
                "arr_time": location.arr_time if location else None,
                "dep_time": location.dep_time if location else None,
                "pass_time": location.pass_time if location else None,
                "platform": location.platform if location else None,
                "line": location.line if location else None,
                "path": location.path if location else None,
                "delay": train.delay,
                "forecast_delay": train.forecast_delay
            })
        
        # Sort by arrival time
        train_data.sort(key=lambda t: t["arr_time"] if t["arr_time"] else (t["pass_time"] if t["pass_time"] else t["dep_time"]))
        
        return jsonify({
            "success": True,
            "location": tiploc,
            "train_count": len(train_data),
            "trains": train_data
        })
    except Exception as e:
        logger.exception(f"Error getting trains at location: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@active_trains_bp.route('/by_headcode/<headcode>', methods=['GET'])
def get_trains_by_headcode(headcode):
    """Get all active trains that match a specific headcode."""
    check_log_rotation()
    
    try:
        manager = get_active_trains_manager()
        
        # Find all trains with matching headcode
        matching_trains = []
        for uid, train in manager.trains.items():
            if train.headcode == headcode:
                matching_trains.append(train)
        
        if not matching_trains:
            return jsonify({
                "success": True,
                "message": f"No trains found with headcode: {headcode}",
                "trains": []
            })
        
        # Build train data in same format as active_trains endpoint
        train_data = []
        for train in matching_trains:
            # Build the external train object
            train_obj = {
                "train_id": train.headcode,
                "uid": train.uid,
                "headcode": train.headcode,
                "last_step_time": train.last_step_time.isoformat() if train.last_step_time else None,
                "schedule_start_date": date.today().strftime('%Y-%m-%d'),
                "current_berth_id": train.berth,
                "current_berth_entry_time": train.current_berth_entry_time.isoformat() if train.current_berth_entry_time else None,
                "previous_berth": train.previous_berth,
                "current_location": train.current_location,
                "detected": train.detected,
                "terminated": train.terminated,
                "cancelled": train.cancelled
            }
            
            # Add schedule data if available
            if train.schedule:
                schedule_data = {
                    "uid": train.schedule.uid,
                    "headcode": train.schedule.train_identity,
                    "service_code": train.schedule.service_code or "00000000",
                    "stp_indicator": train.schedule.stp_indicator,
                    "transaction_type": train.schedule.transaction_type,
                    "runs_from": train.schedule.runs_from.isoformat() if train.schedule.runs_from else None,
                    "runs_to": train.schedule.runs_to.isoformat() if train.schedule.runs_to else None,
                    "days_run": train.schedule.days_run,
                    "train_status": train.schedule.train_status,
                    "train_category": train.schedule.train_category,
                    "power_type": train.schedule.power_type,
                    "speed": train.schedule.speed,
                    "operating_chars": train.schedule.operating_chars,
                    "source_table": train.schedule.source_table
                }
                train_obj["schedule"] = schedule_data
                
                # Add locations data
                locations = []
                associations = {}
                
                for loc in train.schedule.locations:
                    location_data = {
                        "sequence": loc.sequence,
                        "tiploc": loc.tiploc,
                        "location_type": loc.location_type,
                        "arr_time": loc.arr_time,
                        "dep_time": loc.dep_time,
                        "pass_time": loc.pass_time,
                        "public_arr": loc.public_arr,
                        "public_dep": loc.public_dep,
                        "platform": loc.platform,
                        "line": loc.line,
                        "path": loc.path,
                        "activity": loc.activity,
                        "engineering_allowance": loc.engineering_allowance,
                        "pathing_allowance": loc.pathing_allowance,
                        "performance_allowance": loc.performance_allowance,
                        "actual_arr": loc.actual_arr,
                        "actual_dep": loc.actual_dep,
                        "actual_pass": loc.actual_pass,
                        "actual_platform": loc.actual_platform,
                        "delay_minutes": (loc.delay_seconds or 0) / 60,  # Convert seconds to minutes for API
                        "forecast_arr": loc.forecast_arr,
                        "forecast_dep": loc.forecast_dep,
                        "forecast_pass": loc.forecast_pass,
                        "forecast_platform": loc.forecast_platform,
                        "forecast_timestamp": loc.forecast_timestamp.isoformat() if loc.forecast_timestamp else None,
                        "from_berth": loc.from_berth,
                        "to_berth": loc.to_berth,
                        "pred_arr": loc.pred_arr,
                        "pred_dep": loc.pred_dep,
                        "pred_pass": loc.pred_pass,
                        "pred_delay_min": loc.pred_delay_min,
                        "smart_pred_arr": loc.smart_pred_arr,
                        "smart_pred_dep": loc.smart_pred_dep,
                        "smart_pred_pass": loc.smart_pred_pass,
                        "smart_pred_confidence": loc.smart_pred_confidence,
                        "smart_pred_delay_min": loc.smart_pred_delay_min,
                        "smart_pred_timestamp": loc.smart_pred_timestamp.isoformat() if loc.smart_pred_timestamp else None,
                        "associations": loc.associations,
                        "late_dwell_secs": loc.late_dwell_secs,
                        "recovery_secs": loc.recovery_secs
                    }
                    locations.append(location_data)
                
                train_obj["locations"] = locations
                train_obj["associations"] = associations
            
            train_data.append(train_obj)
        
        return jsonify({
            "success": True,
            "headcode": headcode,
            "train_count": len(train_data),
            "trains": train_data
        })
        
    except Exception as e:
        logger.exception(f"Error getting trains by headcode {headcode}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@active_trains_bp.route('/by_uid/<uid>', methods=['GET'])
def get_trains_by_uid(uid):
    """Get all active trains that match a specific UID."""
    check_log_rotation()
    
    try:
        manager = get_active_trains_manager()
        
        # Find all trains with matching UID
        matching_trains = []
        for train_uid, train in manager.trains.items():
            if train.uid == uid:
                matching_trains.append(train)
        
        if not matching_trains:
            return jsonify({
                "success": True,
                "message": f"No trains found with UID: {uid}",
                "trains": []
            })
        
        # Build train data in same format as active_trains endpoint
        train_data = []
        for train in matching_trains:
            # Build the external train object
            train_obj = {
                "train_id": train.headcode,
                "uid": train.uid,
                "headcode": train.headcode,
                "last_step_time": train.last_step_time.isoformat() if train.last_step_time else None,
                "schedule_start_date": date.today().strftime('%Y-%m-%d'),
                "current_berth_id": train.berth,
                "current_berth_entry_time": train.current_berth_entry_time.isoformat() if train.current_berth_entry_time else None,
                "previous_berth": train.previous_berth,
                "current_location": train.current_location,
                "detected": train.detected,
                "terminated": train.terminated,
                "cancelled": train.cancelled
            }
            
            # Add schedule data if available
            if train.schedule:
                schedule_data = {
                    "uid": train.schedule.uid,
                    "headcode": train.schedule.train_identity,
                    "service_code": train.schedule.service_code or "00000000",
                    "stp_indicator": train.schedule.stp_indicator,
                    "transaction_type": train.schedule.transaction_type,
                    "runs_from": train.schedule.runs_from.isoformat() if train.schedule.runs_from else None,
                    "runs_to": train.schedule.runs_to.isoformat() if train.schedule.runs_to else None,
                    "days_run": train.schedule.days_run,
                    "train_status": train.schedule.train_status,
                    "train_category": train.schedule.train_category,
                    "power_type": train.schedule.power_type,
                    "speed": train.schedule.speed,
                    "operating_chars": train.schedule.operating_chars,
                    "source_table": train.schedule.source_table
                }
                train_obj["schedule"] = schedule_data
                
                # Add locations data
                locations = []
                associations = {}
                
                for loc in train.schedule.locations:
                    location_data = {
                        "sequence": loc.sequence,
                        "tiploc": loc.tiploc,
                        "location_type": loc.location_type,
                        "arr_time": loc.arr_time,
                        "dep_time": loc.dep_time,
                        "pass_time": loc.pass_time,
                        "public_arr": loc.public_arr,
                        "public_dep": loc.public_dep,
                        "platform": loc.platform,
                        "line": loc.line,
                        "path": loc.path,
                        "activity": loc.activity,
                        "engineering_allowance": loc.engineering_allowance,
                        "pathing_allowance": loc.pathing_allowance,
                        "performance_allowance": loc.performance_allowance,
                        "actual_arr": loc.actual_arr,
                        "actual_dep": loc.actual_dep,
                        "actual_pass": loc.actual_pass,
                        "actual_platform": loc.actual_platform,
                        "delay_minutes": (loc.delay_seconds or 0) / 60,  # Convert seconds to minutes for API
                        "forecast_arr": loc.forecast_arr,
                        "forecast_dep": loc.forecast_dep,
                        "forecast_pass": loc.forecast_pass,
                        "forecast_platform": loc.forecast_platform,
                        "forecast_timestamp": loc.forecast_timestamp.isoformat() if loc.forecast_timestamp else None,
                        "from_berth": loc.from_berth,
                        "to_berth": loc.to_berth,
                        "pred_arr": loc.pred_arr,
                        "pred_dep": loc.pred_dep,
                        "pred_pass": loc.pred_pass,
                        "pred_delay_min": loc.pred_delay_min,
                        "smart_pred_arr": loc.smart_pred_arr,
                        "smart_pred_dep": loc.smart_pred_dep,
                        "smart_pred_pass": loc.smart_pred_pass,
                        "smart_pred_confidence": loc.smart_pred_confidence,
                        "smart_pred_delay_min": loc.smart_pred_delay_min,
                        "smart_pred_timestamp": loc.smart_pred_timestamp.isoformat() if loc.smart_pred_timestamp else None,
                        "associations": loc.associations,
                        "late_dwell_secs": loc.late_dwell_secs,
                        "recovery_secs": loc.recovery_secs
                    }
                    locations.append(location_data)
                
                train_obj["locations"] = locations
                train_obj["associations"] = associations
            
            train_data.append(train_obj)
        
        return jsonify({
            "success": True,
            "uid": uid,
            "train_count": len(train_data),
            "trains": train_data
        })
        
    except Exception as e:
        logger.exception(f"Error getting trains by UID {uid}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def detect_train_if_needed(manager, headcode: str, from_berth: str, to_berth: str, timestamp: datetime) -> Optional[ActiveTrain]:
    # Find detected trains
    detected = [t for t in manager.trains.values() if t.headcode == headcode and t.detected]
    if detected:
        if len(detected) == 1:
            logger.debug(f"Real-time update: train {headcode} already detected (UID: {detected[0].uid})")
            return detected[0]
        else:
            logger.warning(f"Real-time update: {len(detected)} detected trains for {headcode}, ambiguity detected")
            return None

    # No detected trains — find best candidate for activation
    candidates = [t for t in manager.trains.values() if t.headcode == headcode]
    if not candidates:
        logger.warning(f"Real-time update: no trains found in timetable for headcode {headcode}")
        return None

    if len(candidates) > 1:
        logger.info(f"Real-time update: {len(candidates)} candidate trains for {headcode}, choosing by departure time proximity")

    # Sort by scheduled or forecast departure time closest to now
    # Convert timestamp to London timezone and make it naive for comparison with schedule times
    from active_trains import to_london_tz, get_london_now
    now = to_london_tz(timestamp).replace(tzinfo=None)
    def get_dep_time(t):
        if not t.schedule or not t.schedule.locations:
            return datetime.max
        # Get the first location with a departure time (earliest departure)
        locations_with_dep = [loc for loc in t.schedule.locations if loc.dep_time]
        if not locations_with_dep:
            return datetime.max
        sorted_locations = sorted(locations_with_dep, key=lambda x: x.dep_time)
        for loc in sorted_locations:
            if loc.dep_time:
                try:
                    logger.info(f"Using for {t.headcode}, {loc.tiploc} dep: {loc.dep_time}")
                    # Handle both HH:MM and HH:MM:SS formats
                    if len(loc.dep_time) == 5:  # HH:MM
                        dt = datetime.strptime(loc.dep_time, "%H:%M")
                    else:  # HH:MM:SS
                        dt = datetime.strptime(loc.dep_time, "%H:%M:%S")
                    return dt.replace(year=now.year, month=now.month, day=now.day)
                except Exception as e:
                    logger.warning(f"Failed to parse time {loc.dep_time}: {e}")
                    continue
        return datetime.max

    # Filter candidates within reasonable time window and show time differences
    threshold_seconds = config.TIMETABLE_MATCHING_THRESHOLD_MINS * 60
    filtered_candidates = []
    
    for t in candidates:
        dep_time = get_dep_time(t)
        time_diff = (dep_time - now).total_seconds()
        abs_diff = abs(time_diff)
        logger.info(f"Candidate {t.uid}: dep_time={dep_time.strftime('%H:%M:%S')}, diff={time_diff:.0f}s, abs_diff={abs_diff:.0f}s")
        
        if abs_diff <= threshold_seconds:
            filtered_candidates.append(t)
            logger.info(f"  -> Within {config.TIMETABLE_MATCHING_THRESHOLD_MINS}min threshold, keeping candidate")
        else:
            logger.info(f"  -> Outside {config.TIMETABLE_MATCHING_THRESHOLD_MINS}min threshold ({abs_diff/60:.1f}min), discarding")
    
    if not filtered_candidates:
        logger.warning(f"No candidates within {config.TIMETABLE_MATCHING_THRESHOLD_MINS}min threshold, using all candidates")
        filtered_candidates = candidates
    
    # Sort by absolute time difference from now - pick the closest time match
    filtered_candidates.sort(key=lambda t: abs((get_dep_time(t) - now).total_seconds()))
    candidates = filtered_candidates
    logger.info(f"Sorted by time proximity to current time - choosing closest match from {len(candidates)} candidates")
    logger.info(f"Sorted candidates = {[f'{t.uid}({t.headcode})' for t in candidates]}")
    chosen = candidates[0]
    chosen.detected = True
    chosen.berth = to_berth
    chosen.last_step_time = timestamp
    
    # Log train activation with candidate count
    if len(candidates) > 1:
        logger.info(f"Train activated: {headcode} (UID: {chosen.uid}) detected at {to_berth} at {timestamp.strftime('%H:%M:%S')} - chosen from {len(candidates)} candidates")
    else:
        logger.info(f"Train activated: {headcode} (UID: {chosen.uid}) detected at {to_berth} at {timestamp.strftime('%H:%M:%S')}")
    
    return chosen

@active_trains_bp.route('/logs', methods=['GET'])
def get_logs():
    """Get recent log entries for web display."""
    try:
        lines = request.args.get('lines', 500, type=int)
        lines = min(lines, 2000)  # Cap at 2000 lines
        
        log_manager = get_log_manager()
        log_lines = log_manager.get_recent_logs(lines)
        log_stats = log_manager.get_log_stats()
        
        return jsonify({
            "logs": log_lines,
            "stats": log_stats,
            "requested_lines": lines,
            "actual_lines": len(log_lines)
        })
        
    except Exception as e:
        return jsonify({
            "error": "Failed to retrieve logs",
            "message": str(e)
        }), 500

# ============================================================================
# BLUEPRINT REGISTRATION
# ============================================================================

# Blueprint is now registered directly in main.py with /api/trains prefix