import logging
import os
import json
from datetime import date, datetime
import traceback

from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for
from sqlalchemy import text, or_, and_, cast, Integer, extract, desc, func, asc
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import case

# Import configuration
import config

from database import get_db
from models import ParsedFile, BasicSchedule as Schedule, ScheduleLocation, Association
import cif_parser_fixed

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

web_bp = Blueprint('web', __name__, template_folder='templates', static_folder='static')

db = get_db()

@web_bp.route('/')
def index():
    """Home page with station and date selection form."""
    stations = [
        {"code": code, "name": config.LOCATION_NAMES.get(code, code)}
        for code in config.AREA_OF_INTEREST
    ]
    
    today = date.today().isoformat()
    
    return render_template('index.html', 
                           stations=stations,
                           today=today)

@web_bp.route('/schedules')
def schedules():
    """Display schedules for a given location and date using direct database access."""
    location_code = request.args.get('location', list(config.AREA_OF_INTEREST)[0])
    date_str = request.args.get('date', date.today().isoformat())
    platform = request.args.get('platform')
    line = request.args.get('line')
    path = request.args.get('path')
    
    logger.info(f"Looking for schedules at {location_code} on {date_str} via direct DB access")
    
    try:
        search_date = date.fromisoformat(date_str)
        day_of_week = search_date.weekday()
        day_position = day_of_week + 1  # CIF days_run uses 1-based positions
        
        # Find all schedules at this location with STP precedence
        # First, get all schedules that might be relevant
        query = """
        WITH location_schedules AS (
            -- Permanent schedules locations
            SELECT schedule_id, id as location_id, arr, dep, "pass" as pass_time, 
                   platform, line, path, activity, 
                   public_arr, public_dep, tiploc,
                   engineering_allowance, pathing_allowance, performance_allowance,
                   'schedules_ltp' as source_table,
                   'P' as stp_indicator
            FROM schedule_locations_ltp
            WHERE tiploc = :location
            
            UNION ALL
            
            -- New schedules locations
            SELECT schedule_id, id as location_id, arr, dep, "pass" as pass_time, 
                   platform, line, path, activity, 
                   public_arr, public_dep, tiploc,
                   engineering_allowance, pathing_allowance, performance_allowance,
                   'schedules_stp_new' as source_table,
                   'N' as stp_indicator
            FROM schedule_locations_stp_new
            WHERE tiploc = :location
            
            UNION ALL
            
            -- Overlay schedules locations
            SELECT schedule_id, id as location_id, arr, dep, "pass" as pass_time, 
                   platform, line, path, activity,
                   public_arr, public_dep, tiploc,
                   engineering_allowance, pathing_allowance, performance_allowance,
                   'schedules_stp_overlay' as source_table,
                   'O' as stp_indicator
            FROM schedule_locations_stp_overlay
            WHERE tiploc = :location
            
            UNION ALL
            
            -- Cancellation schedules locations
            SELECT schedule_id, id as location_id, arr, dep, "pass" as pass_time, 
                   platform, line, path, activity,
                   public_arr, public_dep, tiploc,
                   engineering_allowance, pathing_allowance, performance_allowance,
                   'schedules_stp_cancellation' as source_table,
                   'C' as stp_indicator
            FROM schedule_locations_stp_cancellation
            WHERE tiploc = :location
        ),
        filtered_schedules AS (
            -- Permanent schedules
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.location_id, ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path,
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                ls.engineering_allowance, ls.pathing_allowance, ls.performance_allowance,
                ls.source_table, ls.stp_indicator,
                4 as precedence  -- Lowest precedence
            FROM 
                schedules_ltp s
            JOIN 
                location_schedules ls ON s.id = ls.schedule_id AND ls.source_table = 'schedules_ltp'
            WHERE 
                :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTR(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
            
            UNION ALL
            
            -- New STP schedules
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.location_id, ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path,
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                ls.engineering_allowance, ls.pathing_allowance, ls.performance_allowance,
                ls.source_table, ls.stp_indicator,
                3 as precedence
            FROM 
                schedules_stp_new s
            JOIN 
                location_schedules ls ON s.id = ls.schedule_id AND ls.source_table = 'schedules_stp_new'
            WHERE 
                :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTR(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
            
            UNION ALL
            
            -- Overlay STP schedules
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.location_id, ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path,
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                ls.engineering_allowance, ls.pathing_allowance, ls.performance_allowance,
                ls.source_table, ls.stp_indicator,
                2 as precedence
            FROM 
                schedules_stp_overlay s
            JOIN 
                location_schedules ls ON s.id = ls.schedule_id AND ls.source_table = 'schedules_stp_overlay'
            WHERE 
                :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTR(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
            
            UNION ALL
            
            -- Cancellation STP schedules (highest precedence)
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.location_id, ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path,
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                ls.engineering_allowance, ls.pathing_allowance, ls.performance_allowance,
                ls.source_table, ls.stp_indicator,
                1 as precedence  -- Highest precedence
            FROM 
                schedules_stp_cancellation s
            JOIN 
                location_schedules ls ON s.id = ls.schedule_id AND ls.source_table = 'schedules_stp_cancellation'
            WHERE 
                :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTR(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
        ),
        -- Get minimum precedence (highest STP) for each UID
        best_precedence AS (
            SELECT uid, MIN(precedence) as min_precedence
            FROM filtered_schedules
            GROUP BY uid
        ),
        -- Get schedules with the best precedence for each UID
        best_schedules AS (
            SELECT fs.*
            FROM filtered_schedules fs
            JOIN best_precedence bp ON fs.uid = bp.uid AND fs.precedence = bp.min_precedence
        )
        -- Final result
        SELECT 
            id, uid, train_identity, runs_from, runs_to, days_run,
            train_status, train_category, power_type, timing_load,
            location_id, arr, dep, pass_time, platform, line, path, 
            activity, public_arr, public_dep, tiploc,
            source_table, stp_indicator
        FROM 
            best_schedules
        ORDER BY
            CASE 
                WHEN arr IS NOT NULL THEN arr
                ELSE dep
            END
        """
        
        result = db.session.execute(
            text(query), 
            {
                "location": location_code, 
                "search_date": search_date,
                "day_position": day_position,
                "platform": platform,
                "line": line,
                "path": path
            }
        )
        
        # Convert to list of dicts
        schedules = []
        schedule_count = 0
        
        for row in result:
            schedules.append({
                "id": row.id,
                "uid": row.uid,
                "train_identity": row.train_identity,
                "runs_from": row.runs_from.isoformat() if row.runs_from else None,
                "runs_to": row.runs_to.isoformat() if row.runs_to else None,
                "days_run": row.days_run,
                "train_status": row.train_status,
                "train_category": row.train_category,
                "power_type": row.power_type,
                "timing_load": row.timing_load,
                "location": {
                    "id": row.location_id,
                    "arr": row.arr,
                    "dep": row.dep,
                    "pass_time": row.pass_time,  # Use pass_time instead of pass
                    "platform": row.platform,
                    "line": row.line,
                    "path": row.path,
                    "activity": row.activity,
                    "public_arr": row.public_arr,
                    "public_dep": row.public_dep,
                    "tiploc": row.tiploc
                },
                "source_table": row.source_table,
                "stp_indicator": row.stp_indicator
            })
            schedule_count += 1
        
        logger.info(f"Found {schedule_count} schedules for {location_code} on {date_str}")
        
        # Now get all associations for the found schedules
        if schedules:
            # Extract all unique UIDs from the schedules
            uids = [s["uid"] for s in schedules]
            
            # Query for associations
            assoc_query = """
            WITH stp_ranked_associations AS (
                -- Permanent associations
                SELECT 
                    a.id, a.main_uid, a.assoc_uid, a.date_from, a.date_to, a.days_run, 
                    a.category, a.location, a.base_suffix, a.assoc_suffix,
                    a.date_indicator, 'P' as stp_indicator,
                    4 as precedence  -- Lowest precedence
                FROM 
                    associations a
                WHERE 
                    a.main_uid IN :uids OR a.assoc_uid IN :uids
                    AND :search_date BETWEEN a.date_from AND a.date_to
                    AND SUBSTR(a.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                -- New associations
                SELECT 
                    a.id, a.main_uid, a.assoc_uid, a.date_from, a.date_to, a.days_run, 
                    a.category, a.location, a.base_suffix, a.assoc_suffix,
                    a.date_indicator, 'N' as stp_indicator,
                    3 as precedence
                FROM 
                    associations_stp_new a
                WHERE 
                    (a.main_uid IN :uids OR a.assoc_uid IN :uids)
                    AND :search_date BETWEEN a.date_from AND a.date_to
                    AND SUBSTR(a.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                -- Overlay associations
                SELECT 
                    a.id, a.main_uid, a.assoc_uid, a.date_from, a.date_to, a.days_run, 
                    a.category, a.location, a.base_suffix, a.assoc_suffix,
                    a.date_indicator, 'O' as stp_indicator,
                    2 as precedence
                FROM 
                    associations_stp_overlay a
                WHERE 
                    (a.main_uid IN :uids OR a.assoc_uid IN :uids)
                    AND :search_date BETWEEN a.date_from AND a.date_to
                    AND SUBSTR(a.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                -- Cancellation associations
                SELECT 
                    a.id, a.main_uid, a.assoc_uid, a.date_from, a.date_to, a.days_run, 
                    a.category, a.location, a.base_suffix, a.assoc_suffix,
                    a.date_indicator, 'C' as stp_indicator,
                    1 as precedence  -- Highest precedence
                FROM 
                    associations_stp_cancellation a
                WHERE 
                    (a.main_uid IN :uids OR a.assoc_uid IN :uids)
                    AND :search_date BETWEEN a.date_from AND a.date_to
                    AND SUBSTR(a.days_run, :day_position, 1) = '1'
            ),
            -- Get minimum precedence (highest STP) for each association pair
            best_assoc_precedence AS (
                SELECT main_uid, assoc_uid, location, MIN(precedence) as min_precedence
                FROM stp_ranked_associations
                GROUP BY main_uid, assoc_uid, location
            ),
            -- Get associations with the best precedence for each pair
            best_associations AS (
                SELECT a.*
                FROM stp_ranked_associations a
                JOIN best_assoc_precedence b 
                    ON a.main_uid = b.main_uid 
                    AND a.assoc_uid = b.assoc_uid 
                    AND a.location = b.location
                    AND a.precedence = b.min_precedence
            )
            -- Final result
            SELECT *
            FROM best_associations
            """
            
            assoc_result = db.session.execute(
                text(assoc_query), 
                {
                    "uids": tuple(uids),
                    "search_date": search_date,
                    "day_position": day_position
                }
            )
            
            # Convert to list of dicts
            associations = []
            
            for row in assoc_result:
                # Skip cancelled associations
                if row.stp_indicator == 'C':
                    continue
                
                associations.append({
                    "id": row.id,
                    "main_uid": row.main_uid,
                    "assoc_uid": row.assoc_uid,
                    "date_from": row.date_from.isoformat() if row.date_from else None,
                    "date_to": row.date_to.isoformat() if row.date_to else None,
                    "days_run": row.days_run,
                    "category": row.category,
                    "location": row.location,
                    "base_suffix": row.base_suffix,
                    "assoc_suffix": row.assoc_suffix,
                    "date_indicator": row.date_indicator,
                    "stp_indicator": row.stp_indicator
                })
        else:
            associations = []
        
        stations = [
            {"code": code, "name": config.LOCATION_NAMES.get(code, code)}
            for code in config.AREA_OF_INTEREST
        ]
        
        # Render the template
        return render_template(
            'schedules.html',
            location=location_code,
            search_date=date_str,
            platform=platform or '',
            line=line or '',
            path=path or '',
            schedules=schedules,
            associations=associations,
            stations=stations
        )
    
    except Exception as e:
        logger.exception(f"Error retrieving schedules: {e}")
        return render_template(
            'schedules.html',
            location=location_code,
            search_date=date_str,
            error=str(e),
            schedules=[],
            associations=[]
        )

