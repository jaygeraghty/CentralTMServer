"""
Functions to apply STP overlays and cancellations to a set of base schedules.
"""
from typing import List, Dict, Any, Optional
from datetime import date
import logging
from sqlalchemy import text
from app import db
from stp_utils import STP_INDICATORS

# Configure logging
logger = logging.getLogger(__name__)

def check_for_cancellations(base_schedules: List[Dict[str, Any]], search_date: date) -> List[Dict[str, Any]]:
    """
    Check if any of the base schedules are cancelled on the specified date.
    
    Args:
        base_schedules: List of base schedule dictionaries (from LTP and N schedules)
        search_date: The date to check for cancellations
        
    Returns:
        List of schedules with cancellation flags applied
    """
    if not base_schedules:
        return []
    
    # Extract all UIDs from base schedules
    uids = [schedule['uid'] for schedule in base_schedules]
    if not uids:
        return base_schedules
    
    # Get day of week (1=Monday, 7=Sunday)
    day_of_week = search_date.isoweekday()
    day_mask_position = day_of_week - 1  # 0=Monday, 6=Sunday in array
    
    # Query cancellations for these UIDs on this date
    query = f"""
    SELECT 
        uid, 
        runs_from, 
        runs_to, 
        days_run
    FROM 
        schedules_stp_cancellation
    WHERE 
        uid IN ({', '.join([f"'{uid}'" for uid in uids])})
        AND runs_from <= :search_date
        AND runs_to >= :search_date
        AND SUBSTRING(days_run, :day_position, 1) = '1'
    """
    
    params = {
        'search_date': search_date,
        'day_position': day_mask_position + 1
    }
    
    try:
        results = db.session.execute(text(query), params).fetchall()
        
        # Create a set of cancelled UIDs for quick lookup
        cancelled_uids = {row.uid for row in results}
        
        # Mark schedules as cancelled or not
        for schedule in base_schedules:
            if schedule['uid'] in cancelled_uids:
                schedule['is_cancelled'] = True
                schedule['effective_stp_indicator'] = 'C'
            else:
                schedule['is_cancelled'] = False
                schedule['effective_stp_indicator'] = schedule['stp_indicator']
        
        return base_schedules
        
    except Exception as e:
        logger.exception(f"Error checking for cancellations: {str(e)}")
        # Return original schedules without cancellation info on error
        return base_schedules

def apply_overlays(base_schedules: List[Dict[str, Any]], search_date: date) -> List[Dict[str, Any]]:
    """
    Apply overlay (STP indicator 'O') records to the base schedules.
    
    Args:
        base_schedules: List of base schedule dictionaries (potentially with cancellation flags)
        search_date: The date to check for overlays
        
    Returns:
        Updated list of schedules with overlays applied
    """
    if not base_schedules:
        return []
    
    # Extract all UIDs from base schedules that aren't already cancelled
    uids = [schedule['uid'] for schedule in base_schedules if not schedule.get('is_cancelled', False)]
    if not uids:
        return base_schedules
    
    # Get day of week (1=Monday, 7=Sunday)
    day_of_week = search_date.isoweekday()
    day_mask_position = day_of_week - 1  # 0=Monday, 6=Sunday in array
    
    # Query overlays for these UIDs on this date
    query = f"""
    SELECT 
        s.id as schedule_id,
        s.uid,
        s.stp_indicator,
        s.train_status,
        s.train_category,
        s.train_identity,
        s.service_code,
        s.power_type,
        s.speed,
        s.operating_chars,
        s.days_run,
        s.runs_from,
        s.runs_to,
        'schedules_stp_overlay' as source_table
    FROM 
        schedules_stp_overlay s
    WHERE 
        s.uid IN ({', '.join([f"'{uid}'" for uid in uids])})
        AND s.runs_from <= :search_date
        AND s.runs_to >= :search_date
        AND SUBSTRING(s.days_run, :day_position, 1) = '1'
    """
    
    params = {
        'search_date': search_date,
        'day_position': day_mask_position + 1
    }
    
    try:
        results = db.session.execute(text(query), params).fetchall()
        
        # Convert overlay results to dictionaries
        overlays = []
        for row in results:
            overlay_dict = {
                'schedule_id': row.schedule_id,
                'uid': row.uid,
                'stp_indicator': row.stp_indicator,
                'train_status': row.train_status,
                'train_category': row.train_category,
                'train_identity': row.train_identity,
                'service_code': row.service_code,
                'power_type': row.power_type,
                'speed': row.speed,
                'operating_chars': row.operating_chars,
                'days_run': row.days_run,
                'runs_from': row.runs_from,
                'runs_to': row.runs_to,
                'source_table': row.source_table,
                'stp_precedence': STP_INDICATORS['O']['precedence'],
                'effective_stp_indicator': 'O',
                'is_overlay': True
            }
            overlays.append(overlay_dict)
        
        # If no overlays found, return original schedules
        if not overlays:
            return base_schedules
            
        # Create a dictionary of overlays by UID for quick lookup
        overlay_dict = {overlay['uid']: overlay for overlay in overlays}
        
        # Create a new result list
        result_schedules = []
        
        # Apply overlays to base schedules
        for schedule in base_schedules:
            uid = schedule['uid']
            
            # If schedule is already cancelled, keep it as is
            if schedule.get('is_cancelled', False):
                result_schedules.append(schedule)
                continue
                
            # If there's an overlay for this UID, use it instead
            if uid in overlay_dict:
                result_schedules.append(overlay_dict[uid])
            else:
                # No overlay, keep the original
                if 'effective_stp_indicator' not in schedule:
                    schedule['effective_stp_indicator'] = schedule['stp_indicator']
                result_schedules.append(schedule)
        
        return result_schedules
        
    except Exception as e:
        logger.exception(f"Error applying overlays: {str(e)}")
        # Return original schedules without overlay info on error
        return base_schedules

