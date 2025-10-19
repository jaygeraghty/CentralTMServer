# Database Operations Documentation

## Overview

This document describes the database schema and operations for the UK railway data system. Our application uses SQLAlchemy with PostgreSQL to store and manage railway schedule data from CIF files.

## Database Schema

### Core Models

Our database schema uses class mixins to share common fields across different STP (Schedule Type Permanence) indicator tables:

```python
class ScheduleMixin:
    """Common fields for all schedule tables."""
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(6), index=True, nullable=False)
    runs_from = db.Column(db.Date, nullable=False)
    runs_to = db.Column(db.Date, nullable=False)
    days_run = db.Column(db.String(7), nullable=False)
    train_status = db.Column(db.String(1))
    train_category = db.Column(db.String(2))
    train_identity = db.Column(db.String(4))
    headcode = db.Column(db.String(4))
    service_code = db.Column(db.String(8))
    portion_id = db.Column(db.String(1))
    power_type = db.Column(db.String(3))
    timing_load = db.Column(db.String(4))
    speed = db.Column(db.Integer)
    operating_chars = db.Column(db.String(6))
    train_class = db.Column(db.String(1))
    sleepers = db.Column(db.String(1))
    reservations = db.Column(db.String(1))
    catering = db.Column(db.String(4))
    branding = db.Column(db.String(4))
    uic_code = db.Column(db.String(5))
    atoc_code = db.Column(db.String(2))
    applicable_timetable = db.Column(db.String(1))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LocationMixin:
    """Common fields for all schedule location tables."""
    id = db.Column(db.Integer, primary_key=True)
    tiploc = db.Column(db.String(7), index=True)
    tiploc_instance = db.Column(db.String(1))
    arrival = db.Column(db.String(5))
    departure = db.Column(db.String(5))
    pass_time = db.Column(db.String(5))
    public_arrival = db.Column(db.String(4))
    public_departure = db.Column(db.String(4))
    platform = db.Column(db.String(3))
    line = db.Column(db.String(3))
    path = db.Column(db.String(3))
    activity = db.Column(db.String(12))
    engineering_allowance = db.Column(db.String(2))
    pathing_allowance = db.Column(db.String(2))
    performance_allowance = db.Column(db.String(2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AssociationMixin:
    """Common fields for all association tables."""
    id = db.Column(db.Integer, primary_key=True)
    main_uid = db.Column(db.String(6), index=True, nullable=False)
    assoc_uid = db.Column(db.String(6), index=True, nullable=False)
    category = db.Column(db.String(2), nullable=False)
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    days_run = db.Column(db.String(7), nullable=False)
    location = db.Column(db.String(7), nullable=False)
    base_suffix = db.Column(db.String(1))
    assoc_suffix = db.Column(db.String(1))
    diagram_type = db.Column(db.String(1))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### STP-specific Tables

We maintain separate tables for each STP indicator type (P, N, O, C):

```python
class ScheduleLTP(db.Model, ScheduleMixin):
    """Long Term Plan schedule (STP indicator 'P')."""
    __tablename__ = 'schedules_ltp'
    transaction_type = db.Column(db.String(1))
    stp_indicator = db.Column(db.String(1), default='P')

class ScheduleSTPNew(db.Model, ScheduleMixin):
    """New Short Term Plan schedule (STP indicator 'N')."""
    __tablename__ = 'schedules_stp_new'
    transaction_type = db.Column(db.String(1))
    stp_indicator = db.Column(db.String(1), default='N')

class ScheduleSTPOverlay(db.Model, ScheduleMixin):
    """Overlay Short Term Plan schedule (STP indicator 'O')."""
    __tablename__ = 'schedules_stp_overlay'
    transaction_type = db.Column(db.String(1))
    stp_indicator = db.Column(db.String(1), default='O')

class ScheduleSTPCancellation(db.Model, ScheduleMixin):
    """Cancellation Short Term Plan schedule (STP indicator 'C')."""
    __tablename__ = 'schedules_stp_cancellation'
    transaction_type = db.Column(db.String(1))
    stp_indicator = db.Column(db.String(1), default='C')
```

And similarly for schedule locations and associations:

```python
class ScheduleLocationLTP(db.Model, LocationMixin):
    """Schedule location for Long Term Plan schedules."""
    __tablename__ = 'schedule_locations_ltp'
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules_ltp.id', ondelete='CASCADE'))
    schedule = db.relationship('ScheduleLTP', backref=db.backref('locations', lazy=True, cascade='all, delete-orphan'))
    
# Similar classes for STPNew, STPOverlay, and STPCancellation location tables

