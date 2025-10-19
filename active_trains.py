"""
ActiveTrains module - Keeps track of all trains running today in the system.

This module provides functionality to load and manage active trains data from the database,
including their schedules, locations, and associations. It's used to efficiently query
and update train information in memory without constant database access.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, date, time as dt_time, timedelta
from dataclasses import dataclass, field
import pytz

# Set timezone to London for all logging and time operations
os.environ['TZ'] = 'Europe/London'
time.tzset()
from time_utils import parse_cif_time, parse_database_time
from models import (ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay,
                    ScheduleSTPCancellation, ScheduleLocationLTP,
                    ScheduleLocationSTPNew, ScheduleLocationSTPOverlay,
                    ScheduleLocationSTPCancellation, AssociationLTP,
                    AssociationSTPNew, AssociationSTPOverlay,
                    AssociationSTPCancellation, ScheduleLocation,
                    BasicSchedule, Association)
from app import db
from sqlalchemy import text, func

# Configure logging
logger = logging.getLogger(__name__)

LATE_DWELL_CFG = {
    "LESTER": 45,
    "HTHRGRN": 30,
    # add more TIPLOC overrides here
}


@dataclass
class ActiveScheduleLocation:
    """Represents a location in an active train's schedule."""
    sequence: int
    tiploc: str
    recurrence_value: str
    location_type: str  # 'LO', 'LI', 'LT'
    arr_time: Optional[str] = None
    dep_time: Optional[str] = None
    pass_time: Optional[str] = None
    public_arr: Optional[str] = None
    public_dep: Optional[str] = None
    platform: Optional[str] = None
    line: Optional[str] = None
    path: Optional[str] = None
    activity: Optional[str] = None
    engineering_allowance: Optional[str] = None
    pathing_allowance: Optional[str] = None
    performance_allowance: Optional[str] = None

    # Additional real-time fields
    actual_arr: Optional[str] = None
    actual_dep: Optional[str] = None
    actual_pass: Optional[str] = None
    actual_platform: Optional[str] = None
    delay_seconds: Optional[int] = None
    forecast_arr: Optional[str] = None
    forecast_dep: Optional[str] = None
    forecast_pass: Optional[str] = None
    forecast_platform: Optional[str] = None
    forecast_timestamp: Optional[datetime] = None
    from_berth: Optional[str] = None
    to_berth: Optional[str] = None

    # ---------- OUR prediction layer ----------
    pred_arr: str | None = None
    pred_dep: str | None = None
    pred_pass: str | None = None
    pred_delay_min: float | None = None

    # ---------- SMART prediction cycle layer ----------
    smart_pred_arr: str | None = None  # AI-powered arrival predictions
    smart_pred_dep: str | None = None  # AI-powered departure predictions  
    smart_pred_pass: str | None = None  # AI-powered pass predictions
    smart_pred_confidence: float | None = None  # Confidence level (0.0-1.0)
    smart_pred_timestamp: Optional[datetime] = None  # When smart prediction was made
    smart_pred_delay_min: int | None = None  # Smart prediction delay estimate

    # ── config / future SRT hook ────────────────────────────────────
    late_dwell_secs: int = 60  # minimum dwell when late (configurable)
    recovery_secs: int = 0  # SECTIONAL SLACK between *previous* call → here
    #   (set to 0 for now; will be filled from SRT later)

    # ── associations at this location ────────────────────────────────
    associations: Dict[str, Dict[str, Any]] = field(
        default_factory=dict)  # headcode -> association data

    def __repr__(self):
        return f" tiploc={self.tiploc}, location_type={self.location_type}, Arr={self.arr_time}, Dep:{self.dep_time}, sequence={self.sequence}, Pass={self.pass_time}, platform={self.platform}, line={self.line}, path={self.path}, activity={self.activity}, Act Arr={self.actual_arr}, Act Dep={self.actual_dep}, Act Pass = {self.actual_pass}, Pred Arr={self.pred_arr}, Pred Dep={self.pred_dep}, Pred Pass={self.pred_pass}"


@dataclass
class ActiveAssociation:
    """Represents an association between two active trains."""
    main_uid: str
    assoc_uid: str
    category: str  # 'JJ', 'VV', 'NP'
    date_from: date
    date_to: date
    days_run: str
    location: str  # TIPLOC
    base_suffix: Optional[str] = None
    assoc_suffix: Optional[str] = None
    date_indicator: Optional[str] = None
    stp_indicator: str = 'P'  # 'P', 'N', 'O', 'C'

    # References to the actual trains
    main_train: Optional['ActiveTrain'] = None
    assoc_train: Optional['ActiveTrain'] = None


@dataclass
class ActiveSchedule:
    """Represents a schedule for an active train."""
    id: int
    uid: str
    stp_indicator: str  # 'P', 'N', 'O', 'C'
    transaction_type: str  # 'N', 'D', 'R'
    runs_from: date
    runs_to: date
    days_run: str
    train_status: str
    train_category: str
    train_identity: str  # Headcode
    service_code: str
    power_type: str
    speed: Optional[int] = None
    operating_chars: Optional[str] = None

    terminated: bool = False
    cancelled: bool = False
    terminated_time: Optional[datetime] = None
    # Relationships - now a list to support duplicate TIPLOCs
    locations: List[ActiveScheduleLocation] = field(default_factory=list)

    # Additional fields
    source_table: Optional[str] = field(
        default=None)  # Which table this schedule came from

    def has_tiploc(self, tiploc: str) -> bool:
        """Check if this schedule visits the specified TIPLOC."""
        return any(loc.tiploc == tiploc for loc in self.locations)

    def get_locations_at_tiploc(self,
                                tiploc: str) -> List[ActiveScheduleLocation]:
        """Get all locations for a specific TIPLOC (handles duplicate visits)."""
        return [loc for loc in self.locations if loc.tiploc == tiploc]

    def get_first_location_at_tiploc(
            self, tiploc: str) -> Optional[ActiveScheduleLocation]:
        """Get the first occurrence of a TIPLOC in the schedule."""
        for loc in self.locations:
            if loc.tiploc == tiploc:
                return loc
        return None

    def get_location_by_sequence(
            self, sequence: int) -> Optional[ActiveScheduleLocation]:
        """Get location by sequence number."""
        for loc in self.locations:
            if loc.sequence == sequence:
                return loc
        return None

    def get_locations_sorted(self) -> List[ActiveScheduleLocation]:
        """Get all locations sorted by sequence."""
        return sorted(self.locations, key=lambda x: x.sequence)

    def add_location(self, location: ActiveScheduleLocation):
        """Add a location to the schedule."""
        self.locations.append(location)


