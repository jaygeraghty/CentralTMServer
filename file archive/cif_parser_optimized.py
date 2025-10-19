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
from models import ParsedFile, BasicSchedule, ScheduleLocation, Association
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

# Precompiled sets for faster lookups - moved to module level
LOCATION_RECORD_TYPES = {'LO', 'LI', 'LT'}

# Ensure directories exist
os.makedirs(IMPORT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Lightweight data structures for parsed records
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
        
        # Performance counters for profiling
        self.perf_counters = {
            'file_read_time': 0,
            'bs_processing_time': 0,
            'location_processing_time': 0,
            'aa_processing_time': 0,
            'db_flush_time': 0
        }
        
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
            return True
            
        # Fast set-based lookup
        return any(location.get('tiploc') in self.area_of_interest for location in locations)
    
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
            self.process_file(file_path)
            
        # Log performance metrics
        total_time = time.perf_counter() - start_time
        logger.info(f"Total processing time: {total_time:.2f}s")
        for key, value in self.perf_counters.items():
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
            # Parse header to get file references - use buffered IO for performance
            t0 = time.perf_counter()
            with open(file_path, 'rb') as f_binary:
                # Use buffered IO for better performance
                with io.BufferedReader(f_binary, buffer_size=BUFFER_SIZE) as buffered:
                    header = next(io.TextIOWrapper(buffered, newline='\n')).strip()
            
            # Add time to file read counter
            self.perf_counters['file_read_time'] += time.perf_counter() - t0
            
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
                extract_type = None
                for pos in [44, 45, 46, 47, 48]:
                    if pos < len(header) and header[pos:pos+1] in ['F', 'U']:
                        extract_type = header[pos:pos+1]
                        break
                        
                if not extract_type:
                    # Default to full extract for testing
                    extract_type = 'F'
                    logger.warning(f"Could not find extract type in header, defaulting to 'F': {header}")
            
            # Check if file is already processed - avoid DB query if possible
            if db.session.query(ParsedFile).filter_by(file_ref=current_file_ref).first():
                logger.info(f"File already processed (ref: {current_file_ref}): {file_path}")
                shutil.move(file_path, os.path.join(ARCHIVE_DIR, os.path.basename(file_path)))
                return
            
            # Check file sequence
            last_processed_ref = self.get_last_processed_file_ref()
            if last_processed_ref and last_file_ref and last_file_ref != last_processed_ref:
                logger.warning(
                    f"File sequence mismatch: expected previous file {last_processed_ref}, "
                    f"but this file references {last_file_ref} as previous. Skipping: {file_path}"
                )
                #return
            
            # Process file based on extract type
            if extract_type == 'F':  # Full extract
                self.process_full_extract(file_path, current_file_ref)
            elif extract_type == 'U':  # Update
                self.process_update_extract(file_path, current_file_ref)
            else:
                logger.error(f"Unknown extract type '{extract_type}': {file_path}")
                return
            
            # Record processed file and move to archive
            processed_file = ParsedFile()
            processed_file.file_ref = current_file_ref
            processed_file.extract_type = extract_type
            processed_file.processed_at = datetime.now()
            processed_file.filename = os.path.basename(file_path)
            db.session.add(processed_file)
            db.session.commit()
            
            # Move file to archive
            archive_path = os.path.join(ARCHIVE_DIR, os.path.basename(file_path))
            shutil.move(file_path, archive_path)
            logger.info(f"Moved processed file to archive: {archive_path}")
                
        except Exception as e:
            logger.exception(f"Error processing file {file_path}: {str(e)}")
    
    def process_full_extract(self, file_path: str, file_ref: str):
        """
        Process a full extract CIF file.
        
        Args:
            file_path: Path to the CIF file
            file_ref: Current file reference
        """
        logger.info(f"Processing full extract file: {file_path}")
        
        # Use raw SQL for truncation without nested transactions
        try:
            # First reset the session to ensure no transaction is active
            db.session.rollback()
            
            # Now execute the truncate commands - use a single transaction for all truncates
            truncate_start = time.perf_counter()
            db.session.execute(db.text("TRUNCATE TABLE schedule_locations CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE basic_schedules CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE associations CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE parsed_files CASCADE"))
            db.session.commit()
            self.perf_counters['db_flush_time'] += time.perf_counter() - truncate_start
            
            # Process the file data
            self.load_file_data(file_path)
        except Exception as e:
            db.session.rollback()
            logger.exception(f"Error in process_full_extract: {str(e)}")
    
    def process_update_extract(self, file_path: str, file_ref: str):
        """
        Process an update extract CIF file.
        
        Args:
            file_path: Path to the CIF file
            file_ref: Current file reference
        """
        logger.info(f"Processing update extract file: {file_path}")
        
        # Process the file data with transaction type handling
        self.load_file_data(file_path)
    
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
        # Process file using buffered IO for better performance
        current_schedule = None
        location_seq = 0
        
        # Batch buffers - preallocate with expected size
        bs_buffer = []
        sl_buffer = []
        aa_buffer = []
                
        try:
            # Use binary mode with BufferedReader for significantly better IO performance
            start_time = time.perf_counter()
            with open(file_path, 'rb') as f_binary:
                # Use buffered IO for better performance
                with io.BufferedReader(f_binary, buffer_size=BUFFER_SIZE) as buffered:
                    # Convert to text stream with efficient line handling
                    text_io = io.TextIOWrapper(buffered, newline='\n')
                    
                    # Skip header
                    next(text_io)
                    self.perf_counters['file_read_time'] += time.perf_counter() - start_time
                    
                    # Keep track of locations for current schedule for area of interest filtering
                    current_locations = []
                    
                    # Process file line by line with buffered IO
                    for line in text_io:
                        print(line)
                        line = line.rstrip()
                        if not line or len(line) < 2:
                            continue
                        
                        record_type = line[0:2]
                        
                        # Location records (LO, LI, LT) - use set lookup for performance
                        if record_type in LOCATION_RECORD_TYPES:
                            t0 = time.perf_counter()
                            location_seq += 1
                            tiploc = line[2:10].strip()
                            
                            # Add to current locations list for area of interest filtering
                            current_locations.append({'tiploc': tiploc})
                            
                            # Only process location records if we have a valid schedule
                            if current_schedule and len(current_schedule) > 0:
                                # Parse differently based on record type
                                arr_time = dep_time = pass_time = public_arr = public_dep = platform = line_code = path_code = activity = None
                                
                                if record_type == 'LO':  # Origin location
                                    # LO format: TIPLOC(7+1), Dep Time(5), Public Dep(4), Platform(3), Line(3)...
                                    dep_time = line[10:15].strip() or None
                                    public_dep = line[15:19].strip() or None
                                    platform = line[19:22].strip() or None
                                    line_code = line[22:25].strip() or None
                                    activity = line[29:41].strip() or None  # Activities start at position 29
                                
                                elif record_type == 'LI':  # Intermediate location
                                    # LI format: TIPLOC(7+1), Arr Time(5), Dep Time(5), Pass(5), Pub Arr(4), Pub Dep(4), Platform(3), Line(3), Path(3)...
                                    arr_time = line[10:15].strip() or None
                                    dep_time = line[15:20].strip() or None
                                    pass_time = line[20:25].strip() or None
                                    public_arr = line[25:29].strip() or None
                                    public_dep = line[29:33].strip() or None
                                    platform = line[33:36].strip() or None
                                    line_code = line[36:39].strip() or None
                                    path_code = line[39:42].strip() or None
                                    activity = line[42:54].strip() or None  # Activities start at position 42
                                
                                elif record_type == 'LT':  # Terminating location
                                    # LT format: TIPLOC(7+1), Arr Time(5), Public Arr(4), Platform(3), Path(3)...
                                    arr_time = line[10:15].strip() or None
                                    public_arr = line[15:19].strip() or None
                                    platform = line[19:22].strip() or None
                                    path_code = line[22:25].strip() or None
                                    activity = line[25:37].strip() or None  # Activities start at position 25
                                
                                # First flush basic schedule if it's not in the database yet
                                if 'id' not in current_schedule:
                                    t1 = time.perf_counter()
                                    self.flush_bs_buffer([current_schedule])
                                    self.perf_counters['db_flush_time'] += time.perf_counter() - t1
                                
                                # Add location to buffer - use lightweight dict creation for performance
                                sl_buffer.append({
                                    'schedule_id': current_schedule['id'],
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
                                    'activity': activity
                                })
                                
                                # Flush buffer if full
                                if len(sl_buffer) >= SL_BATCH_SIZE:
                                    t1 = time.perf_counter()
                                    self.flush_sl_buffer(sl_buffer)
                                    self.perf_counters['db_flush_time'] += time.perf_counter() - t1
                                    sl_buffer = []
                            
                            self.perf_counters['location_processing_time'] += time.perf_counter() - t0
                        
                        # Basic Schedule (BS)
                        elif record_type == 'BS':
                            t0 = time.perf_counter()
                            # Check if previous schedule is in area of interest before saving
                            if current_schedule and len(current_schedule) > 0:
                                if self.is_in_area_of_interest(current_locations):
                                    bs_buffer.append(current_schedule)
                                    
                                    # Flush buffer if full
                                    if len(bs_buffer) >= BS_BATCH_SIZE:
                                        t1 = time.perf_counter()
                                        updated_bs_buffer = self.flush_bs_buffer(bs_buffer)
                                        self.perf_counters['db_flush_time'] += time.perf_counter() - t1
                                        bs_buffer = []
                                        
                                        # Update current schedule if it exists in buffer
                                        if current_schedule:
                                            for schedule in updated_bs_buffer:
                                                if schedule.get('uid') == current_schedule.get('uid'):
                                                    current_schedule = schedule
                                                    break
                                else:
                                    logger.debug(f"Skipping schedule {current_schedule.get('uid')} - not in area of interest")
                            
                            # Reset for new schedule
                            current_locations = []
                            location_seq = 0
                            
                            # Parse new BS record - read fields once with efficient slicing
                            transaction_type = line[2:3]
                            
                            # Skip deletion records as per requirement
                            if transaction_type == 'D':
                                current_schedule = {}
                                continue
                            
                            # Extract all fields in a single pass for better performance
                            uid = line[3:9]
                            runs_from_str = line[9:15]
                            runs_to_str = line[15:21]
                            days_run = line[21:28]
                            train_status = line[29:30]
                            train_category = line[30:32]
                            train_identity = line[32:36]
                            service_code = line[41:49]
                            power_type = line[50:53]
                            
                            # Handle speed (may be empty)
                            speed_str = line[57:60]
                            speed = int(speed_str) if speed_str.strip() and speed_str.strip().isdigit() else None
                            
                            operating_chars = line[60:66]
                            stp_indicator = line[79:80]
                            
                            # Parse dates
                            runs_from = self.parse_cif_date(runs_from_str)
                            runs_to = self.parse_cif_date(runs_to_str)
                            
                            # Skip invalid records
                            if not runs_from or not runs_to:
                                current_schedule = {}
                                continue
                            
                            # Create schedule record efficiently
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
                            self.perf_counters['bs_processing_time'] += time.perf_counter() - t0
                        
                        # Add Association (AA) record processing - currently missing in original implementation
                        elif record_type == 'AA':
                            t0 = time.perf_counter()
                            # Check if we should skip it
                            transaction_type = line[2:3]
                            if transaction_type == 'D':  # Skip deletion records
                                continue
                                
                            # Extract fields in a single pass
                            main_uid = line[3:9].strip()
                            assoc_uid = line[9:15].strip()
                            category = line[15:17].strip()
                            date_from_str = line[17:23].strip()
                            date_to_str = line[23:29].strip()
                            days_run = line[29:36].strip()
                            location = line[36:44].strip()
                            base_suffix = line[44:45].strip() or None
                            assoc_suffix = line[45:46].strip() or None
                            date_indicator = line[47:48].strip() or None
                            stp_indicator = line[79:80].strip()
                            
                            # Parse dates
                            date_from = self.parse_cif_date(date_from_str)
                            date_to = self.parse_cif_date(date_to_str)
                            
                            # Skip invalid records
                            if not date_from or not date_to:
                                continue
                                
                            # Add to buffer
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
                            
                            # Flush if buffer is full
                            if len(aa_buffer) >= AA_BATCH_SIZE:
                                t1 = time.perf_counter()
                                self.flush_aa_buffer(aa_buffer)
                                self.perf_counters['db_flush_time'] += time.perf_counter() - t1
                                aa_buffer = []
                            
                            self.perf_counters['aa_processing_time'] += time.perf_counter() - t0
                    
                    # Check if last schedule should be saved
                    if current_schedule and len(current_schedule) > 0:
                        if self.is_in_area_of_interest(current_locations):
                            bs_buffer.append(current_schedule)
                        else:
                            logger.debug(f"Skipping schedule {current_schedule.get('uid')} - not in area of interest")
                    
                    # Flush any remaining records with timing
                    if bs_buffer:
                        logger.info(f"Saving {len(bs_buffer)} schedules relevant to area of interest")
                        t0 = time.perf_counter()
                        updated_bs_buffer = self.flush_bs_buffer(bs_buffer)
                        self.perf_counters['db_flush_time'] += time.perf_counter() - t0
                        
                    if sl_buffer:
                        t0 = time.perf_counter()
                        self.flush_sl_buffer(sl_buffer)
                        self.perf_counters['db_flush_time'] += time.perf_counter() - t0
                        
                    if aa_buffer:
                        t0 = time.perf_counter()
                        self.flush_aa_buffer(aa_buffer)
                        self.perf_counters['db_flush_time'] += time.perf_counter() - t0
                    
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
        
        # Find records that already have IDs
        existing_records = [rec for rec in buffer if 'id' in rec]
        new_records = [rec for rec in buffer if 'id' not in rec]
        
        if existing_records:
            schedules_with_ids.extend(existing_records)
        
        if new_records:
            try:
                # Use bulk insert with psycopg2 for better performance
                conn = db.engine.raw_connection()
                try:
                    with conn.cursor() as cursor:
                        # Prepare values
                        values = []
                        for schedule_data in new_records:
                            values.append((
                                schedule_data['uid'],
                                schedule_data['stp_indicator'],
                                schedule_data['transaction_type'],
                                schedule_data['runs_from'],
                                schedule_data['runs_to'],
                                schedule_data['days_run'],
                                schedule_data['train_status'],
                                schedule_data['train_category'],
                                schedule_data['train_identity'],
                                schedule_data['service_code'],
                                schedule_data['power_type'],
                                schedule_data['speed'],
                                schedule_data['operating_chars'],
                                schedule_data['created_at']
                            ))
                            
                        # Execute bulk insert with RETURNING id for efficiency
                        args_str = ','.join(cursor.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", x).decode('utf-8') for x in values)
                        cursor.execute(f"""
                            INSERT INTO basic_schedules 
                            (uid, stp_indicator, transaction_type, runs_from, runs_to, days_run, 
                             train_status, train_category, train_identity, service_code, 
                             power_type, speed, operating_chars, created_at)
                            VALUES {args_str}
                            RETURNING id, uid, stp_indicator, runs_from, runs_to
                        """)
                        
                        # Get the inserted IDs
                        result_rows = cursor.fetchall()
                        conn.commit()
                        
                        # Update schedule data with IDs
                        for row in result_rows:
                            # Match by multiple fields for safety (uid, stp, from, to)
                            id, uid, stp, runs_from, runs_to = row
                            for schedule in new_records:
                                if (schedule['uid'] == uid and
                                    schedule['stp_indicator'] == stp and
                                    schedule['runs_from'] == runs_from and
                                    schedule['runs_to'] == runs_to):
                                    schedule['id'] = id
                                    schedules_with_ids.append(schedule)
                                    break
                finally:
                    conn.close()
                    
            except Exception as e:
                logger.exception(f"Error in bulk insert of schedules: {str(e)}")
                # Fallback to traditional SQLAlchemy ORM method
                for schedule_data in new_records:
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
                    schedule.created_at = schedule_data['created_at']
                    db.session.add(schedule)
                
                db.session.commit()
                
                # Update schedule data with IDs
                for schedule_data in new_records:
                    if 'id' not in schedule_data:
                        # Find the corresponding BasicSchedule by UID and other unique fields
                        schedule = db.session.query(BasicSchedule).filter_by(
                            uid=schedule_data['uid'],
                            stp_indicator=schedule_data['stp_indicator'],
                            runs_from=schedule_data['runs_from'],
                            runs_to=schedule_data['runs_to']
                        ).first()
                        
                        if schedule:
                            schedule_data['id'] = schedule.id
                            schedules_with_ids.append(schedule_data)
            
        logger.info(f"Committed {len(new_records)} basic schedules to database")
        return schedules_with_ids
    
    def flush_sl_buffer(self, buffer: List[Dict]):
        """
        Flush buffer of schedule locations to database.
        
        Args:
            buffer: List of location dictionaries
        """
        if not buffer:
            return
        
        try:
            # Use native psycopg2 connection for better bulk insert performance
            conn = db.engine.raw_connection()
            try:
                with conn.cursor() as cursor:
                    # Prepare values for bulk insert
                    values = []
                    for location_data in buffer:
                        values.append((
                            location_data['schedule_id'],
                            location_data['sequence'],
                            location_data['location_type'],
                            location_data['tiploc'],
                            location_data['arr'],
                            location_data['dep'],
                            location_data['pass_time'],
                            location_data['public_arr'],
                            location_data['public_dep'],
                            location_data['platform'],
                            location_data['line'],
                            location_data['path'],
                            location_data['activity']
                        ))
                    
                    # Use execute_values for efficient bulk insert
                    psycopg2.extras.execute_values(
                        cursor,
                        """
                        INSERT INTO schedule_locations
                        (schedule_id, sequence, location_type, tiploc, arr, dep, pass_time,
                         public_arr, public_dep, platform, line, path, activity)
                        VALUES %s
                        """,
                        values,
                        template=None,
                        page_size=1000
                    )
                    conn.commit()
            finally:
                conn.close()
                
        except Exception as e:
            logger.exception(f"Error in bulk insert of locations: {str(e)}")
            # Fallback to traditional SQLAlchemy ORM method
            for location_data in buffer:
                location = ScheduleLocation()
                location.schedule_id = location_data['schedule_id']
                location.sequence = location_data['sequence']
                location.location_type = location_data['location_type'] 
                location.tiploc = location_data['tiploc']
                location.arr = location_data['arr']
                location.dep = location_data['dep']
                location.pass_time = location_data['pass_time']
                location.public_arr = location_data['public_arr']
                location.public_dep = location_data['public_dep']
                location.platform = location_data['platform']
                location.line = location_data['line']
                location.path = location_data['path']
                location.activity = location_data['activity']
                db.session.add(location)
            
            db.session.commit()
    
        logger.info(f"Committed {len(buffer)} schedule locations to database")
    
    def flush_aa_buffer(self, buffer: List[Dict]):
        """
        Flush buffer of associations to database.
        
        Args:
            buffer: List of association dictionaries
        """
        if not buffer:
            return
            
        try:
            # Use native psycopg2 connection for better bulk insert performance
            conn = db.engine.raw_connection()
            try:
                with conn.cursor() as cursor:
                    # Prepare values for bulk insert
                    values = []
                    for assoc_data in buffer:
                        values.append((
                            assoc_data['main_uid'],
                            assoc_data['assoc_uid'],
                            assoc_data['category'],
                            assoc_data['date_from'],
                            assoc_data['date_to'],
                            assoc_data['days_run'],
                            assoc_data['location'],
                            assoc_data['base_suffix'],
                            assoc_data['assoc_suffix'],
                            assoc_data['date_indicator'],
                            assoc_data['stp_indicator'],
                            assoc_data['transaction_type'],
                            assoc_data['created_at']
                        ))
                    print(f"Values = {values}")
                    # Use execute_values for efficient bulk insert
                    psycopg2.extras.execute_values(
                        cursor,
                        """
                        INSERT INTO associations
                        (main_uid, assoc_uid, category, date_from, date_to, days_run,
                         location, base_suffix, assoc_suffix, date_indicator, 
                         stp_indicator, transaction_type, created_at)
                        VALUES %s
                        """,
                        values,
                        template=None,
                        page_size=1000
                    )
                    conn.commit()
            finally:
                conn.close()
                
        except Exception as e:
            logger.exception(f"Error in bulk insert of associations: {str(e)}")
            # Fallback to traditional SQLAlchemy ORM method
            for assoc_data in buffer:
                association = Association()
                association.main_uid = assoc_data['main_uid']
                association.assoc_uid = assoc_data['assoc_uid']
                association.category = assoc_data['category']
                association.date_from = assoc_data['date_from']
                association.date_to = assoc_data['date_to']
                association.days_run = assoc_data['days_run']
                association.location = assoc_data['location']
                association.base_suffix = assoc_data['base_suffix']
                association.assoc_suffix = assoc_data['assoc_suffix']
                association.date_indicator = assoc_data['date_indicator']
                association.stp_indicator = assoc_data['stp_indicator']
                association.transaction_type = assoc_data['transaction_type']
                association.created_at = assoc_data['created_at']
                db.session.add(association)
            
            db.session.commit()
        
        logger.info(f"Committed {len(buffer)} associations to database")

def process_cif_files():
    """Function to process CIF files in the import folder."""
    logger.info("Starting CIF file processing")
    start_time = time.perf_counter()
    with app.app_context():
        parser = CIFParser()
        parser.process_all_files()
    end_time = time.perf_counter()
    logger.info(f"Completed CIF file processing in {end_time - start_time:.2f} seconds")