@web_bp.route('/debug/database')
def debug_database():
    """
    Debug endpoint that returns all schedule data in JSON format.
    Shows schedules, locations, and associations from all STP tables.
    """
    try:
        limit = int(request.args.get('limit', 50))
        
        # Get schedules from all tables
        ltp_schedules = db.session.query(Schedule).filter_by(table="schedules_ltp").limit(limit).all()
        new_schedules = db.session.query(Schedule).filter_by(table="schedules_stp_new").limit(limit).all()
        overlay_schedules = db.session.query(Schedule).filter_by(table="schedules_stp_overlay").limit(limit).all()
        cancel_schedules = db.session.query(Schedule).filter_by(table="schedules_stp_cancellation").limit(limit).all()
        
        # Get locations from all tables
        ltp_locations = db.session.query(ScheduleLocation).filter_by(table="schedule_locations_ltp").limit(limit).all()
        new_locations = db.session.query(ScheduleLocation).filter_by(table="schedule_locations_stp_new").limit(limit).all()
        overlay_locations = db.session.query(ScheduleLocation).filter_by(table="schedule_locations_stp_overlay").limit(limit).all()
        cancel_locations = db.session.query(ScheduleLocation).filter_by(table="schedule_locations_stp_cancellation").limit(limit).all()
        
        # Get associations from all tables
        ltp_associations = db.session.query(Association).filter_by(table="associations").limit(limit).all()
        new_associations = db.session.query(Association).filter_by(table="associations_stp_new").limit(limit).all()
        overlay_associations = db.session.query(Association).filter_by(table="associations_stp_overlay").limit(limit).all()
        cancel_associations = db.session.query(Association).filter_by(table="associations_stp_cancellation").limit(limit).all()
        
        # Build the response
        result = {
            "schedules": {
                "ltp": [s.to_dict() for s in ltp_schedules],
                "new": [s.to_dict() for s in new_schedules],
                "overlay": [s.to_dict() for s in overlay_schedules],
                "cancellation": [s.to_dict() for s in cancel_schedules]
            },
            "locations": {
                "ltp": [l.to_dict() for l in ltp_locations],
                "new": [l.to_dict() for l in new_locations],
                "overlay": [l.to_dict() for l in overlay_locations],
                "cancellation": [l.to_dict() for l in cancel_locations]
            },
            "associations": {
                "ltp": [a.to_dict() for a in ltp_associations],
                "new": [a.to_dict() for a in new_associations],
                "overlay": [a.to_dict() for a in overlay_associations],
                "cancellation": [a.to_dict() for a in cancel_associations]
            }
        }
        
        return jsonify(result)
    
    except Exception as e:
        logger.exception(f"Error in debug database endpoint: {e}")
        return jsonify({"error": str(e)})