@dataclass
class ActiveTrain:
    """Represents an active train in the system with its complete schedule and real-time info."""
    uid: str
    headcode: str

    # Real-time fields
    berth: Optional[str] = None
    last_location: Optional[str] = None
    current_location: Optional[str] = None  # Descriptive current position
    delay: Optional[int] = None
    forecast_delay: Optional[int] = None
    forecast_delay_at: Optional[datetime] = None
    detected: bool = False
    last_step_time: Optional[datetime] = None
    terminated: bool = False
    cancelled: bool = False

    # TD system actual timestamps
    current_berth_entry_time: Optional[
        datetime] = None  # Actual time train entered current berth
    previous_berth: Optional[
        str] = None  # Previous berth for tracking movements

    # Schedule information
    schedule: Optional[ActiveSchedule] = None

    # Associations
    associations: Dict[str, List[ActiveAssociation]] = field(
        default_factory=lambda: {})

    def add_association(self, association: ActiveAssociation):
        """Add an association for this train at a specific location."""
        location = association.location
        if location not in self.associations:
            self.associations[location] = []
        self.associations[location].append(association)

    def get_associations_at(self, location: str) -> List[ActiveAssociation]:
        """Get all associations for this train at a specific location."""
        return self.associations.get(location, [])

    def get_all_locations(self) -> List[str]:
        """Get all unique locations this train visits."""
        if not self.schedule:
            return []
        return list(set(loc.tiploc for loc in self.schedule.locations))
    
    def update_current_location(self, tiploc: str, event_type: str):
        """
        Update the current_location field based on arrival/departure events.
        
        Args:
            tiploc: Location where the event occurred
            event_type: Type of event ('arr', 'arrival', 'dep', 'departure', 'pass')
        """
        if not self.schedule:
            return
            
        # Get sorted locations for sequence navigation
        sorted_locations = self.schedule.get_locations_sorted()
        current_loc_idx = None
        
        # Find the index of the current location
        for i, loc in enumerate(sorted_locations):
            if loc.tiploc == tiploc:
                current_loc_idx = i
                break
        
        if current_loc_idx is None:
            return
            
        if event_type in ['arr', 'arrival']:
            # Train has arrived at this location
            self.current_location = f"At {tiploc}"
            
        elif event_type in ['dep', 'departure', 'pass']:
            # Train has departed or passed this location
            if current_loc_idx < len(sorted_locations) - 1:
                # Not the last location - train is between current and next
                next_loc = sorted_locations[current_loc_idx + 1]
                self.current_location = f"Between {tiploc} and {next_loc.tiploc}"
            else:
                # This was the last location - train has completed journey
                self.current_location = f"Departed {tiploc} (journey complete)"
    
    def get_current_position_info(self) -> dict:
        """
        Determine the current position of the train based on actual times.
        Returns a dictionary with position information for highlighting.
        """
        if not self.schedule:
            return {"position": "unknown", "tiploc": None, "index": None}
        
        sorted_locations = self.schedule.get_locations_sorted()
        
        # Check for actual times to determine precise position
        for i, loc in enumerate(sorted_locations):
            # If we have actual arrival but no departure, we're at this location
            if loc.actual_arr and not loc.actual_dep:
                return {
                    "position": "at_station",
                    "tiploc": loc.tiploc,
                    "index": i,
                    "status": f"At {loc.tiploc}"
                }
            
            # If we have actual departure or pass, we've left this location
            if loc.actual_dep or loc.actual_pass:
                # Check if this is the last location
                if i == len(sorted_locations) - 1:
                    return {
                        "position": "completed",
                        "tiploc": loc.tiploc,
                        "index": i,
                        "status": f"Departed {loc.tiploc} (journey complete)"
                    }
                else:
                    # We're between this location and the next
                    next_loc = sorted_locations[i + 1]
                    return {
                        "position": "between_stations",
                        "tiploc": loc.tiploc,
                        "next_tiploc": next_loc.tiploc,
                        "index": i,
                        "status": f"Between {loc.tiploc} and {next_loc.tiploc}"
                    }
        
        # If no actual times but we have current_location, use that
        if self.current_location:
            return {
                "position": "estimated",
                "tiploc": None,
                "index": None,
                "status": self.current_location
            }
        
        # Default to unknown position
        return {"position": "unknown", "tiploc": None, "index": None, "status": "Position unknown"}

    def apply_realtime_update(self,
                              tiploc: str,
                              timestamp: datetime,
                              event_type: str,
                              from_berth: Optional[str] = None,
                              to_berth: Optional[str] = None):
        logger.info(
            f"In apply_rt_update for {self.headcode} at {tiploc} for {event_type} at {timestamp} event_type {event_type}"
        )
        # Skip early return check for delete events
        if event_type != "delete" and (self.terminated or self.cancelled):
            return

        manager = get_active_trains_manager()

        # ───── DELETE event ─────
        if event_type == "delete":
            logger.info(
                f"Train {self.headcode} (UID: {self.uid}) being deleted at {tiploc} from {from_berth} to {to_berth}"
            )
            self.cancelled = True
            self.terminated_time = timestamp

            # Remove from all manager collections with verification
            try:
                uid_removed = manager.trains.pop(self.uid, None) is not None
                headcode_removed = False

                # Handle multiple trains with same headcode carefully
                if self.headcode in manager.trains_by_headcode:
                    if manager.trains_by_headcode[self.headcode] == self:
                        manager.trains_by_headcode.pop(self.headcode, None)
                        headcode_removed = True
                    else:
                        logger.warning(
                            f"Headcode {self.headcode} points to different train in manager"
                        )

                logger.info(
                    f"Train deletion completed: UID removed={uid_removed}, headcode removed={headcode_removed}"
                )

            except Exception as e:
                logger.error(
                    f"Error during train deletion for {self.headcode} (UID: {self.uid}): {e}"
                )

            return

        # ───── STEP event ─────
        if event_type == "step":
            logger.info(
                f"Train {self.headcode} stepped from {from_berth} to {to_berth} at {tiploc}"
            )
            self.last_location = tiploc
            self.last_step_time = timestamp

            # Record actual TD system timestamps
            self.previous_berth = from_berth
            self.berth = to_berth
            self.current_berth_entry_time = timestamp  # Actual time train entered the berth

            return  # No further schedule logic needed

        # ───── ARR/DEP/PASS events ─────
        if not self.schedule or not self.schedule.has_tiploc(tiploc):
            logger.info(
                f"Train {self.headcode} has not timetabled via TIPLOC {tiploc}"
            )
            return

        # Get all locations that match this TIPLOC (handles duplicate visits)
        matching_locations = self.schedule.get_locations_at_tiploc(tiploc)
        if not matching_locations:
            logger.info(
                f"No location found for TIPLOC {tiploc} in train {self.headcode}"
            )
            return

        # For multiple locations at same TIPLOC, find the one closest to current London time
        loc = None
        if len(matching_locations) > 1:
            logger.info(
                f"Train {self.headcode} visits {tiploc} {len(matching_locations)} times, selecting closest to current time"
            )

            # Get current London time for comparison
            london_now = get_london_now()
            current_time_for_comparison = london_now.replace(tzinfo=None)

            best_location = None
            smallest_time_diff = float('inf')

            for location in matching_locations:
                # Determine which time field to use based on what's available and event type
                time_to_check = None

                # Priority: use the time that matches the event type first
                if (event_type == "arr" or event_type == "arrival") and location.arr_time:
                    time_to_check = location.arr_time
                elif (event_type == "dep" or event_type == "departure") and location.dep_time:
                    time_to_check = location.dep_time
                elif event_type == "pass" and location.pass_time:
                    time_to_check = location.pass_time
                else:
                    # Fallback: use dep_time or pass_time (but not both - check which exists)
                    if location.dep_time:
                        time_to_check = location.dep_time
                    elif location.pass_time:
                        time_to_check = location.pass_time
                    elif location.arr_time:
                        time_to_check = location.arr_time

                if time_to_check:
                    try:
                        # Parse the time (format: HH:MM:SS or HH:MM)
                        scheduled_dt = None
                        for fmt in ["%H:%M:%S", "%H:%M"]:
                            try:
                                scheduled_dt = datetime.strptime(
                                    time_to_check, fmt)
                                break
                            except ValueError:
                                continue

                        if scheduled_dt:
                            # Set the date to match current timestamp for comparison
                            scheduled_dt = scheduled_dt.replace(
                                year=current_time_for_comparison.year,
                                month=current_time_for_comparison.month,
                                day=current_time_for_comparison.day)

                            # Calculate time difference
                            time_diff = abs((current_time_for_comparison -
                                             scheduled_dt).total_seconds())

                            # Also check if the time makes more sense on the next day (for late night/early morning services)
                            scheduled_dt_next_day = scheduled_dt + timedelta(
                                days=1)
                            time_diff_next_day = abs(
                                (current_time_for_comparison -
                                 scheduled_dt_next_day).total_seconds())

                            # Also check previous day (for services that cross midnight)
                            scheduled_dt_prev_day = scheduled_dt - timedelta(
                                days=1)
                            time_diff_prev_day = abs(
                                (current_time_for_comparison -
                                 scheduled_dt_prev_day).total_seconds())

                            # Use the smallest time difference
                            actual_time_diff = min(time_diff,
                                                   time_diff_next_day,
                                                   time_diff_prev_day)

                            logger.debug(
                                f"Location seq {location.sequence} at {time_to_check}: time diff = {actual_time_diff/60:.1f} minutes"
                            )

                            if actual_time_diff < smallest_time_diff:
                                smallest_time_diff = actual_time_diff
                                best_location = location

                    except Exception as e:
                        logger.warning(
                            f"Error parsing time {time_to_check} for location {location.sequence}: {e}"
                        )
                else:
                    logger.debug(
                        f"Location seq {location.sequence} has no suitable time field for comparison"
                    )

            if best_location:
                loc = best_location
                logger.info(
                    f"Selected location sequence {loc.sequence} (time diff: {smallest_time_diff/60:.1f} minutes)"
                )
            else:
                # Fallback to first location if time parsing fails
                loc = matching_locations[0]
                logger.warning(
                    f"Time-based selection failed, using first location (sequence {loc.sequence})"
                )
        else:
            loc = matching_locations[0]

        actual_hhmmss = timestamp.strftime("%H:%M:%S")
        loc.from_berth = from_berth
        loc.to_berth = to_berth

        if (event_type == "arr" or event_type == "arrival") and loc.arr_time:
            loc.actual_arr = actual_hhmmss
            # Update current location when train arrives
            self.update_current_location(tiploc, "arrival")
        elif (event_type == "dep" or event_type == "departure") and loc.dep_time:
            loc.actual_dep = actual_hhmmss
            # Update current location when train departs
            self.update_current_location(tiploc, "departure")
        elif (event_type == "pass" or event_type == "dep" or event_type == "departure") and loc.pass_time:
            #This has been added as i doubt we will get pass from the STOMP server, but we will have .pass times
            loc.actual_pass = actual_hhmmss
            # Update current location when train passes
            self.update_current_location(tiploc, "pass")
        else:
            return

        # Delay estimation with robust time parsing
        def parse_time_robust(time_str):
            """Parse time string that might have seconds or not."""
            if not time_str:
                return None
            # Try with seconds first, then without
            for fmt in ["%H:%M:%S", "%H:%M"]:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue
            return None

        sched_time = None
        if (event_type == "arr" or event_type == "arrival") and loc.arr_time:
            sched_time = parse_time_robust(loc.arr_time)
        elif (event_type == "dep" or event_type == "departure") and loc.dep_time:
            sched_time = parse_time_robust(loc.dep_time)
        elif(event_type == "pass" or event_type == "dep" or event_type == "departure") and loc.pass_time:
            sched_time = parse_time_robust(loc.pass_time)
        
        if sched_time:
            # Handle railway operating day and cross-midnight scenarios
            sched_time = sched_time.replace(year=timestamp.year,
                                            month=timestamp.month,
                                            day=timestamp.day)
            logger.info(f"Sched time = {sched_time}")

            # Ensure both timestamps have the same timezone awareness
            if timestamp.tzinfo is not None and sched_time.tzinfo is None:
                # Make sched_time timezone-aware using London timezone
                london_tz = pytz.timezone('Europe/London')
                sched_time = london_tz.localize(sched_time)
            elif timestamp.tzinfo is None and sched_time.tzinfo is not None:
                # Make timestamp timezone-aware
                timestamp = to_london_tz(timestamp)

            # Calculate delay in seconds
            delay_seconds = (timestamp - sched_time).total_seconds()
            print(
                f"Delay seconds based on ts {timestamp} -  sched_time {sched_time}"
            )

            # Handle cases where trains cross midnight or have large time differences
            # If delay is more than 12 hours, likely a date boundary issue
            if delay_seconds > 43200:  # More than 12 hours late (43200 seconds)
                # Try previous day for scheduled time
                sched_time_prev = sched_time - timedelta(days=1)
                delay_seconds_prev = (timestamp - sched_time_prev).total_seconds()
                if abs(delay_seconds_prev) < abs(delay_seconds):
                    delay_seconds = delay_seconds_prev
            elif delay_seconds < -43200:  # More than 12 hours early (impossible)
                # Try next day for scheduled time
                sched_time_next = sched_time + timedelta(days=1)
                delay_seconds_next = (timestamp - sched_time_next).total_seconds()
                if abs(delay_seconds_next) < abs(delay_seconds):
                    delay_seconds = delay_seconds_next

            # Cap reasonable delay values (trains rarely more than 6 hours late)
            if delay_seconds > 21600:  # More than 6 hours (21600 seconds)
                logger.warning(
                    f"Unusually large delay calculated: {delay_seconds:.0f} seconds for {self.headcode} at {tiploc}"
                )
                delay_seconds = min(delay_seconds, 21600)  # Cap at 6 hours
            elif delay_seconds < -3600:  # More than 1 hour early (suspicious)
                logger.warning(
                    f"Train appears to be running early: {delay_seconds:.0f} seconds for {self.headcode} at {tiploc}"
                )

            loc.delay_seconds = int(delay_seconds)
            logger.info(
                f"Train {self.headcode} at {tiploc} has delay of {loc.delay_seconds} seconds. Scheduled arr = {loc.arr_time or None}, dep = {loc.dep_time or None}, pass = {loc.pass_time or None}"
            )

        # Mark step info
        self.last_step_time = timestamp
        if tiploc != "" and tiploc is not None:
            self.last_location = tiploc
        self.berth = to_berth

        # ⏹️ Check for terminationAc
        final_tiploc = list(self.schedule.locations)[-1]
        if tiploc == final_tiploc:
            self.terminated = True
            self.terminated_time = timestamp
            manager.trains.pop(self.uid, None)
            manager.trains_by_headcode.pop(self.headcode, None)
            logger.info(
                f"Train {self.headcode} terminated at final TIPLOC {tiploc}.")

        propagate_delay(self, tiploc)

    def update_real_time_info(self,
                              berth=None,
                              location=None,
                              delay=None,
                              forecast_delay=None,
                              forecast_time=None):
        """Update real-time information for this train."""
        if berth:
            self.berth = berth
        if location:
            self.last_location = location
        if delay is not None:
            self.delay = delay
        if forecast_delay is not None:
            self.forecast_delay = forecast_delay
            self.forecast_delay_at = datetime.now(
            ) if forecast_time is None else forecast_time


