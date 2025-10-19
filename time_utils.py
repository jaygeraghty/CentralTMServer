
"""
Time parsing utilities for handling CIF time formats and conversions.
"""

from datetime import datetime, time
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def parse_cif_time(time_str: Optional[str]) -> Optional[str]:
    """
    Parse CIF time format and convert to HH:MM:SS format.
    
    CIF times can be:
    - HHMM (e.g., "1810" = 18:10:00)
    - HHMMH (e.g., "1810H" = 18:10:30, where H indicates +30 seconds)
    
    Args:
        time_str: Time string from CIF format
        
    Returns:
        Time in HH:MM:SS format, or None if invalid
    """
    if not time_str:
        return None
    
    try:
        # Handle half-second indicator
        has_half_second = time_str.endswith('H')
        if has_half_second:
            time_str = time_str[:-1]  # Remove 'H'
        
        # Validate length
        if len(time_str) != 4:
            logger.warning(f"Invalid CIF time format: {time_str} (expected 4 digits)")
            return None
        
        # Extract hours and minutes
        hour_str = time_str[:2]
        minute_str = time_str[2:]
        
        # Validate numeric
        if not hour_str.isdigit() or not minute_str.isdigit():
            logger.warning(f"Non-numeric characters in CIF time: {time_str}")
            return None
        
        hour = int(hour_str)
        minute = int(minute_str)
        
        # Validate ranges
        if hour < 0 or hour > 23:
            logger.warning(f"Invalid hour in CIF time: {hour}")
            return None
        
        if minute < 0 or minute > 59:
            logger.warning(f"Invalid minute in CIF time: {minute}")
            return None
        
        # Add 30 seconds if half-second indicator is present
        seconds = 30 if has_half_second else 0
        
        # Format as HH:MM:SS
        return f"{hour:02d}:{minute:02d}:{seconds:02d}"
        
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing CIF time '{time_str}': {str(e)}")
        return None

def parse_cif_time_to_datetime(time_str: Optional[str], date_obj: datetime) -> Optional[datetime]:
    """
    Parse CIF time and combine with a date to create a datetime object.
    
    Args:
        time_str: Time string from CIF format
        date_obj: Date to combine with the time
        
    Returns:
        Datetime object, or None if invalid
    """
    parsed_time = parse_cif_time(time_str)
    if not parsed_time:
        return None
    
    try:
        time_parts = parsed_time.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        second = int(time_parts[2]) if len(time_parts) > 2 else 0
        
        return date_obj.replace(hour=hour, minute=minute, second=second, microsecond=0)
    except (ValueError, AttributeError) as e:
        logger.error(f"Error creating datetime from CIF time '{time_str}': {str(e)}")
        return None

def cif_time_to_iso_datetime(time_str: Optional[str], date_str: str) -> Optional[str]:
    """
    Convert time string to ISO datetime string for API responses.
    Handles both CIF format (HHMM) and HH:MM:SS format.
    
    Args:
        time_str: Time string from CIF format or HH:MM:SS format
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        ISO datetime string (YYYY-MM-DDTHH:MM:SS), or None if invalid
    """
    if not time_str:
        return None
    
    # If it's already in HH:MM:SS or HH:MM format, use it directly
    if ':' in time_str:
        # Validate the time format
        parts = time_str.split(':')
        if len(parts) == 2:  # HH:MM format
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return f"{date_str}T{hour:02d}:{minute:02d}:00"
            except ValueError:
                pass
        elif len(parts) == 3:  # HH:MM:SS format
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2])
                if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
                    return f"{date_str}T{time_str}"
            except ValueError:
                pass
        
        logger.warning(f"Invalid time format with colons: {time_str}")
        return None
    
    # Otherwise, treat as CIF format and parse it
    parsed_time = parse_cif_time(time_str)
    if not parsed_time:
        return None
    
    try:
        # parsed_time is now in HH:MM:SS format, so we can use it directly
        return f"{date_str}T{parsed_time}"
    except Exception as e:
        logger.error(f"Error creating ISO datetime from time '{time_str}': {str(e)}")
        return None

def validate_cif_time_format(time_str: str) -> bool:
    """
    Validate if a string is in valid CIF time format.
    
    Args:
        time_str: Time string to validate
        
    Returns:
        True if valid CIF time format, False otherwise
    """
    if not time_str:
        return False
    
    # Check for H suffix
    if time_str.endswith('H'):
        time_str = time_str[:-1]
    
    # Must be exactly 4 digits
    if len(time_str) != 4 or not time_str.isdigit():
        return False
    
    # Validate hour and minute ranges
    try:
        hour = int(time_str[:2])
        minute = int(time_str[2:])
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except ValueError:
        return False

def parse_database_time(time_str: Optional[str]) -> Optional[str]:
    """
    Parse time from database which could be in CIF format (HHMM/HHMMH) or already in HH:MM:SS format.
    
    Args:
        time_str: Time string from database
        
    Returns:
        Time in HH:MM:SS format, or None if invalid
    """
    if not time_str:
        return None
    
    time_str = str(time_str).strip()
    
    # If it's already in HH:MM:SS or HH:MM format, validate and return/convert
    if ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 2:  # HH:MM format
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return f"{hour:02d}:{minute:02d}:00"
            except ValueError:
                pass
        elif len(parts) == 3:  # HH:MM:SS format
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2])
                if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
                    return time_str  # Already in correct format
            except ValueError:
                pass
        
        logger.warning(f"Invalid time format with colons: {time_str}")
        return None
    
    # Otherwise, treat as CIF format
    return parse_cif_time(time_str)
