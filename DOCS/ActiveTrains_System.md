# ActiveTrains System Documentation

## Overview

The ActiveTrains system is a core component of our railway data application that provides real-time tracking and management of currently running trains. It maintains an in-memory representation of all trains active on a particular day, improving performance for frequent queries about train status.

## Architecture

The ActiveTrains system uses a manager class (`ActiveTrainsManager`) to maintain collections of train objects, with efficient lookups by UID, headcode, and location. This in-memory approach allows for fast response times when querying active train data.

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
        self.last_updated = None
        self.logger = logging.getLogger(__name__)
```

## Data Model

### ActiveTrain

Each train is represented by an `ActiveTrain` object containing its complete schedule and real-time information:

```python
class ActiveTrain:
    """Represents an active train in the system with its complete schedule and real-time info."""
    uid: str
    headcode: str
    
    # Real-time tracking information
    berth: Optional[str] = None
    last_location: Optional[str] = None
    delay: Optional[int] = None
    forecast_delay: Optional[int] = None
    forecast_delay_at: Optional[datetime] = None
    
    # Complete schedule information
    schedule: Optional[ActiveSchedule] = None
    
    # Associations with other trains
    associations: Dict[str, List[ActiveAssociation]] = field(default_factory=lambda: {})
```

### ActiveSchedule

Each train's schedule is represented by an `ActiveSchedule` object:

```python
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
    
    # Collection of locations the train visits
    locations: Dict[str, ActiveScheduleLocation] = field(default_factory=dict)
    
    # Which table this schedule came from
    source_table: Optional[str] = field(default=None)
```

### ActiveScheduleLocation

Each location in a schedule has specific arrival, departure, and platform information:

```python
class ActiveScheduleLocation:
    """Represents a location in an active train's schedule."""
    sequence: int
    tiploc: str
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
    
    # Real-time information
    actual_arr: Optional[str] = None
    actual_dep: Optional[str] = None
    actual_platform: Optional[str] = None
    delay_minutes: Optional[int] = None
    forecast_arr: Optional[str] = None
    forecast_dep: Optional[str] = None
    forecast_platform: Optional[str] = None
```

### ActiveAssociation

Train associations (joins, divides) are represented by `ActiveAssociation` objects:

```python
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
    
    # References to associated trains
    main_train: Optional['ActiveTrain'] = None
    assoc_train: Optional['ActiveTrain'] = None
```

## Key Operations

### Initialization

The ActiveTrains system initializes on application startup, loading today's train data:

```python
def initialize_active_trains():
    """Initialize the active trains manager with today's data."""
    manager = get_active_trains_manager()
    manager.refresh_data()
    return manager