class ActiveTrainsManager:
    """
    Manages the collection of active trains in the system.
    This is loaded on server startup and kept updated during operation.
    Supports UK railway day operations (02:00 to 01:59 next day).
    """

    def __init__(self):
        self.trains: Dict[str, ActiveTrain] = {}
        self.trains_by_headcode: Dict[str, ActiveTrain] = {}
        self.trains_tomorrow: Dict[str, ActiveTrain] = {}
        self.trains_tomorrow_by_headcode: Dict[str, ActiveTrain] = {}
        self.current_railway_date: Optional[date] = None
        self.last_refresh: Optional[datetime] = None
        self.active_headcodes: Dict[str, str] = {
        }  # headcode -> UID of currently active train

    def get_train_by_uid(self, uid: str) -> Optional[ActiveTrain]:
        """Get a train by its UID."""
        return self.trains.get(uid)

    def get_train_by_headcode(self, headcode: str) -> Optional[ActiveTrain]:
        """Get a train by its headcode."""
        return self.trains_by_headcode.get(headcode)

    def get_tomorrow_train_by_uid(self, uid: str) -> Optional[ActiveTrain]:
        """Get a tomorrow's train by its UID."""
        return self.trains_tomorrow.get(uid)

    def get_tomorrow_train_by_headcode(self,
                                       headcode: str) -> Optional[ActiveTrain]:
        """Get a tomorrow's train by its headcode."""
        return self.trains_tomorrow_by_headcode.get(headcode)

    def get_trains_at_location(self, tiploc: str) -> List[ActiveTrain]:
        """Get all trains that visit a specific location."""
        result = []
        for train in self.trains.values():
            if train.schedule and tiploc in train.schedule.locations:
                result.append(train)
        return result

    def get_railway_date(self, dt: Optional[datetime] = None) -> date:
        """
        Calculate the railway date for a given datetime.
        UK railway day runs from 02:00 to 01:59 the following day.
        
        Args:
            dt: Datetime to calculate railway date for (defaults to now in London timezone)
            
        Returns:
            date: The railway date
        """
        if dt is None:
            dt = get_london_now()
        else:
            # Ensure we're working in London timezone
            dt = to_london_tz(dt)

        # If it's before 02:00, it's still yesterday's railway day
        if dt.time() < dt_time(2, 0):
            return (dt.date() - timedelta(days=1))
        else:
            return dt.date()

    def is_railway_day_rollover_time(self,
                                     dt: Optional[datetime] = None) -> bool:
        """
        Check if the current time is the railway day rollover time (02:00).
        
        Args:
            dt: Datetime to check (defaults to now)
            
        Returns:
            bool: True if it's 02:00 (railway day rollover)
        """
        if dt is None:
            dt = get_london_now()
        else:
            # Ensure we're working in London timezone
            dt = to_london_tz(dt)

        return dt.time().hour == 2 and dt.time().minute == 0

    def refresh_data(self, target_date: Optional[date] = None):
        """
        Refresh active trains data for the current railway date or a specified date.
        This is typically called on server startup and periodically during operation.
        Loads trains for both today and tomorrow according to UK railway day operations.
        
        Handles edge case: System startup between 00:00-01:59 London time should load
        the previous calendar day as "today" since railway day hasn't rolled over yet.
        """
        # Use current railway date if not specified
        if target_date is None:
            target_date = self.get_railway_date()

        london_now = get_london_now()
        logger.info(
            f"Refreshing active trains data for railway date: {target_date} (London time: {london_now.strftime('%Y-%m-%d %H:%M:%S %Z')})"
        )

        # Set current railway date and refresh timestamp
        self.current_railway_date = target_date
        self.last_refresh = datetime.now()

        # Handle edge case: if system starts between 00:00-01:59, log the scenario
        if london_now.hour < 2:
            logger.info(
                f"System startup during night hours ({london_now.hour:02d}:{london_now.minute:02d}) - railway day {target_date} still active until 02:00"
            )

        # Clear existing data
        self.trains = {}
        self.trains_by_headcode = {}
        self.trains_tomorrow = {}
        self.trains_tomorrow_by_headcode = {}
        self.active_headcodes = {}

        # Load schedules for today following STP precedence rules
        self._load_schedules_for_date(target_date, is_tomorrow=False)

        # Load schedules for tomorrow
        tomorrow_date = target_date + timedelta(days=1)
        self._load_schedules_for_date(tomorrow_date, is_tomorrow=True)

        # Load associations for both days
        self._load_associations(target_date)
        self._load_associations(tomorrow_date)

        logger.info(
            f"Loaded {len(self.trains)} active trains for {target_date} and {len(self.trains_tomorrow)} for {tomorrow_date}"
        )
        
        # Log to web logs interface for monitoring
        active_trains_web_logger = logging.getLogger('active_trains')
        active_trains_web_logger.info(f"🚂 Active Trains Loaded: Today={len(self.trains)} ({target_date}), Tomorrow={len(self.trains_tomorrow)} ({tomorrow_date})")

    def promote_tomorrow_trains(self):
        """
        Promote tomorrow's trains to today's trains and load new tomorrow's trains.
        This should be called at 02:00 during railway day rollover.
        """
        old_railway_date = self.current_railway_date
        new_railway_date = self.get_railway_date()

        logger.info(
            f"Railway day rollover: promoting tomorrow's trains from {old_railway_date} to {new_railway_date}"
        )
        
        # Log to active_trains logger for web logs interface
        active_trains_web_logger = logging.getLogger('active_trains')
        active_trains_web_logger.info(f"🔄 Railway Day Rollover Started: {old_railway_date} → {new_railway_date}")

        # Store counts for logging
        old_today_count = len(self.trains)
        old_tomorrow_count = len(self.trains_tomorrow)

        # Clear today's trains (yesterday's trains are now obsolete)
        self.trains.clear()
        self.trains_by_headcode.clear()
        self.active_headcodes.clear()

        # Promote tomorrow's trains to today (proper dictionary copy, not reference)
        self.trains = dict(self.trains_tomorrow)
        self.trains_by_headcode = dict(self.trains_tomorrow_by_headcode)

        # Update active headcodes mapping
        for headcode, train in self.trains_by_headcode.items():
            self.active_headcodes[headcode] = train.uid

        # Update the railway date
        self.current_railway_date = new_railway_date
        self.last_refresh = datetime.now()

        # Clear tomorrow's collections (prepare for new data)
        self.trains_tomorrow.clear()
        self.trains_tomorrow_by_headcode.clear()

        # Load new tomorrow's trains (the day after the new railway date)
        tomorrow_date = new_railway_date + timedelta(days=1)
        logger.info(f"Loading new tomorrow's trains for {tomorrow_date}")

        self._load_schedules_for_date(tomorrow_date, is_tomorrow=True)
        self._load_associations(tomorrow_date)

        # Fallback mechanism: If today's trains are empty after promotion, reload them
        if len(self.trains) == 0:
            logger.warning(f"No trains found for today ({new_railway_date}) after promotion - implementing fallback")
            logger.info(f"Fallback: Loading trains directly for today ({new_railway_date})")
            
            # Log fallback activation to web logs
            active_trains_web_logger.warning(f"⚠️ Railway Day Rollover Fallback: No trains after promotion, reloading {new_railway_date}")
            
            # Load today's trains directly
            self._load_schedules_for_date(new_railway_date, is_tomorrow=False)
            self._load_associations(new_railway_date)
            
            logger.info(f"Fallback complete: Loaded {len(self.trains)} trains for today")
            active_trains_web_logger.info(f"✅ Fallback Complete: Loaded {len(self.trains)} trains for {new_railway_date}")

        logger.info(f"Railway day rollover complete:")
        logger.info(
            f"  Cleared {old_today_count} trains from {old_railway_date}")
        logger.info(
            f"  Promoted {old_tomorrow_count} trains to today ({new_railway_date})"
        )
        logger.info(
            f"  Loaded {len(self.trains_tomorrow)} new trains for tomorrow ({tomorrow_date})"
        )
        logger.info(
            f"  Active trains: {len(self.trains)} today, {len(self.trains_tomorrow)} tomorrow"
        )
        
        # Log final rollover status to web logs
        active_trains_web_logger.info(f"✅ Railway Day Rollover Complete: Today={len(self.trains)}, Tomorrow={len(self.trains_tomorrow)}")
        active_trains_web_logger.info(f"📊 Rollover Summary: Cleared {old_today_count}, Promoted {old_tomorrow_count}, Loaded {len(self.trains_tomorrow)} new")

    def _load_schedules_for_date(self,
                                 target_date: date,
                                 is_tomorrow: bool = False):
        """
        Load all schedules that run on the specified date.
        Applies STP precedence rules: C > O > N > P
        
        Args:
            target_date: Date to load schedules for
            is_tomorrow: If True, stores trains in tomorrow's collections
        """
        # Calculate day of week (0-6, Monday is 0)
        day_of_week = target_date.weekday()
        day_mask_position = day_of_week  # 0-based indexing

        logger.info(
            f"Loading schedules for {'tomorrow' if is_tomorrow else 'today'}: {target_date} (day {day_of_week})"
        )

        # Build query using STP precedence rules
        query = f"""
        WITH combined_schedules AS (
            -- 1. STP Cancellations (highest precedence)
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
                sc.operating_chars,
                1 as priority,
                'cancellation' as source_table
            FROM 
                schedules_stp_cancellation sc
            WHERE 
                :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_of_week + 1, 1) = '1'

            UNION ALL

            -- 2. STP Overlays (second priority)
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
                sc.operating_chars,
                2 as priority,
                'overlay' as source_table
            FROM 
                schedules_stp_overlay sc
            WHERE 
                :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_of_week + 1, 1) = '1'

            UNION ALL

            -- 3. STP New schedules (third priority)
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
                sc.operating_chars,
                3 as priority,
                'new' as source_table
            FROM 
                schedules_stp_new sc
            WHERE 
                :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_of_week + 1, 1) = '1'

            UNION ALL

            -- 4. LTP Permanent schedules (lowest priority)
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
                sc.operating_chars,
                4 as priority,
                'permanent' as source_table
            FROM 
                schedules_ltp sc
            WHERE 
                :search_date BETWEEN sc.runs_from AND sc.runs_to
                AND SUBSTR(sc.days_run, :day_of_week + 1, 1) = '1'
        ),
        -- Select the highest precedence for each UID (based on priority)
        priority_schedules AS (
            SELECT 
                uid,
                MIN(priority) as min_priority
            FROM 
                combined_schedules
            GROUP BY 
                uid
        )
        -- Fetch final results with STP precedence applied
        SELECT 
            cs.*
        FROM 
            combined_schedules cs
        JOIN 
            priority_schedules ps ON cs.uid = ps.uid AND cs.priority = ps.min_priority
        """

        try:
            # Execute query with parameters
            result = db.session.execute(text(query), {
                "search_date": target_date,
                "day_of_week": day_mask_position
            })

            # Process each schedule
            for row in result:
                # Skip cancelled services
                if row.source_table == 'cancellation':
                    continue

                # Create active schedule
                active_schedule = ActiveSchedule(
                    id=row.id,
                    uid=row.uid,
                    stp_indicator=row.stp_indicator,
                    transaction_type=row.transaction_type,
                    runs_from=row.runs_from,
                    runs_to=row.runs_to,
                    days_run=row.days_run,
                    train_status=row.train_status,
                    train_category=row.train_category,
                    train_identity=row.train_identity,
                    service_code=row.service_code,
                    power_type=row.power_type,
                    speed=row.speed,
                    operating_chars=row.operating_chars,
                    source_table=row.source_table)

                # Create active train
                active_train = ActiveTrain(uid=row.uid,
                                           headcode=row.train_identity,
                                           schedule=active_schedule)

                # Load locations for this schedule
                self._load_schedule_locations(active_train, row.source_table)
                
                # Initialize predicted times to match scheduled times (for on-time display)
                initialize_predicted_times(active_train)

                # Add to appropriate collections based on is_tomorrow parameter
                if is_tomorrow:
                    self.trains_tomorrow[active_train.uid] = active_train
                    self.trains_tomorrow_by_headcode[
                        active_train.headcode] = active_train
                else:
                    self.trains[active_train.uid] = active_train
                    self.trains_by_headcode[
                        active_train.headcode] = active_train

        except Exception as e:
            logger.error(f"Error loading schedules: {str(e)}")
            raise

    def _load_schedule_locations(self, active_train: ActiveTrain,
                                 source_table: str):
        """Load locations for a specific schedule based on its source table."""
        if not active_train.schedule:
            return

        schedule_id = active_train.schedule.id
        locations_table = None

        # Determine which locations table to use
        if source_table == 'permanent':
            locations_table = ScheduleLocationLTP
        elif source_table == 'new':
            locations_table = ScheduleLocationSTPNew
        elif source_table == 'overlay':
            locations_table = ScheduleLocationSTPOverlay
        elif source_table == 'cancellation':
            locations_table = ScheduleLocationSTPCancellation
        else:
            logger.error(f"Unknown source table: {source_table}")
            return

        try:
            # Query locations for this schedule
            query = db.session.query(locations_table).filter(
                locations_table.schedule_id == schedule_id).order_by(
                    locations_table.sequence)

            locations = query.all()

            # Check if we found any locations in the STP-specific table
            if not locations:
                # If not, try the legacy ScheduleLocation table
                locations = db.session.query(ScheduleLocation).filter(
                    ScheduleLocation.schedule_id == schedule_id).order_by(
                        ScheduleLocation.sequence).all()

            # Add each location to the schedule
            for loc in locations:
                # Get the sequence value safely from database result
                try:
                    sequence = int(str(
                        loc.sequence)) if loc.sequence is not None else 0
                except (ValueError, TypeError):
                    sequence = 0
                tiploc = str(loc.tiploc) if loc.tiploc is not None else ""
                #This code is to strip the recurrence value from the TIPLOC if it exists
                recurrence_value = "1"
                if len(tiploc) == 8 and tiploc[7].isdigit():
                    recurrence_value = tiploc[7]
                    tiploc = tiploc[:7]
                location_type = str(
                    loc.location_type) if loc.location_type is not None else ""

                active_location = ActiveScheduleLocation(
                    sequence=int(sequence),
                    tiploc=tiploc,
                    recurrence_value=recurrence_value,
                    location_type=location_type,
                    arr_time=parse_database_time(str(loc.arr))
                    if loc.arr is not None else None,
                    dep_time=parse_database_time(str(loc.dep))
                    if loc.dep is not None else None,
                    pass_time=parse_database_time(str(loc.pass_time))
                    if loc.pass_time is not None else None,
                    public_arr=parse_database_time(str(loc.public_arr))
                    if loc.public_arr is not None else None,
                    public_dep=parse_database_time(str(loc.public_dep))
                    if loc.public_dep is not None else None,
                    platform=str(loc.platform)
                    if loc.platform is not None else None,
                    line=str(loc.line) if loc.line is not None else None,
                    path=str(loc.path) if loc.path is not None else None,
                    activity=str(loc.activity)
                    if loc.activity is not None else None,
                    engineering_allowance=str(loc.engineering_allowance)
                    if hasattr(loc, 'engineering_allowance')
                    and loc.engineering_allowance is not None else None,
                    pathing_allowance=str(loc.pathing_allowance)
                    if hasattr(loc, 'pathing_allowance')
                    and loc.pathing_allowance is not None else None,
                    performance_allowance=str(loc.performance_allowance)
                    if hasattr(loc, 'performance_allowance')
                    and loc.performance_allowance is not None else None,
                    late_dwell_secs=LATE_DWELL_CFG.get(tiploc, 30),
                    recovery_secs=0)

                # Add to schedule's locations list
                active_train.schedule.add_location(active_location)

        except Exception as e:
            logger.error(
                f"Error loading locations for schedule {schedule_id}: {str(e)}"
            )

    def _load_associations(self, target_date: date):
        """
        Load all associations that are active on the specified date.
        Applies STP precedence rules: C > O > N > P
        """
        # Calculate day of week (0-6, Monday is 0)
        day_of_week = target_date.weekday()
        day_mask_position = day_of_week  # 0-based indexing

        # Build query using STP precedence rules
        query = f"""
        WITH combined_assocs AS (
            -- 1. Cancellations (highest precedence)
            SELECT 
                a.id,
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
                1 as priority,
                'cancellation' as source_table
            FROM 
                associations_stp_cancellation a
            WHERE 
                :search_date BETWEEN a.date_from AND a.date_to
                AND SUBSTR(a.days_run, :day_of_week + 1, 1) = '1'

            UNION ALL

            -- 2. Overlays
            SELECT 
                a.id,
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
                2 as priority,
                'overlay' as source_table
            FROM 
                associations_stp_overlay a
            WHERE 
                :search_date BETWEEN a.date_from AND a.date_to
                AND SUBSTR(a.days_run, :day_of_week + 1, 1) = '1'

            UNION ALL

            -- 3. New associations
            SELECT 
                a.id,
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
                3 as priority,
                'new' as source_table
            FROM 
                associations_stp_new a
            WHERE 
                :search_date BETWEEN a.date_from AND a.date_to
                AND SUBSTR(a.days_run, :day_of_week + 1, 1) = '1'

            UNION ALL

            -- 4. Permanent associations
            SELECT 
                a.id,
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
                4 as priority,
                'permanent' as source_table
            FROM 
                associations_ltp a
            WHERE 
                :search_date BETWEEN a.date_from AND a.date_to
                AND SUBSTR(a.days_run, :day_of_week + 1, 1) = '1'
        ),
        -- Select the highest precedence for each association pair by location
        priority_assocs AS (
            SELECT 
                main_uid,
                assoc_uid,
                location,
                MIN(priority) as min_priority
            FROM 
                combined_assocs
            GROUP BY 
                main_uid, assoc_uid, location
        )
        -- Fetch final results with STP precedence applied
        SELECT 
            ca.*
        FROM 
            combined_assocs ca
        JOIN 
            priority_assocs pa ON ca.main_uid = pa.main_uid 
                AND ca.assoc_uid = pa.assoc_uid 
                AND ca.location = pa.location 
                AND ca.priority = pa.min_priority
        """

        try:
            # Execute query with parameters
            result = db.session.execute(text(query), {
                "search_date": target_date,
                "day_of_week": day_mask_position
            })

            # Process each association
            for row in result:
                # Skip cancelled associations
                if row.source_table == 'cancellation':
                    continue

                # Get the trains by UID (check both today and tomorrow collections)
                main_train = self.get_train_by_uid(
                    row.main_uid) or self.get_tomorrow_train_by_uid(
                        row.main_uid)
                assoc_train = self.get_train_by_uid(
                    row.assoc_uid) or self.get_tomorrow_train_by_uid(
                        row.assoc_uid)

                # Process association for both main and associated trains
                if main_train and assoc_train:
                    # Add forward association to main train's location
                    self._add_association_to_location(main_train, row.location,
                                                      assoc_train.headcode,
                                                      assoc_train.uid,
                                                      row.category)

                    # Add reverse association to associated train's location with proper reverse type
                    reverse_type = self._get_reverse_association_type(
                        row.category)
                    self._add_association_to_location(assoc_train,
                                                      row.location,
                                                      main_train.headcode,
                                                      main_train.uid,
                                                      reverse_type)

        except Exception as e:
            logger.error(f"Error loading associations: {str(e)}")
            raise

    def _get_reverse_association_type(self, association_type: str) -> str:
        """
        Get the reverse association type for bidirectional associations.
        
        Args:
            association_type: Original association type
            
        Returns:
            Reverse association type
        """
        reverse_mapping = {
            'NP': 'PR',  # Next -> Previous
            'PR': 'NP',  # Previous -> Next
            'JJ': 'JJ',  # Join -> Join (bidirectional)
            'VV': 'VV',  # Split -> Split (bidirectional)
            'DD': 'DD'  # Double dock -> Double dock (bidirectional)
        }
        return reverse_mapping.get(association_type, association_type)

    def _add_association_to_location(self, train: 'ActiveTrain',
                                     location_tiploc: str,
                                     associated_headcode: str,
                                     associated_uid: str,
                                     association_type: str):
        """
        Add association data to the specific location in a train's schedule.
        
        Args:
            train: The train to add association to
            location_tiploc: TIPLOC where association occurs
            associated_headcode: Headcode of the associated train
            associated_uid: UID of the associated train
            association_type: Type of association (JJ, VV, NP, etc.)
        """
        if not train.schedule:
            return

        # Find all locations that match this TIPLOC (handles duplicate visits)
        matching_locations = train.schedule.get_locations_at_tiploc(
            location_tiploc)

        for location in matching_locations:
            # Create association data in the required format
            association_data = {
                "associated_uid": associated_uid,
                "associated_headcode": associated_headcode,
                "association_type": association_type,
                "location": location_tiploc,
                "platform": location.platform  # Can be null
            }

            # Store association keyed by associated train's headcode
            location.associations[associated_headcode] = association_data

        logger.debug(
            f"Added association {associated_headcode} ({association_type}) to {len(matching_locations)} locations at {location_tiploc} for train {train.headcode}"
        )


