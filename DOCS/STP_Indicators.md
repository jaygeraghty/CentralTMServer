# STP Indicators Documentation

## Overview

STP (Schedule Type Permanence) indicators are a critical component of the UK railway scheduling system. They indicate the permanence of each schedule record and determine how different schedule variations are applied to create the final timetable.

## STP Indicator Types

There are four STP indicator types, each with a different level of precedence:

| Code | Name | Description | Precedence |
|------|------|-------------|------------|
| `P` | Permanent | Long-term base schedule | Lowest |
| `N` | New | New short-term plan schedule | Low |
| `O` | Overlay | Overlay short-term plan that modifies a permanent schedule | Medium |
| `C` | Cancellation | Cancellation of a permanent schedule | Highest |

## Database Implementation

The STP indicator system is implemented in the database with separate tables for each indicator type:

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

The same structure applies to schedule locations and associations, with corresponding tables for each STP indicator.

## STP Precedence Rules

When retrieving schedule information, STP precedence rules are applied to determine which version of a schedule should be used:

1. **Cancellations (C)** take highest precedence
2. **Overlays (O)** are next, applied only if no cancellation exists
3. **New schedules (N)** are third, used only if no cancellation or overlay exists
4. **Permanent schedules (P)** are the baseline and only used if no STP variations exist

## STP Handler Implementation

The STP handler implements the precedence rules using a sequential approach:

```python
def get_schedule_for_date_and_uid(date_str, uid):
    """
    Get schedule for a specific date and UID, applying STP precedence rules.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        uid: Schedule UID
        
    Returns:
        Schedule record with highest STP precedence
    """
    query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    day_of_week = query_date.isoweekday()
    
    # Check for cancellations first (highest precedence)
    cancellation = (ScheduleSTPCancellation.query
        .filter(
            ScheduleSTPCancellation.uid == uid,
            ScheduleSTPCancellation.runs_from <= query_date,
            ScheduleSTPCancellation.runs_to >= query_date,
            func.substr(ScheduleSTPCancellation.days_run, day_of_week, 1) == '1'
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
            func.substr(ScheduleSTPOverlay.days_run, day_of_week, 1) == '1'
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
            func.substr(ScheduleSTPNew.days_run, day_of_week, 1) == '1'
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
            func.substr(ScheduleLTP.days_run, day_of_week, 1) == '1'
        )
        .first())
    
    if permanent:
        return {'schedule': permanent, 'source_table': 'schedules_ltp'}
    
    return None
```

## Location Retrieval

Once the schedule is determined, locations are retrieved from the corresponding table:

```python
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
    
    # Map schedule table to location table
    location_table_map = {
        'schedules_ltp': 'schedule_locations_ltp',
        'schedules_stp_new': 'schedule_locations_stp_new',
        'schedules_stp_overlay': 'schedule_locations_stp_overlay',
        'schedules_stp_cancellation': 'schedule_locations_stp_cancellation'
    }
    
    location_table = location_table_map.get(table_name)
    if not location_table:
        return locations
    
    # Use raw SQL to get locations from appropriate table
    query = text(f"""
        SELECT * FROM {location_table}
        WHERE schedule_id = :schedule_id
        ORDER BY id
    """)
    
    result = db.session.execute(query, {'schedule_id': schedule_id})
    
    for row in result:
        location = {
            'tiploc': row.tiploc,
            'arrival': row.arrival,
            'departure': row.departure,
            'pass_time': row.pass_time,
            'platform': row.platform,
            'line': row.line,
            'path': row.path,
            'public_arrival': row.public_arrival,
            'public_departure': row.public_departure,
            'activity': row.activity
        }
        locations.append(location)
    
    return locations
```

## STP in API Responses

When schedules are returned via the API, the STP indicator is included to indicate the source:

```json
{
  "schedule": {
    "uid": "P19424",
    "train_identity": "1V14",
    "stp_indicator": "O",  // Shows this is an overlay schedule
    "runs_from": "2023-03-01",
    "runs_to": "2023-03-31",
    "days_run": "1111111",
    "locations": [
      {
        "tiploc": "CHRX",
        "departure": "07:20",
        "platform": "14"
      }
    ]
  },
  "source_table": "schedules_stp_overlay"  // Indicates which table provided the data
}
```

## STP in CIF Parsing