def get_locations_for_schedule(schedule: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Get locations for a schedule based on its source table.
    
    Args:
        schedule: Schedule dictionary with source_table and schedule_id
        
    Returns:
        List of location dictionaries
    """
    if not schedule or 'source_table' not in schedule or 'schedule_id' not in schedule:
        return []
        
    source_table = schedule['source_table']
    schedule_id = schedule['schedule_id']
    
    # Map schedule tables to location tables
    location_table_mapping = {
        'schedules_ltp': 'schedule_locations_ltp',
        'schedules_stp_new': 'schedule_locations_stp_new',
        'schedules_stp_overlay': 'schedule_locations_stp_overlay',
        'schedules_stp_cancellation': 'schedule_locations_stp_cancellation',
        'basic_schedules': 'schedule_locations'  # Legacy fallback
    }
    
    if source_table not in location_table_mapping:
        logger.warning(f"Unknown source table: {source_table}")
        return []
        
    location_table = location_table_mapping[source_table]
    
    # Query locations
    query = f"""
    SELECT
        sequence,
        location_type,
        tiploc,
        arr,
        dep,
        pass_time,
        public_arr,
        public_dep,
        platform,
        line,
        path,
        activity
    FROM
        {location_table}
    WHERE
        schedule_id = :schedule_id
    ORDER BY
        sequence ASC
    """
    
    try:
        results = db.session.execute(text(query), {'schedule_id': schedule_id}).fetchall()
        
        # Convert to list of dictionaries
        locations = []
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
                'activity': row.activity
            }
            locations.append(location)
            
        return locations
        
    except Exception as e:
        logger.exception(f"Error getting locations for schedule {schedule_id} from {location_table}: {str(e)}")
        return []

def get_schedules_with_stp_applied(search_date: date, location: str,
                                 platform: Optional[str] = None,
                                 line: Optional[str] = None,
                                 path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get schedules for a specific date and location with STP indicators applied.
    
    This function follows the process:
    1. Get base schedules (LTP/P and STP New/N) for the location/date
    2. Check for cancellations and mark cancelled schedules
    3. Apply overlays to non-cancelled schedules
    4. Fetch locations for all active (non-cancelled) schedules
    
    Args:
        search_date: Date to get schedules for
        location: TIPLOC code to filter by
        platform: Optional platform to filter by
        line: Optional line to filter by
        path: Optional path to filter by
        
    Returns:
        List of schedules with STP indicators applied and locations included
    """
    from stp_utils import get_base_schedules_for_date
    
    # Step 1: Get base schedules (LTP/P and STP New/N)
    base_schedules = get_base_schedules_for_date(search_date, location, platform, line, path)
    
    # Step 2: Check for cancellations
    schedules_with_cancellations = check_for_cancellations(base_schedules, search_date)
    
    # Step 3: Apply overlays
    schedules_with_overlays = apply_overlays(schedules_with_cancellations, search_date)
    
    # Step 4: Fetch locations for all non-cancelled schedules
    for schedule in schedules_with_overlays:
        # Skip fetching locations for cancelled schedules
        if schedule.get('is_cancelled', False):
            schedule['locations'] = []
            continue
            
        # Fetch locations for active schedules
        schedule['locations'] = get_locations_for_schedule(schedule)
    
    return schedules_with_overlays