# London timezone for UK railway operations
LONDON_TZ = pytz.timezone('Europe/London')


def get_london_now() -> datetime:
    """Get current time in London timezone."""
    return datetime.now(LONDON_TZ)


def to_london_tz(dt: datetime) -> datetime:
    """Convert datetime to London timezone."""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = pytz.utc.localize(dt)
    return dt.astimezone(LONDON_TZ)


# Server readiness state
_server_ready = False
_queued_updates = []


def is_server_ready() -> bool:
    """Check if the server is ready to process updates."""
    return _server_ready


def set_server_ready():
    """Mark the server as ready and process any queued updates."""
    global _server_ready, _queued_updates
    _server_ready = True

    # Process any queued updates
    if _queued_updates:
        logger.info(
            f"Processing {len(_queued_updates)} queued updates from before server was ready"
        )
        for update_type, payload in _queued_updates:
            if update_type == 'forecast':
                apply_forecast_update(active_trains_manager, payload)
            elif update_type == 'realtime':
                # Process realtime update
                headcode = payload.get("headcode")
                tiploc = payload.get("tiploc")
                event_type = payload.get("event_type")
                from_berth = payload.get("from_berth")
                to_berth = payload.get("to_berth")

                # Find the train and apply the update
                train = find_active_train_by_headcode_and_detection(
                    headcode, from_berth,
                    list(active_trains_manager.trains.values()))
                if train:
                    actual_step_time_str = payload.get("actual_step_time")
                    if actual_step_time_str:
                        actual_step_time = datetime.fromisoformat(
                            actual_step_time_str.replace("Z", "+00:00"))
                    else:
                        actual_step_time = get_london_now()

                    train.apply_realtime_update(tiploc, actual_step_time,
                                                event_type, from_berth,
                                                to_berth)
                    logger.info(
                        f"Applied queued realtime update for {headcode} at {tiploc}"
                    )
        _queued_updates.clear()