class AssociationLTP(db.Model, AssociationMixin):
    """Long Term Plan association (STP indicator 'P')."""
    __tablename__ = 'associations_ltp'
    transaction_type = db.Column(db.String(1))
    stp_indicator = db.Column(db.String(1), default='P')

# Similar classes for STPNew, STPOverlay, and STPCancellation association tables
```

## Database Connection

The database connection is configured through environment variables:

```python
# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
# Initialize the app with the extension
db.init_app(app)
```

## Key Database Operations

### 1. Bulk Inserts

For performance, we use SQLAlchemy's bulk insert functionality to efficiently add records:

```python
def flush_bs_buffer(self, buffer: List[Dict]):
    """
    Flush buffer of basic schedules to database.
    
    Args:
        buffer: List of schedule dictionaries
    """
    # Route to appropriate tables by STP indicator
    schedules_ltp = []
    schedules_stp_new = []
    schedules_stp_overlay = []
    schedules_stp_cancellation = []
    
    for schedule in buffer:
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
```

### 2. Database Reset

We provide functionality to reset database tables for full extract processing:

```python
def _truncate_all_tables(self):
    """Truncate all database tables for a full extract."""
    tables = [
        "parsed_files",
        "schedule_locations_ltp",
        "schedule_locations_stp_new",
        "schedule_locations_stp_overlay",
        "schedule_locations_stp_cancellation",
        "schedules_ltp",
        "schedules_stp_new",
        "schedules_stp_overlay",
        "schedules_stp_cancellation",
        "associations_ltp",
        "associations_stp_new",
        "associations_stp_overlay",
        "associations_stp_cancellation"
    ]
    
    with db.engine.connect() as connection:
        # Disable foreign key checks for the session
        connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        
        # Truncate each table
        for table in tables:
            connection.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        
        # Commit transaction
        connection.commit()
    
    self.logger.info("All database tables truncated successfully for full extract")
```

### 3. STP Precedence Queries

We implement STP precedence rules (C > O > N > P) when retrieving schedule data:

```python
def get_schedules_for_date_and_uid(date_str, uid):
    """
    Get schedules for a specific date and UID, applying STP precedence rules.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        uid: Schedule UID
        
    Returns:
        Schedule record with highest STP precedence
    """
    query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    # Check for cancellations first (highest precedence)
    cancellation = (ScheduleSTPCancellation.query
        .filter(
            ScheduleSTPCancellation.uid == uid,
            ScheduleSTPCancellation.runs_from <= query_date,
            ScheduleSTPCancellation.runs_to >= query_date,
            func.substr(ScheduleSTPCancellation.days_run, extract('dow', func.date(date_str)), 1) == '1'
        )
        .first())
    
    if cancellation:
        return {'schedule': cancellation, 'source_table': 'schedules_stp_cancellation'}
    
    # Check for overlays next
    overlay = (ScheduleSTPOverlay.query
        .filter(
            ScheduleSTPOverlay.uid == uid,
            ScheduleSTPOverlay.runs_from <= query_date,
            ScheduleSTPOverlay.runs_to >= query_date,
            func.substr(ScheduleSTPOverlay.days_run, extract('dow', func.date(date_str)), 1) == '1'
        )
        .first())
    
    if overlay:
        return {'schedule': overlay, 'source_table': 'schedules_stp_overlay'}
    
    # Check for new schedules next
    new_schedule = (ScheduleSTPNew.query
        .filter(
            ScheduleSTPNew.uid == uid,
            ScheduleSTPNew.runs_from <= query_date,
            ScheduleSTPNew.runs_to >= query_date,
            func.substr(ScheduleSTPNew.days_run, extract('dow', func.date(date_str)), 1) == '1'
        )
        .first())
    
    if new_schedule:
        return {'schedule': new_schedule, 'source_table': 'schedules_stp_new'}
    
    # Finally check permanent schedules
    permanent = (ScheduleLTP.query
        .filter(
            ScheduleLTP.uid == uid,
            ScheduleLTP.runs_from <= query_date,
            ScheduleLTP.runs_to >= query_date,
            func.substr(ScheduleLTP.days_run, extract('dow', func.date(date_str)), 1) == '1'
        )
        .first())
    
    if permanent:
        return {'schedule': permanent, 'source_table': 'schedules_ltp'}
    
    return None
