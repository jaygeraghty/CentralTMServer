# CIF Parser Documentation

## Overview

The Common Interface File (CIF) parser is the core component of the system that processes UK railway timetable data. It reads CIF format files, parses their content, and loads the data into the appropriate database tables.

## Key Components

### CIFParser Class

The main class responsible for parsing and processing CIF files. It handles both full extracts (complete replacement of data) and update extracts (incremental updates).

```python
class CIFParser:
    """
    Parser for UK railway CIF (Common Interface File) data.
    """
    
    def __init__(self):
        """Initialize the CIF parser."""
        # Configure area of interest filter - locations we care about
        self.area_of_interest = app.config.get('AREA_OF_INTEREST', {'CHRX', 'WLOE'})
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Using area of interest: {self.area_of_interest}")
        
        # Performance metrics
        self.file_read_time = 0
        self.bs_processing_time = 0
        self.location_processing_time = 0
        self.aa_processing_time = 0
        self.db_flush_time = 0
```

## File Processing Workflow

### 1. Scanning Import Folder

The parser continually checks the import folder for new CIF files to process:

```python
def scan_import_folder(self) -> List[str]:
    """
    Scan import folder for CIF files.
    
    Returns:
        List[str]: List of file paths
    """
    import_folder = "import"
    file_paths = []
    
    if os.path.exists(import_folder):
        for filename in os.listdir(import_folder):
            if filename.endswith(".CIF"):
                file_paths.append(os.path.join(import_folder, filename))
    
    return file_paths
```

### 2. Processing Files

Files are processed based on their type (full extract or update):

```python
def process_file(self, file_path: str):
    """
    Process a single CIF file.
    
    Args:
        file_path: Path to the CIF file
    """
    self.logger.info(f"Processing file: {file_path}")
    
    # Skip already processed files
    last_file_ref = self.get_last_processed_file_ref()
    
    # Bypass sequence check for test files
    if 'test' in file_path.lower():
        self.logger.info(f"Test file detected, bypassing sequence check: {file_path}")
    else:
        try:
            # Check file header to determine if it's next in sequence
            with open(file_path, 'r') as f:
                header_lines = [next(f) for _ in range(2)]
                
            if len(header_lines) >= 2:
                # Extract file ref from the header
                file_ref = header_lines[1][2:9]
                
                if last_file_ref and last_file_ref >= file_ref:
                    self.logger.info(f"File already processed (ref: {file_ref}): {file_path}")
                    return
        except Exception as e:
            self.logger.error(f"Error reading file header: {e}")
            return
    
    # Check if this is a full extract or update
    is_full_extract = self._is_full_extract(file_path)
    
    if is_full_extract:
        self.process_full_extract(file_path, file_ref if 'file_ref' in locals() else None)
    else:
        self.process_update_extract(file_path, file_ref if 'file_ref' in locals() else None)
```

### 3. Parsing CIF Records

The parser handles different record types in the CIF file:

```python
def load_file_data(self, file_path: str):
    """
    Load CIF file data into the database efficiently.
    
    Args:
        file_path: Path to the CIF file
    """
    # Initialize buffers for batch processing
    bs_buffer = []  # Basic Schedule buffer
    sl_buffer = []  # Schedule Location buffer
    aa_buffer = []  # Association buffer
    
    current_bs_id = None
    current_transaction_type = None
    current_uid = None
    current_stp_indicator = None
    locations = []
    in_location_block = False
    record_count = 0
    
    # Use buffered reading for efficiency
    start_time = time.time()
    
    with open(file_path, 'r') as f:
        for line in f:
            record_type = line[0:2]
            record_count += 1
            
            # Process based on record type
            if record_type == 'HD':
                # Header record - extract file details
                continue
                
            elif record_type == 'BS':
                # Basic Schedule record - start of a new train schedule
                
                # If we were processing a schedule, flush its locations
                if current_bs_id is not None and locations:
                    sl_data = {
                        'schedule_id': current_bs_id,
                        'locations': locations,
                        'transaction_type': current_transaction_type,
                        'stp_indicator': current_stp_indicator
                    }
                    sl_buffer.append(sl_data)
                
                # Extract schedule details
                bs_data = self._parse_basic_schedule(line)
                
                # Reset for new schedule
                locations = []
                current_uid = bs_data['uid']
                current_stp_indicator = bs_data['stp_indicator']
                current_transaction_type = bs_data['transaction_type']
                
                # Only process schedules in our area of interest later
                bs_buffer.append(bs_data)
                
            elif record_type in ('LO', 'LI', 'LT'):
                # Location records (Origin, Intermediate, Terminating)
                location_data = self._parse_schedule_location(line, record_type)
                locations.append(location_data)
                
            elif record_type == 'AA':
                # Association record - links between train schedules
                assoc_data = self._parse_association(line)
                aa_buffer.append(assoc_data)
    
    self.file_read_time = time.time() - start_time
    
    # Final schedule being processed
    if current_bs_id is not None and locations:
        sl_data = {
            'schedule_id': current_bs_id,
            'locations': locations,
            'transaction_type': current_transaction_type,
            'stp_indicator': current_stp_indicator
        }
        sl_buffer.append(sl_data)
    
    # Now we can apply area of interest filtering and flush to database
    self._process_and_save_buffers(bs_buffer, sl_buffer, aa_buffer)
```