def queue_update(update_type: str, payload: dict):
    """Queue an update for processing when the server is ready."""
    global _queued_updates
    _queued_updates.append((update_type, payload))
    logger.info(
        f"{get_london_now().strftime('%Y-%m-%d %H:%M:%S %Z')} - Queued {update_type} update (server not ready yet, {len(_queued_updates)} total queued)"
    )


# Create singleton instance
active_trains_manager = ActiveTrainsManager()

FORECAST_TIME_FMT = "%H:%M"

from datetime import datetime, timedelta


def _HHMM_TO_DT(time_str):
    """Convert HH:MM or HH:MM:SS string to datetime, handling railway times that can exceed 24:00."""
    if not time_str:
        return None

    try:
        # Handle both HH:MM and HH:MM:SS formats
        if ':' in time_str:
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) > 2 else 0
        else:
            return None

        # Handle railway times that go beyond 24:00 (next day services)
        if hour >= 24:
            # Convert to next day time (e.g., 25:30:15 becomes 01:30:15 next day)
            return datetime(2000, 1, 2, hour - 24, minute, second)
        elif hour > 23 or minute > 59 or second > 59:
            # Invalid time - return None
            return None
        else:
            return datetime(2000, 1, 1, hour, minute, second)
    except (ValueError, IndexError):
        return None