@web_bp.route('/maintenance')
def maintenance():
    """
    Database maintenance page - shows options to reset and reload CIF data.
    """
    last_file = db.session.query(ParsedFile).order_by(ParsedFile.processed_at.desc()).first()
    if last_file:
        last_processed = {
            "file_ref": last_file.file_ref,
            "type": last_file.extract_type,
            "processed_at": last_file.processed_at.isoformat() if last_file.processed_at else None
        }
    else:
        last_processed = None
    
    # Get current counts using the specific models
    from models import ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation
    from models import AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation
    from models import ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation
    
    perm_schedules = db.session.query(func.count()).select_from(ScheduleLTP).scalar() or 0
    stp_new_schedules = db.session.query(func.count()).select_from(ScheduleSTPNew).scalar() or 0
    stp_overlay_schedules = db.session.query(func.count()).select_from(ScheduleSTPOverlay).scalar() or 0
    stp_cancel_schedules = db.session.query(func.count()).select_from(ScheduleSTPCancellation).scalar() or 0
    
    perm_assocs = db.session.query(func.count()).select_from(AssociationLTP).scalar() or 0
    stp_new_assocs = db.session.query(func.count()).select_from(AssociationSTPNew).scalar() or 0
    stp_overlay_assocs = db.session.query(func.count()).select_from(AssociationSTPOverlay).scalar() or 0
    stp_cancel_assocs = db.session.query(func.count()).select_from(AssociationSTPCancellation).scalar() or 0
    
    perm_locs = db.session.query(func.count()).select_from(ScheduleLocationLTP).scalar() or 0
    stp_new_locs = db.session.query(func.count()).select_from(ScheduleLocationSTPNew).scalar() or 0
    stp_overlay_locs = db.session.query(func.count()).select_from(ScheduleLocationSTPOverlay).scalar() or 0
    stp_cancel_locs = db.session.query(func.count()).select_from(ScheduleLocationSTPCancellation).scalar() or 0
    
    # Prepare stats for display
    stats = {
        "schedules": {
            "permanent": perm_schedules,
            "stp_new": stp_new_schedules,
            "stp_overlay": stp_overlay_schedules,
            "stp_cancel": stp_cancel_schedules,
            "total": perm_schedules + stp_new_schedules + stp_overlay_schedules + stp_cancel_schedules
        },
        "associations": {
            "permanent": perm_assocs,
            "stp_new": stp_new_assocs,
            "stp_overlay": stp_overlay_assocs,
            "stp_cancel": stp_cancel_assocs,
            "total": perm_assocs + stp_new_assocs + stp_overlay_assocs + stp_cancel_assocs
        },
        "locations": {
            "permanent": perm_locs,
            "stp_new": stp_new_locs,
            "stp_overlay": stp_overlay_locs,
            "stp_cancel": stp_cancel_locs,
            "total": perm_locs + stp_new_locs + stp_overlay_locs + stp_cancel_locs
        }
    }
    
    return render_template(
        'maintenance.html',
        last_processed=last_processed,
        stats=stats
    )

