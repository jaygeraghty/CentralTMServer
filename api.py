import logging
import re
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from flask import request, jsonify, Blueprint, Response, abort
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, text, union_all
from dataclasses import dataclass, field, asdict

from app import db
from models import (
    BasicSchedule, ScheduleLocation, Association,
    # STP-specific schedule tables
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    # STP-specific location tables
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, 
    ScheduleLocationSTPCancellation,
    # STP-specific association tables
    AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Blueprint
api_bp = Blueprint('api', __name__)

def get_locations_for_schedule(schedule_id, table_name):
    """
    Helper function to get locations for a schedule from the appropriate STP-specific location table
    
    Args:
        schedule_id: ID of the schedule
        table_name: Name of the table the schedule is in (e.g., 'schedules_ltp')
        
    Returns:
        List of location dictionaries
    """
    locations = []
    
    try:
        # Map schedule table to corresponding location table
        location_table_mapping = {
            'schedules_ltp': 'schedule_locations_ltp',
            'schedules_stp_new': 'schedule_locations_stp_new',
            'schedules_stp_overlay': 'schedule_locations_stp_overlay',
            'schedules_stp_cancellation': 'schedule_locations_stp_cancellation',
            'basic_schedules': 'schedule_locations'  # Legacy table fallback
        }
        
        if table_name not in location_table_mapping:
            logger.warning(f"Unknown table name: {table_name}")
            return locations
            
        location_table = location_table_mapping[table_name]
        
        # Query for locations
        query = f"SELECT * FROM {location_table} WHERE schedule_id = :schedule_id ORDER BY sequence ASC"
        results = db.session.execute(text(query), {'schedule_id': schedule_id}).fetchall()
        
        # Convert to dictionaries
        for row in results:
            location = {
                'sequence': row.sequence,
                'location_type': row.location_type,
                'tiploc': row.tiploc,
                'arr': row.arr,
                'dep': row.dep,
                'pass_time': row.pass_time,
                'public_arr': row.public_arr,
                'public_dep': row.public_dep,
                'platform': row.platform,
                'line': row.line,
                'path': row.path,
                'activity': row.activity,
                'engineering_allowance': getattr(row, 'engineering_allowance', None),
                'pathing_allowance': getattr(row, 'pathing_allowance', None),
                'performance_allowance': getattr(row, 'performance_allowance', None)
            }
            locations.append(location)
            
    except Exception as e:
        logger.exception(f"Error getting locations for schedule {schedule_id} from {table_name}: {str(e)}")
        # Return empty list on error
        return []
        
    return locations

@api_bp.route("/schedules")
def get_schedules():
    """
    Get schedules for a specific location and date.
    
    Query Parameters:
        location: TIPLOC code of the location
        date_str: Date in YYYY-MM-DD format
        platform: Optional platform code to filter by
        line: Optional line code to filter by
        path: Optional path code to filter by
        
    Returns:
        JSON response with schedules and associations
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
        
        # Get schedule data using direct database query with STP precedence
        schedules = []
        
        # Use the existing schedule query logic from get_schedules_for_multiple_locations
        day_of_week = search_date.weekday()
        day_position = day_of_week + 1  # CIF uses 1-based indexing
        
        # Build query with STP precedence (C > O > N > P)
        query = """
        WITH filtered_schedules AS (
            -- LTP schedules (permanent)
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path, 
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                'schedules_ltp' as source_table, 'P' as stp_indicator, 4 as precedence
            FROM schedules_ltp s
            JOIN schedule_locations_ltp ls ON s.id = ls.schedule_id
            WHERE ls.tiploc = :location
                AND :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTRING(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
            
            UNION ALL
            
            -- STP New schedules
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path,
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                'schedules_stp_new' as source_table, 'N' as stp_indicator, 3 as precedence
            FROM schedules_stp_new s
            JOIN schedule_locations_stp_new ls ON s.id = ls.schedule_id
            WHERE ls.tiploc = :location
                AND :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTRING(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
            
            UNION ALL
            
            -- STP Overlay schedules
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path,
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                'schedules_stp_overlay' as source_table, 'O' as stp_indicator, 2 as precedence
            FROM schedules_stp_overlay s
            JOIN schedule_locations_stp_overlay ls ON s.id = ls.schedule_id
            WHERE ls.tiploc = :location
                AND :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTRING(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
            
            UNION ALL
            
            -- STP Cancellation schedules
            SELECT 
                s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, s.days_run,
                s.train_status, s.train_category, s.power_type, s.timing_load,
                ls.arr, ls.dep, ls.pass_time, ls.platform, ls.line, ls.path,
                ls.activity, ls.public_arr, ls.public_dep, ls.tiploc,
                'schedules_stp_cancellation' as source_table, 'C' as stp_indicator, 1 as precedence
            FROM schedules_stp_cancellation s
            JOIN schedule_locations_stp_cancellation ls ON s.id = ls.schedule_id
            WHERE ls.tiploc = :location
                AND :search_date BETWEEN s.runs_from AND s.runs_to
                AND SUBSTRING(s.days_run, :day_position, 1) = '1'
                AND (:platform IS NULL OR ls.platform = :platform)
                AND (:line IS NULL OR ls.line = :line)
                AND (:path IS NULL OR ls.path = :path)
        ),
        best_precedence AS (
            SELECT uid, MIN(precedence) as min_precedence
            FROM filtered_schedules
            GROUP BY uid
        ),
        best_schedules AS (
            SELECT fs.*
            FROM filtered_schedules fs
            JOIN best_precedence bp ON fs.uid = bp.uid AND fs.precedence = bp.min_precedence
        )
        SELECT * FROM best_schedules
        ORDER BY CASE WHEN arr IS NOT NULL THEN arr ELSE dep END
        """
        
        params = {
            'location': location,
            'search_date': search_date,
            'day_position': day_position,
            'platform': platform,
            'line': line,
            'path': path
        }
        
        result = db.session.execute(text(query), params)
        
        for row in result:
            schedule = {
                'id': row.id,
                'uid': row.uid,
                'train_identity': row.train_identity,
                'runs_from': row.runs_from.isoformat() if row.runs_from else None,
                'runs_to': row.runs_to.isoformat() if row.runs_to else None,
                'days_run': row.days_run,
                'train_status': row.train_status,
                'train_category': row.train_category,
                'power_type': row.power_type,
                'timing_load': row.timing_load,
                'location': {
                    'tiploc': row.tiploc,
                    'arrival_time': row.arr,
                    'departure_time': row.dep,
                    'pass_time': row.pass_time,
                    'platform': row.platform,
                    'line': row.line,
                    'path': row.path,
                    'activity': row.activity,
                    'public_arrival': row.public_arr,
                    'public_departure': row.public_dep
                },
                'source_table': row.source_table,
                'stp_indicator': row.stp_indicator
            }
            schedules.append(schedule)
        
        # Format schedules for API response
        schedule_list = []
        schedule_map = {}  # For quick lookup when processing associations
        
        for schedule in schedules:
            # Create formatted schedule object
            formatted_schedule = {
                'uid': schedule['uid'],
                'stp_indicator': schedule['effective_stp_indicator'],
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
                'cancelled': schedule.get('is_cancelled', False),
                'locations': []
            }
            
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
                formatted_schedule['locations'].append(location_dict)
            
            # Add to results
            schedule_list.append(formatted_schedule)
            
            # Add to lookup map for associations
            schedule_map[schedule['uid']] = formatted_schedule
        
        # Get day of week (1=Monday, 7=Sunday)
        day_of_week = search_date.isoweekday()
        day_position = day_of_week  # 1=Monday, 7=Sunday (for SQL SUBSTR)
        
        # Now, handle associations with same approach as schedules
        # First, get all base associations
        base_assoc_query = """
        SELECT 
            a.id as association_id,
            a.main_uid,
            a.assoc_uid,
            a.category,
            a.date_from,
            a.date_to,
            a.days_run,
            a.location,
            a.base_suffix,
            a.assoc_suffix,
            a.date_indicator,
            a.stp_indicator,
            'associations_ltp' as source_table
        FROM 
            associations_ltp a
        WHERE 
            a.location = :location
            AND a.date_from <= :search_date
            AND a.date_to >= :search_date
            AND SUBSTR(a.days_run, :day_position, 1) = '1'
            
        UNION ALL
        
        SELECT 
            a.id as association_id,
            a.main_uid,
            a.assoc_uid,
            a.category,
            a.date_from,
            a.date_to,
            a.days_run,
            a.location,
            a.base_suffix,
            a.assoc_suffix,
            a.date_indicator,
            a.stp_indicator,
            'associations_stp_new' as source_table
        FROM 
            associations_stp_new a
        WHERE 
            a.location = :location
            AND a.date_from <= :search_date
            AND a.date_to >= :search_date
            AND SUBSTR(a.days_run, :day_position, 1) = '1'
        """
        
        # Parameters for the query
        params = {
            'location': location,
            'search_date': search_date,
            'day_position': day_position
        }
        
        # Get base associations
        base_assoc_results = db.session.execute(text(base_assoc_query), params).fetchall()
        
        # Process into dictionary form
        base_associations = []
        for row in base_assoc_results:
            assoc = {
                'association_id': row.association_id,
                'main_uid': row.main_uid,
                'assoc_uid': row.assoc_uid,
                'category': row.category,
                'date_from': row.date_from,
                'date_to': row.date_to,
                'days_run': row.days_run,
                'location': row.location,
                'base_suffix': row.base_suffix,
                'assoc_suffix': row.assoc_suffix,
                'date_indicator': row.date_indicator,
                'stp_indicator': row.stp_indicator,
                'source_table': row.source_table
            }
            base_associations.append(assoc)
        
        # For each base association, check for cancellations
        associations = []
        for assoc in base_associations:
            # First check for cancellations
            cancel_query = """
            SELECT COUNT(*) as count
            FROM associations_stp_cancellation
            WHERE main_uid = :main_uid
            AND assoc_uid = :assoc_uid
            AND location = :location
            AND date_from <= :search_date
            AND date_to >= :search_date
            AND SUBSTR(days_run, :day_position, 1) = '1'
            """
            
            cancel_params = {
                'main_uid': assoc['main_uid'],
                'assoc_uid': assoc['assoc_uid'],
                'location': assoc['location'],
                'search_date': search_date,
                'day_position': day_position
            }
            
            cancel_result = db.session.execute(text(cancel_query), cancel_params).fetchone()
            
            if cancel_result.count > 0:
                # Association is cancelled
                assoc['is_cancelled'] = True
                assoc['effective_stp_indicator'] = 'C'
            else:
                # Check for overlay
                overlay_query = """
                SELECT 
                    id as association_id,
                    main_uid,
                    assoc_uid,
                    category,
                    date_from,
                    date_to,
                    days_run,
                    location,
                    base_suffix,
                    assoc_suffix,
                    date_indicator,
                    stp_indicator
                FROM 
                    associations_stp_overlay
                WHERE 
                    main_uid = :main_uid
                    AND assoc_uid = :assoc_uid
                    AND location = :location
                    AND date_from <= :search_date
                    AND date_to >= :search_date
                    AND SUBSTR(days_run, :day_position, 1) = '1'
                """
                
                overlay_result = db.session.execute(text(overlay_query), cancel_params).fetchone()
                
                if overlay_result:
                    # Use the overlay instead
                    assoc = {
                        'association_id': overlay_result.association_id,
                        'main_uid': overlay_result.main_uid,
                        'assoc_uid': overlay_result.assoc_uid,
                        'category': overlay_result.category,
                        'date_from': overlay_result.date_from,
                        'date_to': overlay_result.date_to,
                        'days_run': overlay_result.days_run,
                        'location': overlay_result.location,
                        'base_suffix': overlay_result.base_suffix,
                        'assoc_suffix': overlay_result.assoc_suffix,
                        'date_indicator': overlay_result.date_indicator,
                        'stp_indicator': overlay_result.stp_indicator,
                        'source_table': 'associations_stp_overlay',
                        'is_overlay': True,
                        'effective_stp_indicator': 'O'
                    }
                else:
                    # No cancellation or overlay
                    assoc['is_cancelled'] = False
                    assoc['is_overlay'] = False
                    assoc['effective_stp_indicator'] = assoc['stp_indicator']
            
            # Format for API response
            formatted_assoc = {
                'main_uid': assoc['main_uid'],
                'assoc_uid': assoc['assoc_uid'],
                'category': assoc['category'],
                'date_from': assoc['date_from'].strftime("%Y-%m-%d") if assoc['date_from'] else None,
                'date_to': assoc['date_to'].strftime("%Y-%m-%d") if assoc['date_to'] else None,
                'days_run': assoc['days_run'],
                'location': assoc['location'],
                'base_suffix': assoc['base_suffix'],
                'assoc_suffix': assoc['assoc_suffix'],
                'date_indicator': assoc['date_indicator'],
                'stp_indicator': assoc['effective_stp_indicator'],
                'cancelled': assoc.get('is_cancelled', False)
            }
            
            # Try to add references to the actual schedules
            if assoc['main_uid'] in schedule_map:
                formatted_assoc['main_schedule'] = {
                    'uid': assoc['main_uid'],
                    'train_identity': schedule_map[assoc['main_uid']]['train_identity']
                }
            
            if assoc['assoc_uid'] in schedule_map:
                formatted_assoc['assoc_schedule'] = {
                    'uid': assoc['assoc_uid'],
                    'train_identity': schedule_map[assoc['assoc_uid']]['train_identity']
                }
            
            associations.append(formatted_assoc)
        
        # Return results
        return jsonify({
            'date': date_str,
            'location': location,
            'platform': platform,
            'line': line,
            'path': path,
            'schedules': schedule_list,
            'associations': associations
        })
        
    except Exception as e:
        logger.exception(f"Error in get_schedules: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


def get_schedules_for_multiple_locations(locations: List[str], search_date: date) -> List[Dict[str, Any]]:
    """
    Get schedules for multiple locations and a specific date.
    This function is used by the train graph viewer.
    
    Args:
        locations: List of TIPLOC location codes
        search_date: Date to search for schedules
        
    Returns:
        List of schedule dictionaries with all necessary details
    """
    try:
        # Process schedules for all requested locations
        all_schedules = []
        
        # Day of week for filtering
        day_of_week = search_date.weekday()
        day_position = day_of_week + 1  # 1-based for SQL SUBSTR
        
        # Create a session
        session = db.session
        
        # Create a set to track already added UIDs to avoid duplicates
        added_uids = set()
        
        # Query for schedules that run on the specified date and pass through any of the locations
        # Apply STP precedence rules: C > O > N > P
        for location in locations:
            try:
                schedules_query = """
                WITH combined_schedules AS (
                    -- Cancellations (highest precedence)
                    SELECT 
                        sc.id, 
                        sc.uid, 
                        sc.stp_indicator, 
                        sc.transaction_type, 
                        sc.runs_from, 
                        sc.runs_to, 
                        sc.days_run, 
                        sc.train_status, 
                        sc.train_category, 
                        sc.train_identity, 
                        sc.service_code,
                        sc.power_type,
                        sc.speed,
                        'schedules_stp_cancellation' as source_table,
                        1 as priority
                    FROM schedules_stp_cancellation sc
                    JOIN schedule_locations_stp_cancellation sl ON sc.id = sl.schedule_id
                    WHERE 
                        sl.tiploc = :location
                        AND :search_date BETWEEN sc.runs_from AND sc.runs_to
                        AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                        
                    UNION ALL
                    
                    -- Overlays (next precedence)
                    SELECT 
                        sc.id, 
                        sc.uid, 
                        sc.stp_indicator, 
                        sc.transaction_type, 
                        sc.runs_from, 
                        sc.runs_to, 
                        sc.days_run, 
                        sc.train_status, 
                        sc.train_category, 
                        sc.train_identity, 
                        sc.service_code,
                        sc.power_type,
                        sc.speed,
                        'schedules_stp_overlay' as source_table,
                        2 as priority
                    FROM schedules_stp_overlay sc
                    JOIN schedule_locations_stp_overlay sl ON sc.id = sl.schedule_id
                    WHERE 
                        sl.tiploc = :location
                        AND :search_date BETWEEN sc.runs_from AND sc.runs_to
                        AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                        AND NOT EXISTS (
                            SELECT 1 FROM schedules_stp_cancellation ssc
                            WHERE 
                                ssc.uid = sc.uid
                                AND :search_date BETWEEN ssc.runs_from AND ssc.runs_to
                                AND SUBSTR(ssc.days_run, :day_position, 1) = '1'
                        )
                        
                    UNION ALL
                    
                    -- New (next precedence)
                    SELECT 
                        sc.id, 
                        sc.uid, 
                        sc.stp_indicator, 
                        sc.transaction_type, 
                        sc.runs_from, 
                        sc.runs_to, 
                        sc.days_run, 
                        sc.train_status, 
                        sc.train_category, 
                        sc.train_identity, 
                        sc.service_code,
                        sc.power_type,
                        sc.speed,
                        'schedules_stp_new' as source_table,
                        3 as priority
                    FROM schedules_stp_new sc
                    JOIN schedule_locations_stp_new sl ON sc.id = sl.schedule_id
                    WHERE 
                        sl.tiploc = :location
                        AND :search_date BETWEEN sc.runs_from AND sc.runs_to
                        AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                        AND NOT EXISTS (
                            SELECT 1 FROM schedules_stp_cancellation ssc
                            WHERE 
                                ssc.uid = sc.uid
                                AND :search_date BETWEEN ssc.runs_from AND ssc.runs_to
                                AND SUBSTR(ssc.days_run, :day_position, 1) = '1'
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM schedules_stp_overlay sso
                            WHERE 
                                sso.uid = sc.uid
                                AND :search_date BETWEEN sso.runs_from AND sso.runs_to
                                AND SUBSTR(sso.days_run, :day_position, 1) = '1'
                        )
                        
                    UNION ALL
                    
                    -- Permanent (lowest precedence)
                    SELECT 
                        sc.id, 
                        sc.uid, 
                        sc.stp_indicator, 
                        sc.transaction_type, 
                        sc.runs_from, 
                        sc.runs_to, 
                        sc.days_run, 
                        sc.train_status, 
                        sc.train_category, 
                        sc.train_identity, 
                        sc.service_code,
                        sc.power_type,
                        sc.speed,
                        'schedules_ltp' as source_table,
                        4 as priority
                    FROM schedules_ltp sc
                    JOIN schedule_locations_ltp sl ON sc.id = sl.schedule_id
                    WHERE 
                        sl.tiploc = :location
                        AND :search_date BETWEEN sc.runs_from AND sc.runs_to
                        AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                        AND NOT EXISTS (
                            SELECT 1 FROM schedules_stp_cancellation ssc
                            WHERE 
                                ssc.uid = sc.uid
                                AND :search_date BETWEEN ssc.runs_from AND ssc.runs_to
                                AND SUBSTR(ssc.days_run, :day_position, 1) = '1'
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM schedules_stp_overlay sso
                            WHERE 
                                sso.uid = sc.uid
                                AND :search_date BETWEEN sso.runs_from AND sso.runs_to
                                AND SUBSTR(sso.days_run, :day_position, 1) = '1'
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM schedules_stp_new ssn
                            WHERE 
                                ssn.uid = sc.uid
                                AND :search_date BETWEEN ssn.runs_from AND ssn.runs_to
                                AND SUBSTR(ssn.days_run, :day_position, 1) = '1'
                        )
                )
                SELECT * FROM combined_schedules
                ORDER BY priority ASC
                """
                
                # Execute query with parameters
                query_params = {
                    'location': location,
                    'search_date': search_date,
                    'day_position': day_position
                }
                
                # Execute the query
                schedules_result = session.execute(text(schedules_query), query_params).fetchall()
                
                # Process each schedule
                for schedule_row in schedules_result:
                    # Skip if we already have this UID (avoid duplicates from multiple locations)
                    if schedule_row.uid in added_uids:
                        continue
                    
                    # Mark this UID as processed
                    added_uids.add(schedule_row.uid)
                    
                    # Convert result to dict
                    schedule_dict = {
                        'id': schedule_row.id,
                        'uid': schedule_row.uid,
                        'stp_indicator': schedule_row.stp_indicator,
                        'transaction_type': schedule_row.transaction_type,
                        'runs_from': schedule_row.runs_from.isoformat() if schedule_row.runs_from else None,
                        'runs_to': schedule_row.runs_to.isoformat() if schedule_row.runs_to else None,
                        'days_run': schedule_row.days_run,
                        'train_status': schedule_row.train_status,
                        'train_category': schedule_row.train_category,
                        'train_identity': schedule_row.train_identity,
                        'service_code': schedule_row.service_code,
                        'power_type': schedule_row.power_type,
                        'speed': schedule_row.speed,
                        'source_table': schedule_row.source_table,
                        'locations': [],  # Will be filled with location data
                        'associations': [],  # Will be filled with association data
                        'cancelled': schedule_row.stp_indicator == 'C'
                    }
                    
                    # Get locations for this schedule
                    locations_data = get_locations_for_schedule(schedule_row.id, schedule_row.source_table)
                    
                    # Format times properly
                    for loc in locations_data:
                        if loc['arr']:
                            loc['arr'] = loc['arr'].strftime('%H:%M') if hasattr(loc['arr'], 'strftime') else loc['arr']
                        if loc['dep']:
                            loc['dep'] = loc['dep'].strftime('%H:%M') if hasattr(loc['dep'], 'strftime') else loc['dep']
                        if loc['pass_time']:
                            loc['pass_time'] = loc['pass_time'].strftime('%H:%M') if hasattr(loc['pass_time'], 'strftime') else loc['pass_time']
                        if loc['public_arr']:
                            loc['public_arr'] = loc['public_arr'].strftime('%H:%M') if hasattr(loc['public_arr'], 'strftime') else loc['public_arr']
                        if loc['public_dep']:
                            loc['public_dep'] = loc['public_dep'].strftime('%H:%M') if hasattr(loc['public_dep'], 'strftime') else loc['public_dep']
                    
                    schedule_dict['locations'] = locations_data
                    
                    # Add this schedule to our results
                    all_schedules.append(schedule_dict)
            
            except Exception as e:
                logger.exception(f"Error processing schedules for location {location}: {str(e)}")
        
        # Process associations for all schedules
        for schedule in all_schedules:
            try:
                # Get associations for this schedule
                assoc_query = """
                WITH combined_associations AS (
                    -- Cancellations (highest precedence)
                    SELECT 
                        a.id, 
                        a.main_uid, 
                        a.assoc_uid, 
                        a.date_from, 
                        a.date_to, 
                        a.days_run, 
                        a.category, 
                        a.date_indicator, 
                        a.location, 
                        a.base_suffix,
                        a.assoc_suffix,
                        a.stp_indicator,
                        'associations_stp_cancellation' as source_table,
                        1 as priority
                    FROM associations_stp_cancellation a
                    WHERE 
                        (a.main_uid = :uid OR a.assoc_uid = :uid)
                        AND :search_date BETWEEN a.date_from AND a.date_to
                        AND SUBSTR(a.days_run, :day_position, 1) = '1'
                        
                    UNION ALL
                    
                    -- Overlays (next precedence)
                    SELECT 
                        a.id, 
                        a.main_uid, 
                        a.assoc_uid, 
                        a.date_from, 
                        a.date_to, 
                        a.days_run, 
                        a.category, 
                        a.date_indicator, 
                        a.location, 
                        a.base_suffix,
                        a.assoc_suffix,
                        a.stp_indicator,
                        'associations_stp_overlay' as source_table,
                        2 as priority
                    FROM associations_stp_overlay a
                    WHERE 
                        (a.main_uid = :uid OR a.assoc_uid = :uid)
                        AND :search_date BETWEEN a.date_from AND a.date_to
                        AND SUBSTR(a.days_run, :day_position, 1) = '1'
                        AND NOT EXISTS (
                            SELECT 1 FROM associations_stp_cancellation asc
                            WHERE 
                                (asc.main_uid = a.main_uid AND asc.assoc_uid = a.assoc_uid)
                                AND :search_date BETWEEN asc.date_from AND asc.date_to
                                AND SUBSTR(asc.days_run, :day_position, 1) = '1'
                        )
                        
                    UNION ALL
                    
                    -- New (next precedence)
                    SELECT 
                        a.id, 
                        a.main_uid, 
                        a.assoc_uid, 
                        a.date_from, 
                        a.date_to, 
                        a.days_run, 
                        a.category, 
                        a.date_indicator, 
                        a.location, 
                        a.base_suffix,
                        a.assoc_suffix,
                        a.stp_indicator,
                        'associations_stp_new' as source_table,
                        3 as priority
                    FROM associations_stp_new a
                    WHERE 
                        (a.main_uid = :uid OR a.assoc_uid = :uid)
                        AND :search_date BETWEEN a.date_from AND a.date_to
                        AND SUBSTR(a.days_run, :day_position, 1) = '1'
                        AND NOT EXISTS (
                            SELECT 1 FROM associations_stp_cancellation asc
                            WHERE 
                                (asc.main_uid = a.main_uid AND asc.assoc_uid = a.assoc_uid)
                                AND :search_date BETWEEN asc.date_from AND asc.date_to
                                AND SUBSTR(asc.days_run, :day_position, 1) = '1'
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM associations_stp_overlay aso
                            WHERE 
                                (aso.main_uid = a.main_uid AND aso.assoc_uid = a.assoc_uid)
                                AND :search_date BETWEEN aso.date_from AND aso.date_to
                                AND SUBSTR(aso.days_run, :day_position, 1) = '1'
                        )
                        
                    UNION ALL
                    
                    -- Permanent (lowest precedence)
                    SELECT 
                        a.id, 
                        a.main_uid, 
                        a.assoc_uid, 
                        a.date_from, 
                        a.date_to, 
                        a.days_run, 
                        a.category, 
                        a.date_indicator, 
                        a.location, 
                        a.base_suffix,
                        a.assoc_suffix,
                        a.stp_indicator,
                        'associations_ltp' as source_table,
                        4 as priority
                    FROM associations_ltp a
                    WHERE 
                        (a.main_uid = :uid OR a.assoc_uid = :uid)
                        AND :search_date BETWEEN a.date_from AND a.date_to
                        AND SUBSTR(a.days_run, :day_position, 1) = '1'
                        AND NOT EXISTS (
                            SELECT 1 FROM associations_stp_cancellation asc
                            WHERE 
                                (asc.main_uid = a.main_uid AND asc.assoc_uid = a.assoc_uid)
                                AND :search_date BETWEEN asc.date_from AND asc.date_to
                                AND SUBSTR(asc.days_run, :day_position, 1) = '1'
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM associations_stp_overlay aso
                            WHERE 
                                (aso.main_uid = a.main_uid AND aso.assoc_uid = a.assoc_uid)
                                AND :search_date BETWEEN aso.date_from AND aso.date_to
                                AND SUBSTR(aso.days_run, :day_position, 1) = '1'
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM associations_stp_new asn
                            WHERE 
                                (asn.main_uid = a.main_uid AND asn.assoc_uid = a.assoc_uid)
                                AND :search_date BETWEEN asn.date_from AND asn.date_to
                                AND SUBSTR(asn.days_run, :day_position, 1) = '1'
                        )
                )
                SELECT * FROM combined_associations
                ORDER BY priority ASC
                """
                
                # Execute query with parameters
                assoc_params = {
                    'uid': schedule['uid'],
                    'search_date': search_date,
                    'day_position': day_position
                }
                
                # Execute the query
                assoc_result = session.execute(text(assoc_query), assoc_params).fetchall()
                
                # Process each association
                for assoc_row in assoc_result:
                    # Convert result to dict
                    assoc_dict = {
                        'id': assoc_row.id,
                        'main_uid': assoc_row.main_uid,
                        'assoc_uid': assoc_row.assoc_uid,
                        'date_from': assoc_row.date_from.isoformat() if assoc_row.date_from else None,
                        'date_to': assoc_row.date_to.isoformat() if assoc_row.date_to else None,
                        'days_run': assoc_row.days_run,
                        'category': assoc_row.category,
                        'date_indicator': assoc_row.date_indicator,
                        'location': assoc_row.location,
                        'base_suffix': assoc_row.base_suffix,
                        'assoc_suffix': assoc_row.assoc_suffix,
                        'stp_indicator': assoc_row.stp_indicator,
                        'source_table': assoc_row.source_table
                    }
                    
                    # Add to schedule associations
                    schedule['associations'].append(assoc_dict)
            
            except Exception as e:
                logger.exception(f"Error processing associations for schedule {schedule['uid']}: {str(e)}")
        
        return all_schedules
        
    except Exception as e:
        logger.exception(f"Error in get_schedules_for_multiple_locations: {str(e)}")
        return []

# Active trains functionality removed - now handled in api_active_trains.py

@api_bp.route("/db_status")
def get_db_status():
    """
    Get current database status showing counts of different schedule and association types.
    
    Returns:
        JSON response with counts of schedules and associations by STP indicator
    """
    try:
        # Count schedules by STP indicator
        ltp_schedules = db.session.query(func.count(ScheduleLTP.id)).scalar() or 0
        stp_new_schedules = db.session.query(func.count(ScheduleSTPNew.id)).scalar() or 0
        stp_overlay_schedules = db.session.query(func.count(ScheduleSTPOverlay.id)).scalar() or 0
        stp_cancellation_schedules = db.session.query(func.count(ScheduleSTPCancellation.id)).scalar() or 0
        
        # Count associations by STP indicator
        ltp_associations = db.session.query(func.count(AssociationLTP.id)).scalar() or 0
        stp_new_associations = db.session.query(func.count(AssociationSTPNew.id)).scalar() or 0
        stp_overlay_associations = db.session.query(func.count(AssociationSTPOverlay.id)).scalar() or 0
        stp_cancellation_associations = db.session.query(func.count(AssociationSTPCancellation.id)).scalar() or 0
        
        # Count legacy table records (for backward compatibility)
        legacy_schedules = db.session.query(func.count(BasicSchedule.id)).scalar() or 0
        legacy_locations = db.session.query(func.count(ScheduleLocation.id)).scalar() or 0
        legacy_associations = db.session.query(func.count(Association.id)).scalar() or 0
        
        # Total STP-specific locations
        ltp_locations = db.session.query(func.count(ScheduleLocationLTP.id)).scalar() or 0
        stp_new_locations = db.session.query(func.count(ScheduleLocationSTPNew.id)).scalar() or 0
        stp_overlay_locations = db.session.query(func.count(ScheduleLocationSTPOverlay.id)).scalar() or 0
        stp_cancellation_locations = db.session.query(func.count(ScheduleLocationSTPCancellation.id)).scalar() or 0
        
        # Format response
        return jsonify({
            "schedules": {
                "ltp": ltp_schedules,
                "stp_new": stp_new_schedules,
                "stp_overlay": stp_overlay_schedules,
                "stp_cancellation": stp_cancellation_schedules,
                "total": ltp_schedules + stp_new_schedules + stp_overlay_schedules + stp_cancellation_schedules
            },
            "associations": {
                "ltp": ltp_associations,
                "stp_new": stp_new_associations,
                "stp_overlay": stp_overlay_associations,
                "stp_cancellation": stp_cancellation_associations,
                "total": ltp_associations + stp_new_associations + stp_overlay_associations + stp_cancellation_associations
            },
            "legacy": {
                "schedules": legacy_schedules,
                "locations": legacy_locations,
                "associations": legacy_associations
            },
            "locations": {
                "ltp": ltp_locations,
                "stp_new": stp_new_locations,
                "stp_overlay": stp_overlay_locations,
                "stp_cancellation": stp_cancellation_locations,
                "total": ltp_locations + stp_new_locations + stp_overlay_locations + stp_cancellation_locations
            }
        })
    except Exception as e:
        logger.exception(f"Error in get_db_status: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@api_bp.route('/platform_docker', methods=['POST'])
def platform_docker_data():
    """
    Enhanced platform docker data endpoint with proper STP precedence handling.
    
    JSON Body:
        location: TIPLOC code
        date: Date in YYYY-MM-DD format
        page: Page number (optional, default 1)
        per_page: Items per page (optional, default 10)
        
    Returns:
        JSON with platform data and train events
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    import os
    
    # Create database session
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return jsonify({'error': 'Database URL not configured'}), 500
        
    engine = create_engine(db_url, 
                          pool_recycle=300, 
                          pool_pre_ping=True,
                          connect_args={"connect_timeout": 15})
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        params = request.get_json()
        
        location_code = params.get('location')
        date_str = params.get('date')
        page = int(params.get('page', 1))
        per_page = int(params.get('per_page', 10))
        
        if not location_code or not date_str:
            return jsonify({
                'error': 'Missing required parameters: location and date'
            }), 400
            
        # Parse and standardize date format
        try:
            if '-' not in date_str and len(date_str) == 8:
                # Handle YYYYMMDD format
                year = int(date_str[0:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                search_date = date(year, month, day)
                date_str = search_date.strftime('%Y-%m-%d')
            else:
                search_date = date.fromisoformat(date_str)
                date_str = search_date.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            return jsonify({'error': f'Invalid date format: {date_str}. Use YYYY-MM-DD format.'}), 400
        
        day_of_week = search_date.weekday()
        day_position = day_of_week + 1
        offset = (page - 1) * per_page
        
        logger.info(f"Getting platform docker data for {location_code} on {date_str}")
        
        # Get platforms with STP precedence handling
        platforms_query = """
        WITH schedule_ids AS (
            SELECT DISTINCT sl.schedule_id, sl.platform
            FROM (
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
        ),
        schedules_with_precedence AS (
            SELECT 
                sc.id, sc.uid, 'C' as effective_stp, 1 as priority,
                si.platform
            FROM schedules_stp_cancellation sc
            JOIN schedule_ids si ON sc.id = si.schedule_id
            WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_position, 1) = '1'
            
            UNION ALL
            
            SELECT 
                sc.id, sc.uid, 'O' as effective_stp, 2 as priority,
                si.platform
            FROM schedules_stp_overlay sc
            JOIN schedule_ids si ON sc.id = si.schedule_id
            WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_position, 1) = '1'
            
            UNION ALL
            
            SELECT 
                sc.id, sc.uid, 'N' as effective_stp, 3 as priority,
                si.platform
            FROM schedules_stp_new sc
            JOIN schedule_ids si ON sc.id = si.schedule_id
            WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_position, 1) = '1'
            
            UNION ALL
            
            SELECT 
                sc.id, sc.uid, 'P' as effective_stp, 4 as priority,
                si.platform
            FROM schedules_ltp sc
            JOIN schedule_ids si ON sc.id = si.schedule_id
            WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_position, 1) = '1'
        ),
        highest_precedence AS (
            SELECT uid, MIN(priority) as min_priority
            FROM schedules_with_precedence
            GROUP BY uid
        ),
        final_schedules AS (
            SELECT s.*
            FROM schedules_with_precedence s
            JOIN highest_precedence p 
                ON s.uid = p.uid AND s.priority = p.min_priority
        )
        SELECT 
            COALESCE(platform, 'Unknown') as platform_id,
            COUNT(*) as train_count
        FROM final_schedules
        GROUP BY COALESCE(platform, 'Unknown')
        ORDER BY 
            CASE 
                WHEN COALESCE(platform, 'Unknown') ~ '^[0-9]+$' 
                THEN CAST(COALESCE(platform, 'Unknown') AS INTEGER)
                ELSE 9999
            END,
            COALESCE(platform, 'Unknown')
        """
        
        platform_results = session.execute(
            text(platforms_query),
            {
                "location": location_code,
                "search_date": search_date,
                "day_position": day_position
            }
        )
        
        platforms = []
        for row in platform_results:
            platforms.append({
                "id": row.platform_id,
                "name": row.platform_id,
                "train_count": row.train_count
            })
            
        # Apply pagination
        paginated_platforms = platforms[offset:offset + per_page] if platforms else []
        
        # Get train events for each platform
        result_platforms = []
        
        for platform in paginated_platforms:
            platform_id = platform['id']
            
            # Get detailed train events for this platform
            events_query = """
            WITH schedule_ids AS (
                SELECT DISTINCT sl.schedule_id
                FROM (
                    SELECT schedule_id FROM schedule_locations_ltp
                    WHERE tiploc = :location AND platform = :platform_id
                    
                    UNION ALL
                    
                    SELECT schedule_id FROM schedule_locations_stp_new
                    WHERE tiploc = :location AND platform = :platform_id
                    
                    UNION ALL
                    
                    SELECT schedule_id FROM schedule_locations_stp_overlay
                    WHERE tiploc = :location AND platform = :platform_id
                    
                    UNION ALL
                    
                    SELECT schedule_id FROM schedule_locations_stp_cancellation
                    WHERE tiploc = :location AND platform = :platform_id
                ) sl
            ),
            schedules_with_precedence AS (
                SELECT 
                    sc.id, sc.uid, 'C' as effective_stp, sc.train_identity,
                    sc.train_category, sc.train_status, 1 as priority, 
                    true as is_cancelled
                FROM schedules_stp_cancellation sc
                JOIN schedule_ids si ON sc.id = si.schedule_id
                WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                SELECT 
                    sc.id, sc.uid, 'O' as effective_stp, sc.train_identity,
                    sc.train_category, sc.train_status, 2 as priority, 
                    false as is_cancelled
                FROM schedules_stp_overlay sc
                JOIN schedule_ids si ON sc.id = si.schedule_id
                WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                SELECT 
                    sc.id, sc.uid, 'N' as effective_stp, sc.train_identity,
                    sc.train_category, sc.train_status, 3 as priority, 
                    false as is_cancelled
                FROM schedules_stp_new sc
                JOIN schedule_ids si ON sc.id = si.schedule_id
                WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
                
                UNION ALL
                
                SELECT 
                    sc.id, sc.uid, 'P' as effective_stp, sc.train_identity,
                    sc.train_category, sc.train_status, 4 as priority, 
                    false as is_cancelled
                FROM schedules_ltp sc
                JOIN schedule_ids si ON sc.id = si.schedule_id
                WHERE :search_date BETWEEN sc.runs_from AND sc.runs_to
                    AND SUBSTR(sc.days_run, :day_position, 1) = '1'
            ),
            highest_precedence AS (
                SELECT uid, MIN(priority) as min_priority
                FROM schedules_with_precedence
                GROUP BY uid
            ),
            final_schedules AS (
                SELECT s.*
                FROM schedules_with_precedence s
                JOIN highest_precedence p 
                    ON s.uid = p.uid AND s.priority = p.min_priority
            )
            SELECT 
                fs.id as schedule_id, fs.uid, fs.train_identity as headcode,
                fs.train_category as category, fs.train_status,
                COALESCE(sl.arr, '') as arrival_time,
                COALESCE(sl.dep, '') as departure_time,
                CASE WHEN sl.arr IS NOT NULL AND sl.dep IS NULL THEN true ELSE false END as is_terminating,
                CASE WHEN sl.arr IS NULL AND sl.dep IS NOT NULL THEN true ELSE false END as is_originating,
                fs.is_cancelled, fs.effective_stp as stp_indicator
            FROM final_schedules fs
            JOIN (
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
                    WHEN sl.arr IS NOT NULL THEN sl.arr
                    ELSE sl.dep
                END
            """
            
            events_params = {
                "location": location_code,
                "platform_id": platform_id,
                "search_date": search_date,
                "day_position": day_position
            }
            
            events_result = session.execute(text(events_query), events_params)
            
            events = []
            for row in events_result:
                event = {
                    "uid": row.uid,
                    "headcode": row.headcode,
                    "category": row.category,
                    "train_status": row.train_status,
                    "has_associations": False,
                    "forms_from_headcodes": [],
                    "forms_to_headcodes": []
                }
                
                # Format times as HHMM
                if row.arrival_time:
                    arr_time = str(row.arrival_time).replace(':', '').replace(' ', '')
                    if len(arr_time) == 3:
                        arr_time = '0' + arr_time
                    elif len(arr_time) == 1:
                        arr_time = '000' + arr_time
                    elif len(arr_time) == 2:
                        arr_time = '00' + arr_time
                    if len(arr_time) == 4 and arr_time.isdigit():
                        event["arrival_time"] = arr_time
                
                if row.departure_time:
                    dep_time = str(row.departure_time).replace(':', '').replace(' ', '')
                    if len(dep_time) == 3:
                        dep_time = '0' + dep_time
                    elif len(dep_time) == 1:
                        dep_time = '000' + dep_time
                    elif len(dep_time) == 2:
                        dep_time = '00' + dep_time
                    if len(dep_time) == 4 and dep_time.isdigit():
                        event["departure_time"] = dep_time
                
                if row.is_terminating:
                    event["is_terminating"] = True
                
                if row.is_originating:
                    event["is_originating"] = True
                
                if row.is_cancelled:
                    event["is_cancelled"] = True
                
                events.append(event)
            
            result_platforms.append({
                "name": platform_id,
                "events": events
            })
        
        return jsonify({
            'platforms': result_platforms,
            'location': location_code,
            'date': date_str,
            'page': page,
            'per_page': per_page,
            'total_platforms': len(platforms)
        })
        
    except Exception as e:
        logger.exception(f"Error getting platform docker data: {str(e)}")
        return jsonify({
            'error': 'Failed to retrieve platform docker data',
            'message': str(e)
        }), 500
    finally:
        session.close()

@api_bp.route('/train_graph_schedules', methods=['POST'])
def train_graph_schedules():
    """
    Get schedules for multiple locations (train graph functionality).
    
    JSON Body:
        locations: Array of TIPLOC codes
        date: Date in YYYY-MM-DD format
        
    Returns:
        JSON with schedules for all specified locations
    """
    try:
        data = request.get_json()
        locations = data.get('locations', [])
        date_str = data.get('date')
        
        if not locations:
            return jsonify({'error': 'No locations specified'}), 400
        
        if not date_str:
            return jsonify({'error': 'No date specified'}), 400
        
        search_date = date.fromisoformat(date_str)
        
        # Get schedules for all locations
        all_schedules = get_schedules_for_multiple_locations(locations, search_date)
        
        return jsonify({
            'schedules': all_schedules,
            'locations': locations,
            'date': date_str,
            'count': len(all_schedules)
        })
        
    except Exception as e:
        logger.exception(f"Error getting train graph schedules: {str(e)}")
        return jsonify({'error': str(e)}), 500