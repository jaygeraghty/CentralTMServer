import os
import io
import logging
import shutil
import time
from collections import namedtuple
from datetime import datetime
from typing import Dict, List, Generator, Optional, Tuple, Set, Iterable
import psycopg2
import psycopg2.extras
from sqlalchemy.orm import Session
from models import (
    ParsedFile, BasicSchedule, ScheduleLocation, Association,
    # STP-specific schedule tables
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    # STP-specific location tables
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, 
    ScheduleLocationSTPCancellation,
    # STP-specific association tables
    AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation
)
from app import db, app
import datetime as dt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Constants
IMPORT_DIR = "import"
ARCHIVE_DIR = "archive"
BUFFER_SIZE = 16 * 1024 * 1024  # 16MB buffer size for file reading

# Batch sizes - moved to module level to avoid reallocation
BS_BATCH_SIZE = 100
SL_BATCH_SIZE = 500
AA_BATCH_SIZE = 100

# Use module-level counter for performance tracking
perf_counters = {
    'file_read_time': 0.0,
    'bs_processing_time': 0.0,
    'location_processing_time': 0.0,
    'aa_processing_time': 0.0,
    'db_flush_time': 0.0
}

# Precompiled sets for faster lookups
LOCATION_RECORD_TYPES = {'LO', 'LI', 'LT'}