@web_bp.route('/reset-reload-db', methods=['POST'])
def reset_reload_db():
    """
    Handle database reset and reload request from web interface.
    """
    try:
        # Reset the database
        from reset_db_clean import reset_database
        reset_database()
        
        # Trigger file processing
        cif_parser_fixed.process_cif_files()
        
        return jsonify({
            "success": True,
            "message": "Database reset and CIF files processed successfully."
        })
    except Exception as e:
        logger.exception(f"Error in reset/reload: {e}")
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500

@web_bp.route('/train-graph')
def train_graph_view():
    """Train graph viewer page."""
    return render_template('train-graph/index.html')

@web_bp.route('/train-graph/configs')
def train_graph_configs():
    """API endpoint to get all available train graph configurations."""
    try:
        configs_path = os.path.join(current_app.root_path, 'train_graph_configs')
        configs = []
        
        if os.path.exists(configs_path):
            for filename in os.listdir(configs_path):
                if filename.endswith('.json'):
                    config_id = os.path.splitext(filename)[0]
                    config_path = os.path.join(configs_path, filename)
                    
                    with open(config_path, 'r') as f:
                        config_data = json.load(f)
                    
                    configs.append({
                        'id': config_id,
                        'name': config_data.get('name', config_id),
                        'description': config_data.get('description', '')
                    })
        
        return jsonify(configs)
    except Exception as e:
        logger.exception(f"Error getting train graph configurations: {e}")
        return jsonify({'error': str(e)}), 500

@web_bp.route('/train-graph/config/<config_id>')
def train_graph_config(config_id):
    """API endpoint to get a specific train graph configuration."""
    try:
        config_path = os.path.join(current_app.root_path, 'train_graph_configs', f"{config_id}.json")
        
        if not os.path.exists(config_path):
            return jsonify({'error': f"Configuration '{config_id}' not found"}), 404
        
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        return jsonify(config_data)
    except Exception as e:
        logger.exception(f"Error getting train graph configuration '{config_id}': {e}")
        return jsonify({'error': str(e)}), 500

@web_bp.route('/train-graph/schedules', methods=['POST'])
def train_graph_schedules():
    """API endpoint to get schedules for multiple locations."""
    try:
        data = request.get_json()
        locations = data.get('locations', [])
        date_str = data.get('date')
        
        if not locations:
            return jsonify({'error': 'No locations specified'}), 400
        
        if not date_str:
            return jsonify({'error': 'No date specified'}), 400
        
        # Import the API function here to avoid circular imports
        from api import get_schedules_for_multiple_locations
        
        search_date = date.fromisoformat(date_str)
        
        schedules = get_schedules_for_multiple_locations(locations, search_date)
        
        return jsonify({'schedules': schedules})
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception(f"Error getting train graph schedules: {e}\n{tb}")
        return jsonify({'error': str(e)}), 500

@web_bp.route('/platform-docker')
def platform_docker():
    """
    Platform Docker visualization page with progressive loading
    Shows a timeline visualization of platform usage with async data loading

    Query Parameters:
        location: TIPLOC code of the location (default: CHRX)
        date: Date in YYYY-MM-DD format (default: today)
    """
    location = request.args.get('location', list(config.AREA_OF_INTEREST)[0])
    
    # Always provide today's date in YYYY-MM-DD format for HTML5 date inputs
    # This ensures the date picker has a proper default value
    today = date.today()
    date_param = today.strftime('%Y-%m-%d')  # Format as YYYY-MM-DD
    
    stations = [
        {"code": code, "name": config.LOCATION_NAMES.get(code, code)}
        for code in config.AREA_OF_INTEREST
    ]
    
    # Use the new platform docker template with live data support
    return render_template(
        'platform_docker_live_data.html',
        location=location,
        date=date_param,
        stations=stations,
        start_time="0000",
        end_time="2359",
        platforms=[]
    )


