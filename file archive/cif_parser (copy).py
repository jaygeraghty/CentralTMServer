import os
import logging
import shutil
from datetime import datetime
from typing import Dict, List, Generator, Optional, Tuple, Set
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

# Ensure directories exist
os.makedirs(IMPORT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

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
        if not self.area_of_interest:
            # If no specific area is set, include all schedules
            return True
            
        for location in locations:
            if location.get('tiploc') in self.area_of_interest:
                return True
                
        return False
    
    def scan_import_folder(self) -> List[str]:
        """
        Scan import folder for CIF files.
        
        Returns:
            List[str]: List of file paths
        """
        cif_files = []
        for filename in os.listdir(IMPORT_DIR):
            if filename.endswith(".CIF") or filename.endswith(".cif"):
                cif_files.append(os.path.join(IMPORT_DIR, filename))
        return sorted(cif_files)

    def process_all_files(self):
        """Process all CIF files in the import folder."""
        files = self.scan_import_folder()
        if not files:
            logger.info("No CIF files found in import folder")
            return
        
        logger.info(f"Found {len(files)} CIF files to process")
        
        for file_path in files:
            self.process_file(file_path)
    
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
            # Parse header to get file references
            with open(file_path, 'r') as f:
                header = f.readline().strip()
            
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
                return
            
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
            
            # Now execute the truncate commands
            db.session.execute(db.text("TRUNCATE TABLE schedule_locations CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE basic_schedules CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE associations CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE parsed_files CASCADE"))
            db.session.commit()
            
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
            year = int(date_str[0:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            
            # Handle 2-digit year (assume 20xx for now)
            if year < 50:
                year += 2000
            else:
                year += 1900
                
            return dt.date(year, month, day)
        except (ValueError, IndexError):
            logger.warning(f"Invalid date format: {date_str}")
            return None
    
    def load_file_data(self, file_path: str):
        """
        Load CIF file data into the database efficiently.
        
        Args:
            file_path: Path to the CIF file
        """
        # Process file in memory-efficient manner (line by line)
        current_schedule = None
        location_seq = 0
        
        # Batch buffers
        bs_buffer = []
        sl_buffer = []
        aa_buffer = []
        
        # Batch sizes
        BS_BATCH_SIZE = 100
        SL_BATCH_SIZE = 500
        AA_BATCH_SIZE = 100
        
        try:
            with open(file_path, 'r') as f:
                # Skip header
                header_line = f.readline()
                
                # Keep track of locations for current schedule for area of interest filtering
                current_locations = []
                
                for line in f:
                    line = line.rstrip()
                    if not line or len(line) < 2:
                        continue
                    
                    record_type = line[0:2]
                    
                    # Location records (LO, LI, LT)
                    if record_type in ['LO', 'LI', 'LT']:
                        location_seq += 1
                        tiploc = line[2:10].strip()
                        
                        # Add to current locations list for area of interest filtering
                        current_locations.append({'tiploc': tiploc})
                        
                        # Only process location records if we have a valid schedule
                        if current_schedule and len(current_schedule) > 0:
                            # Initialize all fields as None
                            arr_time = None
                            dep_time = None
                            pass_time = None
                            public_arr = None
                            public_dep = None
                            platform = None
                            line_code = None
                            path_code = None
                            activity = None
                            
                            # Parse differently based on record type
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
                                self.flush_bs_buffer([current_schedule])
                            
                            # Add location to buffer
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
                                self.flush_sl_buffer(sl_buffer)
                                sl_buffer = []
                    
                    # Basic Schedule (BS)
                    elif record_type == 'BS':
                        # Check if previous schedule is in area of interest before saving
                        if current_schedule and len(current_schedule) > 0:
                            if self.is_in_area_of_interest(current_locations):
                                bs_buffer.append(current_schedule)
                                
                                # Flush buffer if full
                                if len(bs_buffer) >= BS_BATCH_SIZE:
                                    updated_bs_buffer = self.flush_bs_buffer(bs_buffer)
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
                        
                        # Parse new BS record
                        transaction_type = line[2:3]
                        
                        # Skip deletion records as per requirement
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
                
                # Check if last schedule should be saved
                if current_schedule and len(current_schedule) > 0:
                    if self.is_in_area_of_interest(current_locations):
                        bs_buffer.append(current_schedule)
                    else:
                        logger.debug(f"Skipping schedule {current_schedule.get('uid')} - not in area of interest")
                
                # Flush any remaining records
                if bs_buffer:
                    logger.info(f"Saving {len(bs_buffer)} schedules relevant to area of interest")
                    updated_bs_buffer = self.flush_bs_buffer(bs_buffer)
                    
                    # Update current schedule if it exists in buffer
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
        
        for schedule_data in buffer:
            # Skip if already has ID
            if 'id' in schedule_data:
                schedules_with_ids.append(schedule_data)
                continue
                
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
        for i, schedule_data in enumerate(buffer):
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
        
        logger.info(f"Committed {len(buffer)} basic schedules to database")
        return schedules_with_ids
    
    def flush_sl_buffer(self, buffer: List[Dict]):
        """
        Flush buffer of schedule locations to database.
        
        Args:
            buffer: List of location dictionaries
        """
        if not buffer:
            return
            
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
    with app.app_context():
        parser = CIFParser()
        parser.process_all_files()
    logger.info("Completed CIF file processing")