def _DT_TO_HHMM(dt):
    """Convert datetime to HH:MM string."""
    if not dt:
        return None
    return f"{dt.hour:02d}:{dt.minute:02d}"


def _DT_TO_HHMMSS(dt):
    """Convert datetime to HH:MM:SS string for pred_arr and pred_dep fields."""
    if not dt:
        return None
    return f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def initialize_predicted_times(train: ActiveTrain) -> None:
    """
    Initialize predicted times for all locations in a train's schedule.
    This ensures predicted times are always shown, even when on-time.
    """
    if not train.schedule:
        return
    
    for loc in train.schedule.get_locations_sorted():
        # Only set predicted times if they're not already set
        if not loc.pred_arr and loc.arr_time:
            arr_dt = _HHMM_TO_DT(loc.arr_time)
            if arr_dt:
                loc.pred_arr = _DT_TO_HHMMSS(arr_dt)
        
        if not loc.pred_dep and loc.dep_time:
            dep_dt = _HHMM_TO_DT(loc.dep_time)
            if dep_dt:
                loc.pred_dep = _DT_TO_HHMMSS(dep_dt)
        
        if not loc.pred_pass and loc.pass_time:
            pass_dt = _HHMM_TO_DT(loc.pass_time)
            if pass_dt:
                loc.pred_pass = _DT_TO_HHMMSS(pass_dt)
        
        # Initialize delay as 0 if not set
        if loc.pred_delay_min is None:
            loc.pred_delay_min = 0