@web_bp.route('/simple_platform_data', methods=['POST'])
def simple_platform_data():
    """
    Simplified API endpoint to get platform data for the platform docker visualization.
    Uses basic queries to avoid transaction issues.
    """
    # Get the existing session
    session = db.session
    
    try:
        # Get request data
        data = request.get_json()
        location_code = data.get('location', list(config.AREA_OF_INTEREST)[0])
        date_str = data.get('date', str(date.today()))
        
        # Parse date
        search_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        day_of_week = search_date.weekday() + 1  # 1 = Monday, 7 = Sunday
        
        logger.info(f"Fetching simplified platform data for {location_code} on {date_str}")
        
        # First, get all platforms at this location using a simple query
        platforms_query = """
        SELECT DISTINCT 
            COALESCE(platform, 'Unknown') as platform,
            COUNT(*) as train_count
        FROM (
            SELECT platform FROM schedule_locations_ltp WHERE tiploc = :loc
            UNION ALL
            SELECT platform FROM schedule_locations_stp_new WHERE tiploc = :loc
            UNION ALL
            SELECT platform FROM schedule_locations_stp_overlay WHERE tiploc = :loc
            UNION ALL
            SELECT platform FROM schedule_locations_stp_cancellation WHERE tiploc = :loc
        ) as loc_platforms
        WHERE platform IS NOT NULL
        GROUP BY COALESCE(platform, 'Unknown')
        ORDER BY 
            CASE WHEN platform ~ '^[0-9]+$' THEN CAST(platform AS INTEGER) ELSE 9999 END,
            platform
        """
        
        # Reset session to clear any pending transactions
        session.rollback()
        
        # Execute the platforms query
        platform_results = session.execute(text(platforms_query), {"loc": location_code})
        platforms = []
        
        for row in platform_results:
            # For each platform, get the train schedule data
            trains_query = """
            WITH location_trains AS (
                -- Get basic schedule information
                SELECT
                    s.uid,
                    s.train_identity as headcode,
                    s.train_category as category,
                    l.platform,
                    l.arr as arrival_time,
                    l.dep as departure_time,
                    l.location_type
                FROM
                    schedule_locations_ltp l
                JOIN
                    schedules_ltp s ON l.schedule_id = s.id
                WHERE
                    l.tiploc = :loc
                    AND l.platform = :platform
                    AND :search_date BETWEEN s.runs_from AND s.runs_to
                    AND SUBSTRING(s.days_run, :day_of_week, 1) = '1'
                
                UNION ALL
                
                SELECT
                    s.uid,
                    s.train_identity as headcode,
                    s.train_category as category,
                    l.platform,
                    l.arr as arrival_time,
                    l.dep as departure_time,
                    l.location_type
                FROM
                    schedule_locations_stp_new l
                JOIN
                    schedules_stp_new s ON l.schedule_id = s.id
                WHERE
                    l.tiploc = :loc
                    AND l.platform = :platform
                    AND :search_date BETWEEN s.runs_from AND s.runs_to
                    AND SUBSTRING(s.days_run, :day_of_week, 1) = '1'
            )
            SELECT
                uid,
                headcode,
                category,
                platform,
                arrival_time,
                departure_time,
                location_type
            FROM
                location_trains
            ORDER BY
                COALESCE(arrival_time, departure_time)
            LIMIT 20
            """
            
            trains_params = {
                "loc": location_code,
                "platform": row.platform,
                "search_date": search_date,
                "day_of_week": day_of_week
            }
            
            try:
                # Execute the trains query
                trains_result = session.execute(text(trains_query), trains_params)
                trains = []
                
                for train in trains_result:
                    train_data = {
                        "uid": train.uid,
                        "headcode": train.headcode,
                        "category": train.category,
                        "platform": train.platform
                    }
                    
                    if train.arrival_time:
                        train_data["arrival_time"] = train.arrival_time
                        
                    if train.departure_time:
                        train_data["departure_time"] = train.departure_time
                    
                    # Add additional info about the stop type
                    if train.location_type == 'LO':
                        train_data["origin"] = "Origin"
                    elif train.location_type == 'LT':
                        train_data["destination"] = "Terminating"
                    elif train.location_type == 'LI':
                        train_data["intermediate"] = True
                        
                    trains.append(train_data)
                
                platforms.append({
                    "platform": row.platform,
                    "train_count": row.train_count,
                    "trains": trains
                })
            except Exception as e:
                # Log the error but continue with other platforms
                logger.exception(f"Error fetching trains for platform {row.platform}: {str(e)}")
                platforms.append({
                    "platform": row.platform,
                    "train_count": row.train_count,
                    "trains": [],
                    "error": str(e)
                })
                session.rollback()
        
        # Make sure to commit the session
        session.commit()
        session.close()
        
        return jsonify({
            "platforms": platforms,
            "location": location_code,
            "date": date_str
        })
        
    except Exception as e:
        # Make sure to rollback on error
        session.rollback()
        session.close()
        logger.exception(f"Error in simple_platform_data: {str(e)}")
        return jsonify({"error": f"Failed to retrieve platform data: {str(e)}"}), 500