The CIF parser routes records to the appropriate tables based on their STP indicator:

```python
def flush_bs_buffer(self, buffer: List[Dict]):
    """
    Flush buffer of basic schedules to database.
    
    Args:
        buffer: List of schedule dictionaries
    """
    schedules_ltp = []
    schedules_stp_new = []
    schedules_stp_overlay = []
    schedules_stp_cancellation = []
    
    for schedule in buffer:
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
```

## STP Indicators in Associations

Associations between trains also have STP indicators and follow the same precedence rules:

```python
def get_associations_for_date_and_uid(date_str, uid):
    """
    Get associations for a specific date and UID, applying STP precedence rules.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        uid: Schedule UID (main_uid or assoc_uid)
        
    Returns:
        List of association records with highest STP precedence
    """
    query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    day_of_week = query_date.isoweekday()
    
    # Get all associations for this UID (both as main and associated)
    associations = []
    processed_pairs = set()  # Track processed (main_uid, assoc_uid) pairs
    
    # Check cancellations first (highest precedence)
    cancellations = AssociationSTPCancellation.query.filter(
        or_(
            AssociationSTPCancellation.main_uid == uid,
            AssociationSTPCancellation.assoc_uid == uid
        ),
        AssociationSTPCancellation.date_from <= query_date,
        AssociationSTPCancellation.date_to >= query_date,
        func.substr(AssociationSTPCancellation.days_run, day_of_week, 1) == '1'
    ).all()
    
    for assoc in cancellations:
        # Add to processed set
        pair = (assoc.main_uid, assoc.assoc_uid)
        processed_pairs.add(pair)
        associations.append({'association': assoc, 'source_table': 'associations_stp_cancellation'})
    
    # Similarly check overlay, new, and permanent associations...
    
    return associations
```

## STP Status Reporting

The database status API reports counts of schedules by STP indicator:

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

## Testing STP Functionality

Comprehensive tests verify the correct application of STP precedence rules:

```python
def test_cancellation_precedence(self):
    """Test that cancellations (C) take highest precedence"""
    # Check for a known schedule with a cancellation
    uid = 'P19424'
    headcode = '1V14'
    test_date = date(2025, 5, 17)  # Date when cancellation applies
    
    # Get the schedule details
    result = simplified_stp_handler.get_schedule_for_date_and_uid(
        test_date.strftime('%Y-%m-%d'), uid
    )
    
    # Verify it's a cancellation
    self.assertIsNotNone(result, f"No schedule found for {uid} on {test_date}")
    self.assertEqual(result['schedule'].stp_indicator, 'C', 
                     f"Expected cancellation but got {result['schedule'].stp_indicator}")
    self.assertEqual(result['source_table'], 'schedules_stp_cancellation',
                    f"Expected source table to be 'schedules_stp_cancellation' but got {result['source_table']}")
```

## Integration with ActiveTrains

The ActiveTrains system integrates STP handling when loading schedules:

```python
def _load_schedules(self, target_date: date):
    """
    Load all schedules that run on the specified date.
    Applies STP precedence rules: C > O > N > P
    """
    # Get the day of week (1-7 where 1 is Monday)
    day_of_week = target_date.isoweekday()
    
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
    # Step 3: Process new schedules
    # Step 4: Process permanent schedules
    # ... (similar logic for each STP type)
```

## Real-World Example

To illustrate STP indicators in action, consider a train service that normally runs daily:

1. **Permanent Schedule (P)**: Train P19424 (1V14) runs from CHRX to WLOE at 07:15 daily, 2023-01-01 to 2023-12-31
2. **Overlay (O)**: In March 2023, there's engineering work so train P19424 (1V14) departs at 07:20 instead, 2023-03-01 to 2023-03-31
3. **Cancellation (C)**: On April 7, 2023 (Good Friday), train P19424 is cancelled, 2023-04-07 to 2023-04-07
4. **New (N)**: During a special event, new train N12345 (9V99) runs from CHRX to WLOE at 08:30, 2023-05-20 to 2023-05-21

When querying for train P19424 on different dates, the STP precedence ensures:
- January 15: Shows the permanent schedule (P) with 07:15 departure
- March 15: Shows the overlay schedule (O) with 07:20 departure
- April 7: Shows the cancellation (C)
- May 1: Shows the permanent schedule (P) again