## STP Indicator Handling

STP (Schedule Type Permanence) indicators are a key part of CIF data and determine how different versions of a schedule are applied:

```python
def _process_and_save_buffers(self, bs_buffer, sl_buffer, aa_buffer):
    """
    Process buffers after filtering by area of interest and save to database.
    
    Args:
        bs_buffer: List of basic schedule dictionaries
        sl_buffer: List of schedule location dictionaries
        aa_buffer: List of association dictionaries
    """
    # First flush BS records to get their IDs
    bs_buffer = self.flush_bs_buffer(bs_buffer)
    
    # Create schedule ID lookup
    schedule_id_map = {item['uid']: item['id'] for item in bs_buffer}
    
    # Update SL buffer with schedule IDs
    for sl_item in sl_buffer:
        uid = sl_item['uid']
        if uid in schedule_id_map:
            sl_item['schedule_id'] = schedule_id_map[uid]
    
    # Filter SL buffer to only include schedules passing through our area of interest
    filtered_sl_buffer = [
        sl_item for sl_item in sl_buffer 
        if self.is_in_area_of_interest(sl_item['locations'])
    ]
    
    # Flush filtered SL buffer to database
    self.flush_sl_buffer(filtered_sl_buffer)
    
    # Flush AA buffer to database
    self.flush_aa_buffer(aa_buffer)
```

### Routing to STP Tables

Records are routed to different tables based on their STP indicator:

```python
def flush_bs_buffer(self, buffer: List[Dict]):
    """
    Flush buffer of basic schedules to database.
    
    Args:
        buffer: List of schedule dictionaries
        
    Returns:
        The buffer with schedule IDs added
    """
    start_time = time.time()
    
    for batch in chunked(buffer, 1000):
        schedules_ltp = []
        schedules_stp_new = []
        schedules_stp_overlay = []
        schedules_stp_cancellation = []
        
        for schedule in batch:
            # Route to the appropriate table based on STP indicator
            if schedule['stp_indicator'] == 'P':
                schedules_ltp.append(schedule)
            elif schedule['stp_indicator'] == 'N':
                schedules_stp_new.append(schedule)
            elif schedule['stp_indicator'] == 'O':
                schedules_stp_overlay.append(schedule)
            elif schedule['stp_indicator'] == 'C':
                schedules_stp_cancellation.append(schedule)
        
        # Bulk insert into appropriate tables
        if schedules_ltp:
            db.session.bulk_insert_mappings(ScheduleLTP, schedules_ltp)
        if schedules_stp_new:
            db.session.bulk_insert_mappings(ScheduleSTPNew, schedules_stp_new)
        if schedules_stp_overlay:
            db.session.bulk_insert_mappings(ScheduleSTPOverlay, schedules_stp_overlay)
        if schedules_stp_cancellation:
            db.session.bulk_insert_mappings(ScheduleSTPCancellation, schedules_stp_cancellation)
        
        db.session.commit()
    
    self.db_flush_time += time.time() - start_time
    return buffer
```

## Performance Optimizations

The CIF parser includes several optimizations to handle large data files efficiently:

1. **Buffered reading**: Files are read line by line rather than loading the entire file into memory
2. **Batch processing**: Records are processed in batches to reduce database round-trips
3. **Area of interest filtering**: Only schedules passing through locations of interest are stored
4. **Bulk database operations**: Using SQLAlchemy's bulk insert mechanisms
5. **Progress tracking**: Performance metrics are tracked to identify bottlenecks

## Integration with Scheduler

The parser is integrated with a scheduler to automatically process new files:

```python
def process_cif_files():
    """Function to process CIF files in the import folder."""
    parser = CIFParser()
    parser.process_all_files()
```

## Error Handling

The parser includes robust error handling for file format issues, database operations, and more:

```python
def parse_cif_date(self, date_str: str) -> Optional[dt.date]:
    """
    Parse a CIF date string (YYMMDD).
    
    Args:
        date_str: CIF date string
        
    Returns:
        Optional[dt.date]: Parsed date or None
    """
    try:
        year = 2000 + int(date_str[0:2])
        month = int(date_str[2:4])
        day = int(date_str[4:6])
        return dt.date(year, month, day)
    except (ValueError, IndexError):
        self.logger.warning(f"Invalid date format: {date_str}")
        return None
```

## Testing

Comprehensive unit tests verify the parser's functionality:

```python
def test_parse_cif_date(self):
    """Test that CIF dates are correctly parsed"""
    # Test valid date
    self.assertEqual(
        self.parser.parse_cif_date('230501'),
        date(2023, 5, 1)
    )
    
    # Test invalid date
    self.assertIsNone(self.parser.parse_cif_date('invalid'))
```