@web_bp.route('/platform_docker_data', methods=['POST'])
def platform_docker_data():
    """API endpoint to fetch platform docker data with pagination"""
    # Create a new session for this request to avoid transaction issues
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from flask import current_app
    import os
    
    # Make sure URL is not None
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
        
    engine = create_engine(db_url, 
                          pool_recycle=300, 
                          pool_pre_ping=True,
                          connect_args={"connect_timeout": 15})
    Session = sessionmaker(bind=engine)
    
    # Use a session instance instead of the global db.session
    session = Session()
    
    try:
        params = request.get_json()
        
        location_code = params.get('location')
        date_str = params.get('date')
        
        # Validate and standardize date format
        if not location_code:
            return jsonify({'error': 'Missing location parameter'}), 400
            
        if not date_str:
            # Default to today if date is missing
            today = date.today()
            date_str = today.strftime('%Y-%m-%d')
            search_date = today
            logger.info(f"No date provided, using today: {date_str}")
        else:
            try:
                # Parse the date, standardizing format
                if '-' not in date_str and len(date_str) == 8:
                    # Handle YYYYMMDD format
                    year = int(date_str[0:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])
                    search_date = date(year, month, day)
                    date_str = search_date.strftime('%Y-%m-%d')  # Convert to YYYY-MM-DD
                else:
                    # Handle other formats using date.fromisoformat
                    search_date = date.fromisoformat(date_str)
                    date_str = search_date.strftime('%Y-%m-%d')  # Standardize format
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid date format: {date_str}, error: {str(e)}")
                return jsonify({'error': f'Invalid date format: {date_str}. Please use YYYY-MM-DD format.'}), 400
        
        logger.info(f"Using date: {date_str} for location: {location_code}")
        page = int(params.get('page', 1))
        per_page = int(params.get('per_page', 3))
        logging.info("search date: " + str(search_date))
        day_of_week = search_date.weekday()
        day_position = day_of_week + 1  # CIF uses 1-based position
        offset = (page - 1) * per_page
        
        logger.info(f"Fetching platform docker data for {location_code} on {date_str}")
        
        # First, get all platforms for this location
        platforms_query = """
        WITH location_schedules AS (
            -- Get all schedule IDs for this location from location tables
            SELECT DISTINCT schedule_id 
            FROM schedule_locations_ltp
            WHERE tiploc = :location
            
            UNION
            
            SELECT DISTINCT schedule_id 
            FROM schedule_locations_stp_new
            WHERE tiploc = :location
            
            UNION
            
            SELECT DISTINCT schedule_id 
            FROM schedule_locations_stp_overlay
            WHERE tiploc = :location
            
            UNION
            
            SELECT DISTINCT schedule_id 
            FROM schedule_locations_stp_cancellation
            WHERE tiploc = :location
        )
        -- Get all unique platforms at this location
        SELECT 
            COALESCE(sl.platform, 'Unknown') as platform_id,
            COUNT(DISTINCT sl.schedule_id) as train_count
        FROM (
            -- Join all location tables
            SELECT schedule_id, platform FROM schedule_locations_ltp 
            WHERE tiploc = :location
            
            UNION ALL
            
            SELECT schedule_id, platform FROM schedule_locations_stp_new
            WHERE tiploc = :location
            
            UNION ALL
            
            SELECT schedule_id, platform FROM schedule_locations_stp_overlay
            WHERE tiploc = :location
            
            UNION ALL
            
            SELECT schedule_id, platform FROM schedule_locations_stp_cancellation
            WHERE tiploc = :location
        ) sl
        WHERE sl.schedule_id IN (SELECT schedule_id FROM location_schedules)
        GROUP BY COALESCE(sl.platform, 'Unknown')
        ORDER BY 
            -- Sort platforms numerically when possible
            CASE 
                WHEN COALESCE(sl.platform, 'Unknown') ~ '^[0-9]+$' 
                THEN CAST(COALESCE(sl.platform, 'Unknown') AS INTEGER)
                ELSE 9999
            END,
            COALESCE(sl.platform, 'Unknown')
        """
        
        # Get platform list
        platform_results = session.execute(
            text(platforms_query),
            {"location": location_code}
        )
        
        # Process platforms
        platforms = []
        total_count = 0
        
        for row in platform_results:
            platforms.append({
                "id": row.platform_id,
                "name": row.platform_id,
                "train_count": row.train_count
            })
            total_count += 1
            
        # Apply pagination
        paginated_platforms = platforms[offset:offset + per_page] if platforms else []
        
        # Now that we have platforms, get train events for each platform
        result_platforms = []
        
        for platform in paginated_platforms:
            platform_id = platform['id']
            logger.info(f"Getting train events for platform {platform_id}")
            
            # Get all train events for this platform
            events_query = """
            WITH schedule_ids AS (
                -- Get schedule IDs for trains running on the selected date at this location and platform
                SELECT DISTINCT sl.schedule_id
                FROM (
                    -- Schedule locations from all tables with this platform
                    SELECT schedule_id, tiploc, platform FROM schedule_locations_ltp
                    WHERE tiploc = :location AND platform = :platform_id
                    
                    UNION ALL
                    
                    SELECT schedule_id, tiploc, platform FROM schedule_locations_stp_new
                    WHERE tiploc = :location AND platform = :platform_id
                    
                    UNION ALL
                    
                    SELECT schedule_id, tiploc, platform FROM schedule_locations_stp_overlay
                    WHERE tiploc = :location AND platform = :platform_id
                    
                    UNION ALL
                    
                    SELECT schedule_id, tiploc, platform FROM schedule_locations_stp_cancellation
                    WHERE tiploc = :location AND platform = :platform_id
                ) sl
            ),
            -- Apply STP precedence to get the correct schedule version
            schedules_with_precedence AS (
                -- Cancellations (highest precedence)
                SELECT 
                    sc.id, 
                    sc.uid, 
                    'C' as effective_stp, 
                    sc.train_identity,
                    sc.train_category,
                    sc.train_status,
                    1 as priority,
                    true as is_cancelled
                FROM 
                    schedules_stp_cancellation sc
                JOIN 
                    schedule_ids si ON sc.id = si.schedule_id
                WHERE 
                    :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                -- Overlays (second priority)
                SELECT 
                    sc.id, 
                    sc.uid, 
                    'O' as effective_stp, 
                    sc.train_identity,
                    sc.train_category,
                    sc.train_status,
                    2 as priority,
                    false as is_cancelled
                FROM 
                    schedules_stp_overlay sc
                JOIN 
                    schedule_ids si ON sc.id = si.schedule_id
                WHERE 
                    :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                -- New schedules (third priority)
                SELECT 
                    sc.id, 
                    sc.uid, 
                    'N' as effective_stp, 
                    sc.train_identity,
                    sc.train_category,
                    sc.train_status,
                    3 as priority,
                    false as is_cancelled
                FROM 
                    schedules_stp_new sc
                JOIN 
                    schedule_ids si ON sc.id = si.schedule_id
                WHERE 
                    :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                -- Permanent schedules (lowest priority)
                SELECT 
                    sc.id, 
                    sc.uid, 
                    'P' as effective_stp, 
                    sc.train_identity,
                    sc.train_category,
                    sc.train_status,
                    4 as priority,
                    false as is_cancelled
                FROM 
                    schedules_ltp sc
                JOIN 
                    schedule_ids si ON sc.id = si.schedule_id
                WHERE 
                    :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
            ),
            -- Get the highest precedence for each UID
            highest_precedence AS (
                SELECT uid, MIN(priority) as min_priority
                FROM schedules_with_precedence
                GROUP BY uid
            ),
            -- Final schedule list with STP precedence applied
            final_schedules AS (
                SELECT s.*
                FROM schedules_with_precedence s
                JOIN highest_precedence p 
                    ON s.uid = p.uid AND s.priority = p.min_priority
            )
            -- Get location data for all schedules
            SELECT 
                fs.id as schedule_id,
                fs.uid,
                fs.train_identity as headcode,
                fs.train_category as category,
                fs.train_status,
                COALESCE(sl.arr, '') as arrival_time,
                COALESCE(sl.dep, '') as departure_time,
                CASE WHEN sl.arr IS NOT NULL AND sl.dep IS NULL THEN true ELSE false END as is_terminating,
                CASE WHEN sl.arr IS NULL AND sl.dep IS NOT NULL THEN true ELSE false END as is_originating,
                fs.is_cancelled,
                fs.effective_stp as stp_indicator
            FROM final_schedules fs
            JOIN (
                -- Get locations for each schedule with platform matching
                SELECT * FROM schedule_locations_ltp
                WHERE tiploc = :location AND platform = :platform_id
                
                UNION ALL
                
                SELECT * FROM schedule_locations_stp_new
                WHERE tiploc = :location AND platform = :platform_id
                
                UNION ALL
                
                SELECT * FROM schedule_locations_stp_overlay
                WHERE tiploc = :location AND platform = :platform_id
                
                UNION ALL
                
                SELECT * FROM schedule_locations_stp_cancellation
                WHERE tiploc = :location AND platform = :platform_id
            ) sl ON fs.id = sl.schedule_id
            ORDER BY 
                CASE 
                    WHEN COALESCE(sl.arr, '') != '' THEN sl.arr
                    ELSE sl.dep
                END
            """
            
            # Get train events
            events_params = {
                "location": location_code,
                "platform_id": platform_id,
                "search_date": search_date,
                "day_position": day_position
            }
            
            events_result = session.execute(text(events_query), events_params)
            
            # Process train events
            events = []
            for row in events_result:
                event = {
                    "uid": row.uid,
                    "headcode": row.headcode,
                    "category": row.category,
                    "train_status": row.train_status
                }
                
                # Format arrival time as HHMM (4 characters) if it exists
                if row.arrival_time:
                    # Ensure it's a string and remove any non-digit characters
                    arr_time = str(row.arrival_time).replace(':', '').replace(' ', '')
                    # Pad to ensure it's 4 characters
                    if len(arr_time) == 3:
                        arr_time = '0' + arr_time
                    elif len(arr_time) == 1:
                        arr_time = '000' + arr_time
                    elif len(arr_time) == 2:
                        arr_time = '00' + arr_time
                    # Only use if it looks like a valid time
                    if len(arr_time) == 4 and arr_time.isdigit():
                        event["arrival_time"] = arr_time
                
                # Format departure time as HHMM (4 characters) if it exists  
                if row.departure_time:
                    # Ensure it's a string and remove any non-digit characters
                    dep_time = str(row.departure_time).replace(':', '').replace(' ', '')
                    # Pad to ensure it's 4 characters
                    if len(dep_time) == 3:
                        dep_time = '0' + dep_time
                    elif len(dep_time) == 1:
                        dep_time = '000' + dep_time
                    elif len(dep_time) == 2:
                        dep_time = '00' + dep_time
                    # Only use if it looks like a valid time
                    if len(dep_time) == 4 and dep_time.isdigit():
                        event["departure_time"] = dep_time
                
                if row.is_terminating:
                    event["is_terminating"] = True
                
                if row.is_originating:
                    event["is_originating"] = True
                
                if row.is_cancelled:
                    event["is_cancelled"] = True
                
                events.append(event)
            
            # Process train UIDs for associations
            train_uids = [event['uid'] for event in events if 'uid' in event]
            
            # If we have trains, enhance with association information
            if train_uids:
                # Query for all associations involving these trains at this location
                assoc_query = """
                WITH associated_trains AS (
                    -- Associations from LTP (permanent) table
                    SELECT 
                        a.main_uid, a.assoc_uid, a.category, a.location,
                        m.train_identity as main_headcode,
                        s.train_identity as assoc_headcode
                    FROM associations_ltp a
                    JOIN schedules_ltp m ON a.main_uid = m.uid
                    JOIN schedules_ltp s ON a.assoc_uid = s.uid
                    WHERE 
                        (a.main_uid = ANY(:train_uids) OR a.assoc_uid = ANY(:train_uids))
                        AND a.location = :tiploc
                        AND :search_date BETWEEN a.date_from AND a.date_to
                        AND SUBSTRING(a.days_run, :day_position, 1) = '1'
                    
                    UNION ALL
                    
                    -- Associations from STP New table
                    SELECT 
                        a.main_uid, a.assoc_uid, a.category, a.location,
                        m.train_identity as main_headcode,
                        s.train_identity as assoc_headcode
                    FROM associations_stp_new a
                    JOIN schedules_ltp m ON a.main_uid = m.uid
                    JOIN schedules_ltp s ON a.assoc_uid = s.uid
                    WHERE 
                        (a.main_uid = ANY(:train_uids) OR a.assoc_uid = ANY(:train_uids))
                        AND a.location = :tiploc
                        AND :search_date BETWEEN a.date_from AND a.date_to
                        AND SUBSTRING(a.days_run, :day_position, 1) = '1'
                )
                SELECT * FROM associated_trains
                """
                
                try:
                    # Execute association query
                    assoc_params = {
                        "train_uids": train_uids,
                        "tiploc": location_code,
                        "search_date": search_date,
                        "day_position": day_position
                    }
                    
                    assoc_results = session.execute(text(assoc_query), assoc_params)
                    logger.info(f"Assoc results = {assoc_results}")
                    
                    # Process the associations
                    for row in assoc_results:
                        # Find the main train and associated train
                        main_matches = [e for e in events if e.get('uid') == row.main_uid]
                        assoc_matches = [e for e in events if e.get('uid') == row.assoc_uid]
                        
                        # Update main train info
                        for train in main_matches:
                            train['has_associations'] = True
                            if row.category in ('JJ', 'VV','NP'):  # Join or divide
                                if 'forms_to_headcodes' not in train:
                                    train['forms_to_headcodes'] = []
                                train['forms_to_headcodes'].append(row.assoc_headcode)
                                train.setdefault('forms_to_uids',      []).append(row.assoc_uid)
                        
                        # Update associated train info
                        for train in assoc_matches:
                            train['has_associations'] = True
                            if row.category in ('JJ', 'VV','NP'):  # Join or divide
                                if 'forms_from_headcodes' not in train:
                                    train['forms_from_headcodes'] = []
                                train['forms_from_headcodes'].append(row.main_headcode)
                                train.setdefault('forms_from_uids',      []).append(row.main_uid)
                    
                except Exception as e:
                    logger.exception(f"Error processing associations: {str(e)}")
                    # Continue with the events we have without associations
            
            # Add platform with enhanced events to result
            result_platforms.append({
                "name": platform_id,
                "events": events
            })
            
        # Add detailed logging about what we're returning
        logger.info(f"Returning {len(result_platforms)} platforms with data")
        for platform in result_platforms:
            logger.info(f"Platform {platform['name']} has {len(platform['events'])} events")
        logger.info(result_platforms)
        # Return the result
        validation_errors = verify_platform_data(result_platforms)
        return jsonify({
            "platforms": result_platforms,
            "validation_errors": validation_errors,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "location": location_code,
            "date": date_str
        })
    
    except Exception as e:
        # Ensure connection is properly closed on error
        try:
            session.rollback()
        except:
            pass
        finally:
            try:
                session.close()
            except:
                pass
                
        logger.exception(f"Error fetching platform data: {str(e)}")
        return jsonify({"error": f"Error fetching platform data: {str(e)}"}), 500
    finally:
        # Always close the session
        try:
            session.close()
        except:
            pass