def propagate_delay(train: ActiveTrain, anchor_tiploc: str) -> None:
    """
    Rebuild *predicted* times for every downstream call whenever we receive a
    new forecast at `anchor_tiploc`.

    TODAY
    -----
    • Uses late-dwell trimming at stops
    • Ignores recovery_secs because loader sets them to 0

    TOMORROW
    --------
    • When loader populates recovery_secs from SRT, this exact function will
      automatically let the train “eat” that slack on each leg.
    """
    if not train.schedule:
        return

    locs = train.schedule.get_locations_sorted()

    try:
        anchor_idx = next(i for i, l in enumerate(locs)
                          if l.tiploc == anchor_tiploc)
    except StopIteration:
        return

    anchor = locs[anchor_idx]  #  ←  added
    delay_seconds = anchor.delay_seconds or 0  # Work in seconds for precision

    # Always process forecasts, even with zero delay
    # Convert forecast times from HH:MM to HH:MM:SS format for consistency
    if anchor.forecast_arr:
        forecast_arr_dt = _HHMM_TO_DT(anchor.forecast_arr)
        anchor.pred_arr = _DT_TO_HHMMSS(
            forecast_arr_dt) if forecast_arr_dt else anchor.forecast_arr
    if anchor.forecast_dep:
        forecast_dep_dt = _HHMM_TO_DT(anchor.forecast_dep)
        anchor.pred_dep = _DT_TO_HHMMSS(
            forecast_dep_dt) if forecast_dep_dt else anchor.forecast_dep
    if anchor.forecast_pass:
        forecast_pass_dt = _HHMM_TO_DT(anchor.forecast_pass)
        anchor.pred_pass = _DT_TO_HHMMSS(
            forecast_pass_dt) if forecast_pass_dt else anchor.forecast_pass
    
    # If no forecast but we have scheduled times, use them as predictions
    if not anchor.pred_arr and anchor.arr_time:
        arr_dt = _HHMM_TO_DT(anchor.arr_time)
        if arr_dt:
            anchor.pred_arr = _DT_TO_HHMMSS(arr_dt + timedelta(seconds=delay_seconds))
    if not anchor.pred_dep and anchor.dep_time:
        dep_dt = _HHMM_TO_DT(anchor.dep_time)
        if dep_dt:
            anchor.pred_dep = _DT_TO_HHMMSS(dep_dt + timedelta(seconds=delay_seconds))
    if not anchor.pred_pass and anchor.pass_time:
        pass_dt = _HHMM_TO_DT(anchor.pass_time)
        if pass_dt:
            anchor.pred_pass = _DT_TO_HHMMSS(pass_dt + timedelta(seconds=delay_seconds))
    
    anchor.pred_delay_min = delay_seconds / 60  # Convert to minutes for display

    # Always propagate to downstream locations (even with zero delay)
    # This ensures all locations get predicted times

    prev_loc = locs[anchor_idx]  # start of the first leg

    for loc in locs[anchor_idx + 1:]:

        # ── 1️⃣  subtract sectional slack (placeholder = 0) ─────────
        delay_seconds = max(delay_seconds - prev_loc.recovery_secs, 0)

        # ── 2️⃣  honour real forecasts if present ───────────────────
        if loc.forecast_arr or loc.forecast_dep or loc.forecast_pass:
            # Convert forecast times from HH:MM to HH:MM:SS format for consistency
            if loc.forecast_arr:
                forecast_arr_dt = _HHMM_TO_DT(loc.forecast_arr)
                loc.pred_arr = _DT_TO_HHMMSS(
                    forecast_arr_dt) if forecast_arr_dt else loc.forecast_arr
            if loc.forecast_dep:
                forecast_dep_dt = _HHMM_TO_DT(loc.forecast_dep)
                loc.pred_dep = _DT_TO_HHMMSS(
                    forecast_dep_dt) if forecast_dep_dt else loc.forecast_dep
            if loc.forecast_pass:
                forecast_pass_dt = _HHMM_TO_DT(loc.forecast_pass)
                loc.pred_pass = _DT_TO_HHMMSS(
                    forecast_pass_dt
                ) if forecast_pass_dt else loc.forecast_pass
            loc.pred_delay_min = (loc.delay_seconds or 0) / 60  # Convert to minutes for display
            delay_seconds = loc.delay_seconds or delay_seconds
            prev_loc = loc
            continue

        # ── 3️⃣  create synthetic arrival/pass ─────────────────────
        # Always populate predicted times (even when on-time)
        if loc.arr_time:
            arr_dt = _HHMM_TO_DT(loc.arr_time)
            if arr_dt:
                arr_dt = arr_dt + timedelta(seconds=delay_seconds)
                loc.pred_arr = _DT_TO_HHMMSS(arr_dt)
        elif loc.pass_time:
            pass_dt = _HHMM_TO_DT(loc.pass_time)
            if pass_dt:
                if delay_seconds < 0:
                    # Early running - cannot pass early, use scheduled time
                    loc.pred_pass = _DT_TO_HHMMSS(pass_dt)
                    delay_seconds = 0  # Reset delay after scheduled pass
                else:
                    # Late running - add delay to pass time
                    pass_dt = pass_dt + timedelta(seconds=delay_seconds)
                    loc.pred_pass = _DT_TO_HHMMSS(pass_dt)

        # ── 4️⃣  dwell-trim logic for stops ─────────────────────────
        if loc.arr_time and loc.dep_time:
            booked_arr = _HHMM_TO_DT(loc.arr_time)
            booked_dep = _HHMM_TO_DT(loc.dep_time)

            # Only proceed if both times parsed successfully
            if booked_arr and booked_dep:
                booked_dwell = (booked_dep - booked_arr).seconds
                
                if delay_seconds >= 0:
                    # Late running - use existing dwell-trim logic
                    trim_secs = max(booked_dwell - loc.late_dwell_secs, 0)
                    recovered = min(delay_seconds, trim_secs)
                    delay_after_dwell = max(delay_seconds - recovered, 0)

                    new_dep_dt = booked_arr + timedelta(seconds=delay_seconds) \
                                           + timedelta(seconds=booked_dwell - trim_secs)

                    # never depart earlier than timetable
                    if new_dep_dt < booked_dep:
                        new_dep_dt = booked_dep
                        delay_after_dwell = 0
                else:
                    # Early running - train can arrive early but cannot depart early
                    # Predicted departure remains at scheduled time (no early departure)
                    new_dep_dt = booked_dep
                    delay_after_dwell = 0  # Reset delay after early arrival

                loc.pred_dep = _DT_TO_HHMMSS(new_dep_dt)
                delay_seconds = delay_after_dwell
        else:
            # If no dwell calculation, still populate pred_dep if we have dep_time
            if loc.dep_time and not loc.pred_dep:
                dep_dt = _HHMM_TO_DT(loc.dep_time)
                if dep_dt:
                    # For departures: never allow early departure, even if running early
                    if delay_seconds < 0:
                        # Early running - depart at scheduled time
                        loc.pred_dep = _DT_TO_HHMMSS(dep_dt)
                        delay_seconds = 0  # Reset delay after scheduled departure
                    else:
                        # Late running - add delay to departure
                        dep_dt = dep_dt + timedelta(seconds=delay_seconds)
                        loc.pred_dep = _DT_TO_HHMMSS(dep_dt)

        loc.pred_delay_min = delay_seconds / 60  # Convert to minutes for display
        prev_loc = loc

    # Log summary of propagated predictions (one line per train)
    downstream_count = len(locs) - anchor_idx - 1
    if downstream_count > 0:
        final_loc = locs[-1]
        final_pred = final_loc.pred_arr or final_loc.pred_dep or final_loc.pred_pass or "unknown"
        final_delay = final_loc.pred_delay_min or 0
        logger.info(
            f"{train.headcode}: propagated to {downstream_count} locs, final {final_pred} (+{final_delay}m)"
        )
    else:
        logger.info(f"{train.headcode}: propagated (anchor only)")