```

### Data Refresh

The system periodically refreshes its data to maintain accuracy:

```python
def refresh_data(self, target_date: Optional[date] = None):
    """
    Refresh active trains data for the current date or a specified date.
    This is typically called on server startup and periodically during operation.
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
    
    self.last_updated = datetime.now()
    self.logger.info(f"Loaded {len(self.trains_by_uid)} active trains for {target_date}")
    
    # Note: Metrics about loaded data would be added here
```

### Loading Schedules

The system loads schedules with proper STP precedence applied:

```python
def _load_schedules(self, target_date: date):
    """
    Load all schedules that run on the specified date.
    Applies STP precedence rules: C > O > N > P
    """
    # Get the day of week (1-7 where 1 is Monday)
    day_of_week = target_date.isoweekday()
    day_mask = str(day_of_week)
    
    # We'll track processed UIDs to apply STP precedence
    processed_uids = set()
    
    # Process each STP type in order of precedence
    
    # Step 1: Process cancellations first (highest precedence)
    cancellations = ScheduleSTPCancellation.query.filter(
        ScheduleSTPCancellation.runs_from <= target_date,
        ScheduleSTPCancellation.runs_to >= target_date,
        func.substr(ScheduleSTPCancellation.days_run, day_of_week, 1) == '1'
    ).all()
    
    for schedule in cancellations:
        # Add to processed set - this UID is cancelled
        processed_uids.add(schedule.uid)
        # For cancellations, we create a minimal ActiveTrain without schedule details
        train = ActiveTrain(uid=schedule.uid, headcode=schedule.train_identity)
        self.trains_by_uid[schedule.uid] = train
        if schedule.train_identity:
            self.trains_by_headcode[schedule.train_identity] = train
    
    # Step 2: Process overlays (next precedence)
    overlays = ScheduleSTPOverlay.query.filter(
        ScheduleSTPOverlay.runs_from <= target_date,
        ScheduleSTPOverlay.runs_to >= target_date,
        func.substr(ScheduleSTPOverlay.days_run, day_of_week, 1) == '1'
    ).all()
    
    for schedule in overlays:
        if schedule.uid in processed_uids:
            continue  # Skip if already processed (cancelled)
            
        processed_uids.add(schedule.uid)
        
        # Create a new ActiveTrain for this schedule
        train = ActiveTrain(uid=schedule.uid, headcode=schedule.train_identity)
        active_schedule = self._create_active_schedule(schedule, 'schedules_stp_overlay')
        train.schedule = active_schedule
        
        # Add to lookup collections
        self.trains_by_uid[schedule.uid] = train
        if schedule.train_identity:
            self.trains_by_headcode[schedule.train_identity] = train
            
        # Load locations for this schedule
        self._load_schedule_locations(train, 'schedule_locations_stp_overlay')
    
    # Similar steps for STP new schedules and permanent schedules...
```

### Querying Trains

The system provides efficient methods to retrieve train information:

```python
def get_train_by_uid(self, uid: str) -> Optional[ActiveTrain]:
    """Get a train by its UID."""
    return self.trains_by_uid.get(uid)

def get_train_by_headcode(self, headcode: str) -> Optional[ActiveTrain]:
    """Get a train by its headcode."""
    return self.trains_by_headcode.get(headcode)

def get_trains_at_location(self, tiploc: str) -> List[ActiveTrain]:
    """Get all trains that visit a specific location."""
    return self.trains_by_location.get(tiploc, [])
```

### Real-time Updates

The system can receive and process real-time updates:

```python
def update_real_time_info(self, berth=None, location=None, delay=None, 
                         forecast_delay=None, forecast_time=None):
    """Update real-time information for this train."""
    if berth is not None:
        self.berth = berth
    if location is not None:
        self.last_location = location
    if delay is not None:
        self.delay = delay
    if forecast_delay is not None:
        self.forecast_delay = forecast_delay
        self.forecast_delay_at = forecast_time or datetime.now()
```

## API Integration

The ActiveTrains system is exposed through a RESTful API:

```python
def register_active_trains_api(app):
    """Register the ActiveTrains API blueprint with the Flask app."""
    active_api = Blueprint('active_api', __name__, url_prefix='/api/active')
    
    @active_api.route('/status', methods=['GET'])
    def active_trains_status():
        """Get status of the ActiveTrains system."""
        manager = get_active_trains_manager()
        return jsonify({
            'status': 'active',
            'train_count': len(manager.trains_by_uid),
            'last_updated': manager.last_updated.isoformat() if hasattr(manager, 'last_updated') else None
        })
    
    @active_api.route('/trains', methods=['GET'])
    def list_active_trains():
        """Get a list of all active trains."""
        manager = get_active_trains_manager()
        
        # Get pagination parameters
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Get all trains and apply pagination
        all_trains = list(manager.trains_by_uid.values())
        paginated_trains = all_trains[offset:offset+limit]
        
        # Format for response
        trains_data = []
        for train in paginated_trains:
            train_data = {
                'uid': train.uid,
                'headcode': train.headcode
            }
            
            # Add schedule information if available
            if train.schedule:
                train_data.update({
                    'origin': next((loc.tiploc for loc in train.schedule.locations.values() 
                                    if loc.location_type == 'LO'), None),
                    'destination': next((loc.tiploc for loc in train.schedule.locations.values() 
                                        if loc.location_type == 'LT'), None),
                })
            
            # Add real-time information if available
            if train.last_location:
                train_data['current_location'] = train.last_location
            if train.delay is not None:
                train_data['delay'] = train.delay
                
            trains_data.append(train_data)
        
        return jsonify({
            'trains': trains_data,
            'total': len(all_trains),
            'limit': limit,
            'offset': offset
        })
    
    # More API endpoints...
    
    app.register_blueprint(active_api)
```

## Background Scheduling

The ActiveTrains system is refreshed periodically using a background scheduler:

```python
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

@scheduler.task('interval', id='refresh_trains', seconds=300)
def scheduled_refresh_trains():
    """Refresh active trains data every 5 minutes."""
    manager = get_active_trains_manager()
    manager.refresh_data()
```

## Performance Considerations

The ActiveTrains system is optimized for performance:

1. **In-Memory Storage**: Keeps all active train data in memory for fast access
2. **Indexed Collections**: Maintains trains in multiple collections indexed by UID, headcode, and location
3. **Lazy Loading**: Loads schedule details only when accessed
4. **Background Refreshes**: Updates data in the background without blocking API responses
5. **Efficient Queries**: Uses optimized database queries with proper indexing

## Singleton Pattern

The system uses a singleton pattern to ensure a single instance:

```python
_active_trains_manager = None

def get_active_trains_manager() -> ActiveTrainsManager:
    """Get the singleton instance of the ActiveTrainsManager."""
    global _active_trains_manager
    if _active_trains_manager is None:
        _active_trains_manager = ActiveTrainsManager()
    return _active_trains_manager
```