def verify_platform_data(platforms):
    """
    Runs two checks on the fully-built timeline data:
     1) For any “forms_from” link, the child must arrive **after** the parent departs.
     2) Both sides of every association must live on the same platform.
    Returns a list of human-readable error strings.
    """
    errors = []
    # first build a lookup of uid → platform name
    uid_to_platform = {}
    for plat in platforms:
        for ev in plat['events']:
            uid_to_platform[ev['uid']] = plat['name']

    for plat in platforms:
        pname = plat['name']
        for ev in plat['events']:
            # 1) check all forms_from links
            for parent_uid in ev.get('forms_from_headcodes', []):
                parent_plat = uid_to_platform.get(parent_uid)
                if parent_plat != pname:
                    errors.append(
                        f"Platform mismatch: train {ev['headcode']} (forms_from {parent_uid}) is on {pname} "
                        f"but parent {parent_uid!r} is on {parent_plat!r}."
                    )
                # timing rule:
                arr = ev.get('arrival_time')
                parent_dep = next(
                    (e['departure_time'] for e in plat['events'] if e['uid']==parent_uid),
                    None
                )
                if arr and parent_dep and arr < parent_dep:
                    errors.append(
                        f"Timing error: train {ev['headcode']} arrives at {arr} before its parent "
                        f"{parent_uid} departs at {parent_dep}."
                    )

            # 2) check all forms_to links
            for child_uid in ev.get('forms_to_headcodes', []):
                child_plat = uid_to_platform.get(child_uid)
                if child_plat != pname:
                    errors.append(
                        f"Platform mismatch: train {ev['headcode']} (forms_to {child_uid}) is on {pname} "
                        f"but child {child_uid!r} is on {child_plat!r}."
                    )
                # timing rule:
                dep = ev.get('departure_time')
                child_arr = next(
                    (e['arrival_time'] for e in plat['events'] if e['uid']==child_uid),
                    None
                )
                if dep and child_arr and child_arr < dep:
                    errors.append(
                        f"Timing error: child train {child_uid} arrives at {child_arr} before "
                        f"parent {ev['headcode']} departs at {dep}."
                    )
    return errors