```

### 4. In-Memory Data Management with ActiveTrains

We maintain an in-memory cache of active trains for faster queries:

```python
class ActiveTrainsManager:
    """
    Manages the collection of active trains in the system.
    This is loaded on server startup and kept updated during operation.
    """
    
    def __init__(self):
        """Initialize the ActiveTrains manager."""
        self.trains_by_uid = {}
        self.trains_by_headcode = {}
        self.trains_by_location = defaultdict(list)
        self.logger = logging.getLogger(__name__)
    
    def refresh_data(self, target_date: Optional[date] = None):
        """
        Refresh active trains data for the current date or a specified date.
        """
        if not target_date:
            target_date = date.today()
            
        self.logger.info(f"Refreshing active trains data for date: {target_date}")
        
        # Clear existing data
        self.trains_by_uid.clear()
        self.trains_by_headcode.clear()
        self.trains_by_location.clear()
        
        # Load schedules for today
        self._load_schedules(target_date)
        
        # Load associations
        self._load_associations(target_date)
        
        self.logger.info(f"Loaded {len(self.trains_by_uid)} active trains for {target_date}")
```

## Database Status and Monitoring

We provide functions to check database status and record counts:

```python
def get_db_status():
    """
    Get current database status showing counts of different schedule and association types.
    
    Returns:
        JSON response with counts of schedules and associations by STP indicator
    """
    # Count schedules by STP indicator
    ltp_count = db.session.query(func.count(ScheduleLTP.id)).scalar()
    stp_new_count = db.session.query(func.count(ScheduleSTPNew.id)).scalar()
    stp_overlay_count = db.session.query(func.count(ScheduleSTPOverlay.id)).scalar()
    stp_cancel_count = db.session.query(func.count(ScheduleSTPCancellation.id)).scalar()
    
    # Count associations by STP indicator
    assoc_ltp_count = db.session.query(func.count(AssociationLTP.id)).scalar()
    assoc_stp_new_count = db.session.query(func.count(AssociationSTPNew.id)).scalar()
    assoc_stp_overlay_count = db.session.query(func.count(AssociationSTPOverlay.id)).scalar()
    assoc_stp_cancel_count = db.session.query(func.count(AssociationSTPCancellation.id)).scalar()
    
    return jsonify({
        'schedules': {
            'ltp': ltp_count,
            'stp_new': stp_new_count,
            'stp_overlay': stp_overlay_count,
            'stp_cancellation': stp_cancel_count,
            'total': ltp_count + stp_new_count + stp_overlay_count + stp_cancel_count
        },
        'associations': {
            'ltp': assoc_ltp_count,
            'stp_new': assoc_stp_new_count,
            'stp_overlay': assoc_stp_overlay_count,
            'stp_cancellation': assoc_stp_cancel_count,
            'total': assoc_ltp_count + assoc_stp_new_count + assoc_stp_overlay_count + assoc_stp_cancel_count
        }
    })
```

## Migration Tools

We provide tools to migrate data between different database schema versions:

```python
def move_locations_to_stp_tables():
    """Move location data from legacy table to STP-specific tables based on schedule STP indicator"""
    # Get a connection to the database
    with db.engine.connect() as connection:
        # Step 1: Get all schedule IDs and their STP indicators
        schedules = connection.execute(text("""
            SELECT id, stp_indicator FROM schedules
        """)).fetchall()
        
        # Step 2: For each schedule, move its locations to the appropriate STP table
        for schedule_id, stp_indicator in schedules:
            # Get all locations for this schedule
            locations = connection.execute(text(f"""
                SELECT * FROM schedule_locations 
                WHERE schedule_id = {schedule_id}
            """)).fetchall()
            
            # Skip if no locations
            if not locations:
                continue
                
            # Insert locations into appropriate STP table
            target_table = ''
            if stp_indicator == 'P':
                target_table = 'schedule_locations_ltp'
            elif stp_indicator == 'N':
                target_table = 'schedule_locations_stp_new'
            elif stp_indicator == 'O':
                target_table = 'schedule_locations_stp_overlay'
            elif stp_indicator == 'C':
                target_table = 'schedule_locations_stp_cancellation'
                
            for loc in locations:
                # Create insert statement with all fields
                fields = [f"'{field}'" if isinstance(field, str) else str(field) for field in loc[1:]]
                
                # Replace schedule_id with appropriate value based on table
                fields[0] = str(schedule_id)
                
                connection.execute(text(f"""
                    INSERT INTO {target_table} VALUES (
                        default, {', '.join(fields)}
                    )
                """))
            
        # Commit all changes
        connection.commit()
```

## Database Connection Pooling

We utilize connection pooling for better performance and reliability:

```python
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,  # Recycle connections after 5 minutes
    "pool_pre_ping": True,  # Check connection validity before use
    "pool_size": 10,      # Maximum number of connections in the pool
    "max_overflow": 20    # Maximum number of connections that can be created beyond pool_size
}
```

## Database Schema Initialization

Database schema is created on application startup:

```python
with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401

    db.create_all()
```