# Ensure directories exist
os.makedirs(IMPORT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Lightweight data structures for temporary record storage during parsing
ScheduleRecord = namedtuple('ScheduleRecord', [
    'uid', 'transaction_type', 'stp_indicator', 'runs_from', 'runs_to',
    'days_run', 'train_status', 'train_category', 'train_identity',
    'service_code', 'power_type', 'speed', 'operating_chars', 'created_at'
], defaults=[None] * 14)

LocationRecord = namedtuple('LocationRecord', [
    'schedule_id', 'sequence', 'location_type', 'tiploc', 
    'arr', 'dep', 'pass_time', 'public_arr', 'public_dep',
    'platform', 'line', 'path', 'activity'
], defaults=[None] * 13)

AssociationRecord = namedtuple('AssociationRecord', [
    'main_uid', 'assoc_uid', 'category', 'date_from', 'date_to',
    'days_run', 'location', 'base_suffix', 'assoc_suffix',
    'date_indicator', 'stp_indicator', 'transaction_type', 'created_at'
], defaults=[None] * 13)

class CIFParser:
    """
    Parser for UK railway CIF (Common Interface File) data.
    """

    def __init__(self):
        """Initialize the CIF parser."""
        # Get area of interest from app config
        self.area_of_interest = app.config.get("AREA_OF_INTEREST", set())
        logger.info(f"Using area of interest: {self.area_of_interest}")

    def is_in_area_of_interest(self, locations):
        """
        Check if any location in the schedule is in our area of interest.

        Args:
            locations: List of location dictionaries with tiploc codes

        Returns:
            bool: True if at least one location is in area of interest
        """
        # Fast early return if no filtering needed
        if not self.area_of_interest:
            # If no specific area is set, include all schedules
            logger.warning("BYPASS: Area of interest is empty - allowing all schedules through")
            return True

        # More concise logging for production
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Checking {len(locations)} locations against area of interest: {self.area_of_interest}")

        # Faster check using set-based lookups
        matching_locations = []
        for location in locations:
            # Extract tiploc based on data type
            if isinstance(location, dict):
                tiploc = location.get('tiploc')
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Checking dictionary location with tiploc: {tiploc}")
            else:
                tiploc = location
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Checking string location: {tiploc}")

            if tiploc in self.area_of_interest:
                matching_locations.append(tiploc)

        if matching_locations:
            # Found one or more matching locations
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Schedule matches area of interest at locations: {', '.join(matching_locations)}")
            return True

        # No locations in area of interest
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"No locations matched area of interest")
        return False

    def scan_import_folder(self) -> List[str]:
        """
        Scan import folder for CIF files.

        Returns:
            List[str]: List of file paths
        """
        # Use generator expression for memory efficiency
        cif_files = [
            os.path.join(IMPORT_DIR, filename) 
            for filename in os.listdir(IMPORT_DIR)
            if filename.lower().endswith(".cif")
        ]
        return sorted(cif_files)

    def process_all_files(self):
        """Process all CIF files in the import folder."""
        start_time = time.perf_counter()
        files = self.scan_import_folder()
        if not files:
            logger.info("No CIF files found in import folder")
            return

        logger.info(f"Found {len(files)} CIF files to process")

        for file_path in files:
            logger.info(f"Processing file: {file_path}")
            self.process_file(file_path)
            logger.info(f"Finished file: {file_path}")

        # Log performance metrics
        total_time = time.perf_counter() - start_time
        logger.info(f"Total processing time: {total_time:.2f}s")
        for key, value in perf_counters.items():
            logger.info(f"  {key}: {value:.2f}s ({value/total_time*100:.1f}%)")

    def get_last_processed_file_ref(self, db_session=None) -> Optional[str]:
        """
        Get the reference of the last processed file.

        Args:
            db_session: Optional database session (uses db.session if not provided)

        Returns:
            Optional[str]: Last file reference or None
        """
        session = db_session or db.session
        last_file = session.query(ParsedFile).order_by(ParsedFile.processed_at.desc()).first()
        return last_file.file_ref if last_file else None

    def process_file(self, file_path: str):
        """
        Process a single CIF file.

        Args:
            file_path: Path to the CIF file
        """
        logger.info(f"Processing file: {file_path}")

        try:
            # Parse header to get file references - use regular file IO for now
            t0 = time.perf_counter()
            with open(file_path, 'r') as f:
                header = f.readline().strip()

            # Add time to global file read counter
            global perf_counters
            perf_counters['file_read_time'] += time.perf_counter() - t0

            if not header.startswith('HD'):
                logger.error(f"Invalid CIF file (missing HD record): {file_path}")
                return

            current_file_ref = header[30:37].strip()
            last_file_ref = header[37:44].strip()

            # Extract type can be at different positions depending on file format
            # Let's check a few common positions
            if len(header) >= 47 and header[46:47] in ['F', 'U']:
                extract_type = header[46:47]
            else:
                # Check other common positions for extract type
                for pos in [44, 45, 46, 47, 48]:
                    if pos < len(header) and header[pos:pos+1] in ['F', 'U']:
                        extract_type = header[pos:pos+1]
                        break
                else:
                    # Default to full extract for testing
                    extract_type = 'F'
                    logger.warning(f"Could not find extract type in header, defaulting to 'F': {header}")

            # Check if file is already processed
            # Special bypass for test files
            if 'test_' in os.path.basename(file_path):
                logger.info(f"Test file detected, bypassing 'already processed' check: {file_path}")
            elif db.session.query(ParsedFile).filter_by(file_ref=current_file_ref).first():
                logger.info(f"File already processed (ref: {current_file_ref}): {file_path}")
                shutil.move(file_path, os.path.join(ARCHIVE_DIR, os.path.basename(file_path)))
                return

            # Check file sequence
            last_processed_ref = self.get_last_processed_file_ref()

            # Special bypass for test files
            if 'test_' in os.path.basename(file_path):
                logger.info(f"Test file detected, bypassing sequence check: {file_path}")
            # Regular sequence check for production files
            elif last_processed_ref and last_file_ref and last_file_ref != last_processed_ref:
                logger.warning(
                    f"File sequence mismatch: expected previous file {last_processed_ref}, "
                    f"but this file references {last_file_ref} as previous. Skipping: {file_path}"
                )
                return

            with db.session.begin():
                # Process file based on extract type
                if extract_type == 'F':  # Full extract
                    self.process_full_extract(file_path, current_file_ref)
                elif extract_type == 'U':  # Update
                    self.process_update_extract(file_path, current_file_ref)
                else:
                    logger.error(f"Unknown extract type '{extract_type}': {file_path}")
                    return

                self.load_file_data(file_path)

                # Record processed file
                processed_file = ParsedFile()
                processed_file.file_ref = current_file_ref
                processed_file.extract_type = extract_type
                processed_file.processed_at = datetime.now()
                processed_file.filename = os.path.basename(file_path)
                db.session.add(processed_file)

            # Move file to archive
            archive_path = os.path.join(ARCHIVE_DIR, os.path.basename(file_path))
            shutil.move(file_path, archive_path)
            logger.info(f"Moved processed file to archive: {archive_path}")

        except Exception as e:
            logger.exception(f"Error processing file {file_path}: {str(e)}")

    def process_full_extract(self, file_path: str, file_ref: str):
        """
        Prepare the database for a full extract CIF file by truncating existing data.

        Args:
            file_path: Path to the CIF file
            file_ref: Current file reference
        """
        logger.info(f"Processing full extract file: {file_path}")

        # Use raw SQL for truncation without nested transactions
        # Truncate legacy tables
        db.session.execute(db.text("TRUNCATE TABLE schedule_locations CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE basic_schedules CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE associations CASCADE"))

        # Truncate STP-specific location tables
        db.session.execute(db.text("TRUNCATE TABLE schedule_locations_ltp CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE schedule_locations_stp_new CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE schedule_locations_stp_overlay CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE schedule_locations_stp_cancellation CASCADE"))

        # Truncate STP-specific schedule tables
        db.session.execute(db.text("TRUNCATE TABLE schedules_ltp CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE schedules_stp_new CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE schedules_stp_overlay CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE schedules_stp_cancellation CASCADE"))

        # Truncate STP-specific association tables
        db.session.execute(db.text("TRUNCATE TABLE associations_ltp CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE associations_stp_new CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE associations_stp_overlay CASCADE"))
        db.session.execute(db.text("TRUNCATE TABLE associations_stp_cancellation CASCADE"))

        # Keep track of processed files
        db.session.execute(db.text("TRUNCATE TABLE parsed_files CASCADE"))

        logger.info("All database tables truncated successfully for full extract")

    def process_update_extract(self, file_path: str, file_ref: str):
        """
        Process an update extract CIF file.

        Args:
            file_path: Path to the CIF file
            file_ref: Current file reference
        """
        logger.info(f"Processing update extract file: {file_path}")

        # Actual data load occurs in the surrounding transaction scope

    def parse_cif_date(self, date_str: str) -> Optional[dt.date]:
        """
        Parse a CIF date string (YYMMDD).

        Args:
            date_str: CIF date string

        Returns:
            Optional[dt.date]: Parsed date or None
        """
        if not date_str or date_str.strip() == "":
            return None

        try:
            # Single slicing operation for better performance
            if len(date_str) >= 6:
                year = int(date_str[0:2])
                month = int(date_str[2:4])
                day = int(date_str[4:6])

                # Handle 2-digit year (assume 20xx for now)
                year += 2000 if year < 50 else 1900

                return dt.date(year, month, day)
            return None
        except (ValueError, IndexError):
            logger.warning(f"Invalid date format: {date_str}")
            return None

    def load_file_data(self, file_path: str):
        """
        Load CIF file data into the database efficiently.

        Args:
            file_path: Path to the CIF file
        """
        current_schedule = None
        location_seq = 0
        bs_buffer = []
        sl_buffer = []
        aa_buffer = []

        try:
            t0 = time.perf_counter()
            with open(file_path, 'r') as f:
                header_line = f.readline()
                current_locations = []
                current_location_data = []
                current_schedule_has_area_of_interest = False

                global perf_counters
                perf_counters['file_read_time'] += time.perf_counter() - t0

                for line in f:
                    line = line.rstrip()
                    if not line or len(line) < 2:
                        continue

                    record_type = line[0:2]

                    if record_type in ['LO', 'LI', 'LT']:
                        if current_schedule and len(current_schedule) > 0:
                            location_seq += 1
                            tiploc = line[2:10].strip()

                            current_locations.append({'tiploc': tiploc})
                            if tiploc in self.area_of_interest:
                                current_schedule_has_area_of_interest = True


                            arr_time = dep_time = pass_time = None
                            public_arr = public_dep = platform = None
                            line_code = path_code = activity = None
                            engineering_allowance = pathing_allowance = performance_allowance = None

                            if record_type == 'LO':
                                dep_time = line[10:15].strip() or None
                                public_dep = line[15:19].strip() or None
                                platform = line[19:22].strip() or None
                                line_code = line[22:25].strip() or None
                                engineering_allowance = line[25:27].strip() or None
                                pathing_allowance = line[27:29].strip() or None
                                activity = line[29:41].strip() or None
                                performance_allowance = line[41:43].strip() or None
                                


                            elif record_type == 'LI':
                                arr_time = line[10:15].strip() or None
                                dep_time = line[15:20].strip() or None
                                pass_time = line[20:25].strip() or None
                                public_arr = line[25:29].strip() or None
                                public_dep = line[29:33].strip() or None
                                platform = line[33:36].strip() or None
                                line_code = line[36:39].strip() or None
                                path_code = line[39:42].strip() or None
                                activity = line[42:54].strip() or None
                                engineering_allowance = line[54:56].strip() or None
                                pathing_allowance = line[56:58].strip() or None
                                performance_allowance = line[58:60].strip() or None
                                


                            elif record_type == 'LT':
                                arr_time = line[10:15].strip() or None
                                public_arr = line[15:19].strip() or None
                                platform = line[19:22].strip() or None
                                path_code = line[22:25].strip() or None
                                activity = line[25:37].strip() or None
                                # LT records don't have allowance fields based on CIF specification

                            location_data = {
                                'sequence': location_seq,
                                'location_type': record_type,
                                'tiploc': tiploc,
                                'arr': arr_time,
                                'dep': dep_time,
                                'pass_time': pass_time,
                                'public_arr': public_arr,
                                'public_dep': public_dep,
                                'platform': platform,
                                'line': line_code,
                                'path': path_code,
                                'activity': activity,
                                'engineering_allowance': engineering_allowance,
                                'pathing_allowance': pathing_allowance,
                                'performance_allowance': performance_allowance
                            }

                            current_location_data.append(location_data)

                            if record_type == 'LT':
                                is_cancellation = current_schedule.get('stp_indicator') == 'C'

                                if is_cancellation or current_schedule_has_area_of_interest or self.is_in_area_of_interest(current_locations):
                                    updated_schedules = self.flush_bs_buffer([current_schedule])
                                    if updated_schedules:
                                        current_schedule = updated_schedules[0]
                                        for loc_data in current_location_data:
                                            loc_data['schedule_id'] = current_schedule['id']
                                            if 'stp_id' in current_schedule and 'stp_table' in current_schedule:
                                                loc_data['stp_id'] = current_schedule['stp_id']
                                                loc_data['stp_table'] = current_schedule['stp_table']
                                            sl_buffer.append(loc_data)



                                        if len(sl_buffer) >= SL_BATCH_SIZE:
                                            self.flush_sl_buffer(sl_buffer)
                                            sl_buffer = []
                                    else:
                                        logger.warning(f"Failed to save schedule {current_schedule.get('uid')}")
                                else:
                                    logger.debug(f"Skipping schedule {current_schedule.get('uid')} - no locations in area of interest")

                    elif record_type == 'BS':
                        # Check if previous schedule should be saved
                        if current_schedule and len(current_schedule) > 0 and current_location_data:
                            is_cancellation = current_schedule.get('stp_indicator') == 'C'

                            if is_cancellation or current_schedule_has_area_of_interest or self.is_in_area_of_interest(current_locations):
                                bs_buffer.append(current_schedule)

                                if len(bs_buffer) >= BS_BATCH_SIZE:
                                    updated_bs_buffer = self.flush_bs_buffer(bs_buffer)
                                    bs_buffer = []

                                    if current_schedule and 'uid' in current_schedule:
                                        for schedule in updated_bs_buffer:
                                            if schedule.get('uid') == current_schedule.get('uid'):
                                                current_schedule = schedule
                                                break
                            else:
                                logger.debug(f"Skipping schedule {current_schedule.get('uid')} - not in area of interest")

                        # Reset state for next schedule
                        current_locations = []
                        current_location_data = []
                        location_seq = 0
                        current_schedule_has_area_of_interest = False

                        transaction_type = line[2:3]
                        if transaction_type == 'D':
                            current_schedule = {}
                            continue

                        uid = line[3:9]
                        runs_from_str = line[9:15]
                        runs_to_str = line[15:21]
                        days_run = line[21:28]
                        train_status = line[29:30]
                        train_category = line[30:32]
                        train_identity = line[32:36]
                        service_code = line[41:49]
                        power_type = line[50:53]
                        speed_str = line[57:60]
                        speed = int(speed_str) if speed_str.strip().isdigit() else None
                        operating_chars = line[60:66]
                        stp_indicator = line[79:80]

                        runs_from = self.parse_cif_date(runs_from_str)
                        runs_to = self.parse_cif_date(runs_to_str)
                        if not runs_from or not runs_to:
                            current_schedule = {}
                            continue

                        current_schedule = {
                            'uid': uid,
                            'transaction_type': transaction_type,
                            'stp_indicator': stp_indicator,
                            'runs_from': runs_from,
                            'runs_to': runs_to,
                            'days_run': days_run,
                            'train_status': train_status,
                            'train_category': train_category,
                            'train_identity': train_identity,
                            'service_code': service_code,
                            'power_type': power_type,
                            'speed': speed,
                            'operating_chars': operating_chars,
                            'created_at': datetime.now(),
                        }

                    elif record_type == 'AA':
                        t0 = time.perf_counter()
                        transaction_type = line[2:3]
                        if transaction_type == 'D':
                            continue

                        main_uid = line[3:9].strip()
                        assoc_uid = line[9:15].strip()
                        date_from_str = line[15:21].strip()
                        date_to_str = line[21:27].strip()
                        days_run = line[27:34].strip()
                        category = line[34:36].strip()
                        date_indicator = line[36:37].strip()
                        location = line[37:44].strip()
                        base_suffix = line[44:45].strip() or None
                        assoc_suffix = line[45:46].strip() or None
                        diagram_type = line[46:47].strip()
                        association_type = line[47:48].strip()
                        stp_indicator = line[79:80].strip()

                        date_from = self.parse_cif_date(date_from_str)
                        date_to = self.parse_cif_date(date_to_str)
                        if not date_from or not date_to:
                            continue

                        if location in self.area_of_interest:
                            aa_buffer.append({
                                'main_uid': main_uid,
                                'assoc_uid': assoc_uid,
                                'category': category,
                                'date_from': date_from,
                                'date_to': date_to,
                                'days_run': days_run,
                                'location': location,
                                'base_suffix': base_suffix,
                                'assoc_suffix': assoc_suffix,
                                'date_indicator': date_indicator,
                                'stp_indicator': stp_indicator,
                                'transaction_type': transaction_type,
                                'created_at': datetime.now()
                            })

                        if len(aa_buffer) >= AA_BATCH_SIZE:
                            t1 = time.perf_counter()
                            self.flush_aa_buffer(aa_buffer)
                            perf_counters['db_flush_time'] += time.perf_counter() - t1
                            aa_buffer = []
                            perf_counters['aa_processing_time'] += time.perf_counter() - t0

                if current_schedule and len(current_schedule) > 0:
                    is_cancellation = current_schedule.get('stp_indicator') == 'C'
                    if is_cancellation or self.is_in_area_of_interest(current_locations):
                        bs_buffer.append(current_schedule)

                if bs_buffer:
                    updated_bs_buffer = self.flush_bs_buffer(bs_buffer)
                    if current_schedule and 'uid' in current_schedule:
                        for schedule in updated_bs_buffer:
                            if schedule.get('uid') == current_schedule.get('uid'):
                                current_schedule = schedule
                                break

                if sl_buffer:
                    self.flush_sl_buffer(sl_buffer)
                if aa_buffer:
                    self.flush_aa_buffer(aa_buffer)

        except Exception as e:
            logger.exception(f"Error loading file data: {str(e)}")

    def flush_bs_buffer(self, buffer: List[Dict]):
        """
        Flush buffer of basic schedules to database.

        Args:
            buffer: List of schedule dictionaries

        Returns:
            The buffer with schedule IDs added
        """
        if not buffer:
            return buffer

        # List of schedules to return with IDs
        schedules_with_ids = []
        schedule_entries = []

        for schedule_data in buffer:
            # Skip if already has ID
            if 'id' in schedule_data:
                schedules_with_ids.append(schedule_data)
                continue

            # Add to legacy table for backward compatibility
            schedule = BasicSchedule()
            schedule.uid = schedule_data['uid']
            schedule.stp_indicator = schedule_data['stp_indicator']
            schedule.transaction_type = schedule_data['transaction_type']
            schedule.runs_from = schedule_data['runs_from']
            schedule.runs_to = schedule_data['runs_to']
            schedule.days_run = schedule_data['days_run']
            schedule.train_status = schedule_data['train_status']
            schedule.train_category = schedule_data['train_category']
            schedule.train_identity = schedule_data['train_identity']
            schedule.service_code = schedule_data['service_code']
            schedule.power_type = schedule_data['power_type']
            schedule.speed = schedule_data['speed']
            schedule.operating_chars = schedule_data['operating_chars']
            if 'created_at' in schedule_data:
                schedule.created_at = schedule_data['created_at']
            db.session.add(schedule)

            stp_schedule = None
            stp_table = None
            stp_indicator = schedule_data['stp_indicator']

            if stp_indicator == 'P':
                stp_schedule = ScheduleLTP()
                stp_table = 'schedules_ltp'
            elif stp_indicator == 'N':
                stp_schedule = ScheduleSTPNew()
                stp_table = 'schedules_stp_new'
            elif stp_indicator == 'O':
                stp_schedule = ScheduleSTPOverlay()
                stp_table = 'schedules_stp_overlay'
            elif stp_indicator == 'C':
                stp_schedule = ScheduleSTPCancellation()
                stp_table = 'schedules_stp_cancellation'

            if stp_schedule is not None:
                stp_schedule.uid = schedule_data['uid']
                stp_schedule.stp_indicator = schedule_data['stp_indicator']
                stp_schedule.transaction_type = schedule_data['transaction_type']
                stp_schedule.runs_from = schedule_data['runs_from']
                stp_schedule.runs_to = schedule_data['runs_to']
                stp_schedule.days_run = schedule_data['days_run']
                stp_schedule.train_status = schedule_data['train_status']
                stp_schedule.train_category = schedule_data['train_category']
                stp_schedule.train_identity = schedule_data['train_identity']
                stp_schedule.service_code = schedule_data['service_code']
                stp_schedule.power_type = schedule_data['power_type']
                stp_schedule.speed = schedule_data['speed']
                stp_schedule.operating_chars = schedule_data['operating_chars']
                if 'created_at' in schedule_data:
                    stp_schedule.created_at = schedule_data['created_at']
                db.session.add(stp_schedule)

            schedule_entries.append((schedule_data, schedule, stp_schedule, stp_table))

        if schedule_entries:
            db.session.flush()

            for schedule_data, schedule, stp_schedule, stp_table in schedule_entries:
                schedule_data['id'] = schedule.id
                schedule_data['legacy_table'] = 'basic_schedules'
                schedule_data['schedule_id'] = schedule.id  # Add this for legacy compatibility

                if stp_schedule is not None:
                    schedule_data['stp_id'] = stp_schedule.id
                    schedule_data['stp_table'] = stp_table

                schedules_with_ids.append(schedule_data)

        return schedules_with_ids

    def flush_sl_buffer(self, buffer: List[Dict]):
        """
        Flush buffer of schedule locations to database.

        Args:
            buffer: List of location dictionaries
        """
        if not buffer:
            return

        legacy_mappings = []
        stp_mapping_lists = {
            'schedules_ltp': (ScheduleLocationLTP, []),
            'schedules_stp_new': (ScheduleLocationSTPNew, []),
            'schedules_stp_overlay': (ScheduleLocationSTPOverlay, []),
            'schedules_stp_cancellation': (ScheduleLocationSTPCancellation, []),
        }

        for location_data in buffer:
            legacy_mappings.append({
                'schedule_id': location_data['schedule_id'],
                'sequence': location_data['sequence'],
                'location_type': location_data['location_type'],
                'tiploc': location_data['tiploc'],
                'arr': location_data['arr'],
                'dep': location_data['dep'],
                'pass_time': location_data['pass_time'],
                'public_arr': location_data['public_arr'],
                'public_dep': location_data['public_dep'],
                'platform': location_data['platform'],
                'line': location_data['line'],
                'path': location_data['path'],
                'activity': location_data['activity'],
                'engineering_allowance': location_data.get('engineering_allowance'),
                'pathing_allowance': location_data.get('pathing_allowance'),
                'performance_allowance': location_data.get('performance_allowance'),
            })

            stp_id = location_data.get('stp_id')
            stp_table = location_data.get('stp_table')
            if stp_id and stp_table in stp_mapping_lists:
                model, mappings = stp_mapping_lists[stp_table]
                mappings.append({
                    'schedule_id': stp_id,
                    'sequence': location_data['sequence'],
                    'location_type': location_data['location_type'],
                    'tiploc': location_data['tiploc'],
                    'arr': location_data['arr'],
                    'dep': location_data['dep'],
                    'pass_time': location_data['pass_time'],
                    'public_arr': location_data['public_arr'],
                    'public_dep': location_data['public_dep'],
                    'platform': location_data['platform'],
                    'line': location_data['line'],
                    'path': location_data['path'],
                    'activity': location_data['activity'],
                    'engineering_allowance': location_data.get('engineering_allowance'),
                    'pathing_allowance': location_data.get('pathing_allowance'),
                    'performance_allowance': location_data.get('performance_allowance'),
                })

        if legacy_mappings:
            db.session.bulk_insert_mappings(ScheduleLocation, legacy_mappings)

        for model, mappings in stp_mapping_lists.values():
            if mappings:
                db.session.bulk_insert_mappings(model, mappings)

    def flush_aa_buffer(self, buffer: List[Dict]):
        """
        Flush buffer of associations to database.

        Args:
            buffer: List of association dictionaries
        """
        if not buffer:
            return

        legacy_mappings = []
        stp_mapping_lists = {
            'P': (AssociationLTP, []),
            'N': (AssociationSTPNew, []),
            'O': (AssociationSTPOverlay, []),
            'C': (AssociationSTPCancellation, []),
        }

        for assoc_data in buffer:
            legacy_mappings.append({
                'main_uid': assoc_data['main_uid'],
                'assoc_uid': assoc_data['assoc_uid'],
                'category': assoc_data['category'],
                'date_from': assoc_data['date_from'],
                'date_to': assoc_data['date_to'],
                'days_run': assoc_data['days_run'],
                'location': assoc_data['location'],
                'base_suffix': assoc_data['base_suffix'],
                'assoc_suffix': assoc_data['assoc_suffix'],
                'date_indicator': assoc_data['date_indicator'],
                'stp_indicator': assoc_data['stp_indicator'],
                'transaction_type': assoc_data['transaction_type'],
                'created_at': assoc_data.get('created_at'),
            })

            stp_indicator = assoc_data.get('stp_indicator')
            mapping = stp_mapping_lists.get(stp_indicator)
            if mapping:
                model, mappings = mapping
                mappings.append({
                    'main_uid': assoc_data['main_uid'],
                    'assoc_uid': assoc_data['assoc_uid'],
                    'category': assoc_data['category'],
                    'date_from': assoc_data['date_from'],
                    'date_to': assoc_data['date_to'],
                    'days_run': assoc_data['days_run'],
                    'location': assoc_data['location'],
                    'base_suffix': assoc_data['base_suffix'],
                    'assoc_suffix': assoc_data['assoc_suffix'],
                    'date_indicator': assoc_data['date_indicator'],
                    'stp_indicator': assoc_data['stp_indicator'],
                    'transaction_type': assoc_data['transaction_type'],
                    'created_at': assoc_data.get('created_at'),
                })

        if legacy_mappings:
            db.session.bulk_insert_mappings(Association, legacy_mappings)

        for model, mappings in stp_mapping_lists.values():
            if mappings:
                db.session.bulk_insert_mappings(model, mappings)

def process_cif_files():
    """Function to process CIF files in the import folder."""
    logger.info("Starting CIF file processing")
    with app.app_context():
        parser = CIFParser()
        parser.process_all_files()
    logger.info("Completed CIF file processing")