def get_active_trains_manager() -> ActiveTrainsManager:
    """Get the singleton instance of the ActiveTrainsManager."""
    return active_trains_manager


def find_active_train_by_headcode_and_detection(
        headcode: str, from_berth: Optional[str],
        trains: List[ActiveTrain]) -> Optional[ActiveTrain]:
    candidates = [t for t in trains if t.headcode == headcode and t.detected]
    if not candidates:
        logger.debug(
            f"Real-time update: no detected trains found for headcode {headcode}"
        )
        return None

    if len(candidates) == 1:
        logger.debug(
            f"Real-time update: found single detected train {headcode} (UID: {candidates[0].uid})"
        )
        return candidates[0]

    # Multiple detected trains with same headcode - resolve ambiguity using location data
    logger.warning(
        f"Real-time update: {len(candidates)} detected trains found for headcode {headcode}"
    )

    if from_berth:
        # First try exact berth match
        by_berth = [t for t in candidates if t.berth == from_berth]
        if len(by_berth) == 1:
            logger.info(
                f"Real-time update: resolved ambiguity for {headcode} using berth {from_berth} -> UID {by_berth[0].uid}"
            )
            return by_berth[0]

        # Then try last known location match
        by_location = [t for t in candidates if t.last_location == from_berth]
        if len(by_location) == 1:
            logger.info(
                f"Real-time update: resolved ambiguity for {headcode} using last location {from_berth} -> UID {by_location[0].uid}"
            )
            return by_location[0]

        # Log remaining candidates for debugging
        if by_berth:
            logger.warning(
                f"Real-time update: still {len(by_berth)} candidates for {headcode} at berth {from_berth}"
            )
        if by_location:
            logger.warning(
                f"Real-time update: still {len(by_location)} candidates for {headcode} at location {from_berth}"
            )

    # Fall back to most recently active train (last_step_time)
    by_recent_activity = [t for t in candidates if t.last_step_time]
    if by_recent_activity:
        london_tz = pytz.timezone('Europe/London')
        chosen = max(by_recent_activity,
                     key=lambda t: t.last_step_time or datetime.min.replace(
                         tzinfo=london_tz))
        logger.warning(
            f"Real-time update: ambiguity resolved for {headcode} using most recent activity -> UID {chosen.uid}"
        )
        return chosen

    # Final fallback to most recent forecast
    london_tz = pytz.timezone('Europe/London')
    chosen = max(candidates,
                 key=lambda t: t.forecast_delay_at or datetime.min.replace(
                     tzinfo=london_tz))
    logger.warning(
        f"Real-time update: ambiguity unresolved for {headcode}, chose UID {chosen.uid} (most recent forecast)"
    )
    return chosen


def initialize_active_trains():
    """Initialize the active trains manager with today's data."""
    try:
        active_trains_manager.refresh_data()
        set_server_ready()
        logger.info(
            f"Active trains initialized with {len(active_trains_manager.trains)} trains - server ready for real-time updates"
        )
        return True
    except Exception as e:
        logger.error(f"Error initializing active trains: {str(e)}")
        return False


def apply_forecast_update(manager: ActiveTrainsManager, payload: dict) -> bool:
    """
    Apply forecast updates to active trains from external systems.

    Args:
        manager: The active trains manager instance
        payload: Dictionary containing forecast update data

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        train_id = payload.get('train_id') or payload.get('headcode')
        uid = payload.get('uid')

        if not train_id and not uid:
            logger.warning("Forecast update missing train identification")
            return False

        # Find the train
        train = manager.get_train_by_uid(uid) if uid else None
        if not train and train_id:
            train = manager.get_train_by_headcode(train_id)
        if not train:
            logger.warning(
                f"Unable to find train {train_id} (UID: {uid}) for forecast update"
            )
            return False

        # Mark this specific train as the currently active one for this headcode
        # This resolves ambiguity for real-time updates
        manager.active_headcodes[train.headcode] = train.uid

        if train.detected:
            logger.debug(
                f"Train {train.headcode} (UID: {train.uid}) already detected - processing forecast update"
            )
        else:
            # Mark train as detected when it receives forecast - this enables train selection for real-time updates
            train.detected = True
            logger.info(
                f"Train {train.headcode} (UID: {train.uid}) received forecast - marked as active for headcode"
            )

        forecasts = payload.get('forecasts', [])
        updated = 0

        for forecast in forecasts:
            tiploc = forecast.get('tiploc')
            if not tiploc or not train.schedule or not train.schedule.has_tiploc(
                    tiploc):
                continue

            location = train.schedule.get_first_location_at_tiploc(tiploc)
            if not location:
                continue
            location.forecast_arr = forecast.get("forecast_arrival")
            location.forecast_dep = forecast.get("forecast_departure")
            location.forecast_pass = forecast.get("forecast_pass")
            location.delay_seconds = (forecast.get("delay_minutes", 0) or 0) * 60  # Convert minutes to seconds
            location.forecast_platform = forecast.get("platform")

            # Handle forecast timestamp if present (when forecast was made - should be UTC)
            forecast_timestamp = forecast.get("timestamp")
            if forecast_timestamp:
                try:
                    # Parse UTC timestamp and convert to London time
                    if isinstance(forecast_timestamp, str):
                        forecast_dt = datetime.fromisoformat(
                            forecast_timestamp.replace("Z", "+00:00"))
                        location.forecast_timestamp = to_london_tz(forecast_dt)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse forecast timestamp {forecast_timestamp}: {e}"
                    )

            updated += 1

        if 'delay' in payload:
            train.forecast_delay = payload['delay']
            train.forecast_delay_at = get_london_now()

        # Trigger delay propagation for each forecast location
        for forecast in forecasts:
            tiploc = forecast.get('tiploc')
            if tiploc and train.schedule and train.schedule.has_tiploc(tiploc):
                propagate_delay(train, tiploc)

        logger.info(
            f"Train {train.headcode} (UID: {train.uid}) forecast updated: {updated} locations, predicted {'on time' if payload.get('delay') in [None, 0] else str(payload.get('delay')) + ' min late'}"
        )
        return updated > 0

    except Exception as e:
        logger.error(f"Error applying forecast update: {str(e)}")
        return False