def verify_train_event(event):
    """
    Verify a train event (for now, always returns True)

    Args:
        event: Train event dictionary

    Returns:
        Dictionary with 'verified' (bool) and 'message' (str)
    """
    # In a real system, this would validate the event against business rules
    return {
        'verified': True,
        'message': 'Event verified successfully'
    }

def get_platform_data(location, search_date):
    """
    Get platform data for a specific location and date

    Args:
        location: TIPLOC code
        search_date: Date object

    Returns:
        List of platform dictionaries with train events
    """
    day_of_week = search_date.weekday()
    day_position = day_of_week + 1  # CIF days_run uses 1-based positions
    
    # First get all platforms at this location
    platforms_query = """
    SELECT DISTINCT platform 
    FROM (
        SELECT platform FROM schedule_locations_ltp WHERE tiploc = :location
        UNION
        SELECT platform FROM schedule_locations_stp_new WHERE tiploc = :location
        UNION
        SELECT platform FROM schedule_locations_stp_overlay WHERE tiploc = :location
        UNION
        SELECT platform FROM schedule_locations_stp_cancellation WHERE tiploc = :location
    ) as platforms
    WHERE platform IS NOT NULL
    ORDER BY platform
    """
    
    platform_results = db.session.execute(text(platforms_query), {"location": location})
    
    platforms = []
    for row in platform_results:
        platforms.append({
            "id": row.platform,
            "name": row.platform,
            "events": []
        })
    
    return platforms
@web_bp.route('/db-status')
def db_status():
    """API endpoint to get database status information."""
    try:
        # Get current counts using the specific models
        from models import (ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
                          AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation)
        
        stats = {
            "success": True,
            "counts": {
                "permanent": db.session.query(ScheduleLTP).count(),
                "new": db.session.query(ScheduleSTPNew).count(),
                "overlay": db.session.query(ScheduleSTPOverlay).count(),
                "cancellation": db.session.query(ScheduleSTPCancellation).count()
            },
            "associations": {
                "permanent": db.session.query(AssociationLTP).count(),
                "new": db.session.query(AssociationSTPNew).count(),
                "overlay": db.session.query(AssociationSTPOverlay).count(),
                "cancellation": db.session.query(AssociationSTPCancellation).count()
            }
        }
        
        return jsonify(stats)
    except Exception as e:
        logger.exception(f"Error getting database status: {e}")
        return jsonify({"success": False, "error": str(e)})

@web_bp.route('/simulate-api-calls', methods=['POST'])
def simulate_api_calls():
    """Endpoint to trigger dummy API calls"""
    try:
        from api_simulator import simulate_realtime_step, simulate_forecast_update
        
        # Execute both API simulations
        realtime_result = simulate_realtime_step()
        forecast_result = simulate_forecast_update()
        
        return jsonify({
            "success": True,
            "message": "API simulation calls completed",
            "results": {
                "realtime_step": realtime_result,
                "forecast_update": forecast_result
            }
        })
    except Exception as e:
        logger.exception(f"Error simulating API calls: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Add the actual API endpoints that will receive the simulated calls
@web_bp.route('/api/realtime_update', methods=['POST'])
def realtime_update():
    """Mock endpoint for realtime updates"""
    try:
        # Check authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        token = auth_header.split(' ')[1]
        if token != "your-very-secret-key":
            return jsonify({"error": "Invalid API key"}), 401
        
        data = request.get_json()
        logger.info(f"Received realtime update: {data}")
        
        return jsonify({
            "success": True,
            "message": "Realtime update processed",
            "received_data": data,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.exception(f"Error processing realtime update: {e}")
        return jsonify({"error": str(e)}), 500

# Removed duplicate forecast_update endpoint - handled by api_active_trains.py
