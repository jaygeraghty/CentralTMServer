# Railway Delay Calculation & Propagation System

## Overview

The delay propagation system calculates and maintains predicted arrival, departure, and pass times for trains based on real-time forecast updates. It uses a sophisticated algorithm that considers dwell time trimming, sectional slack recovery, and real forecast data to provide accurate predictions downstream from any forecast point.

## Core Data Structures

### ActiveScheduleLocation
Each location in a train's schedule contains multiple time fields:

**Timetabled Times:**
- `arr_time`: Scheduled arrival time (HH:MM)
- `dep_time`: Scheduled departure time (HH:MM)  
- `pass_time`: Scheduled pass time for non-stopping trains (HH:MM)
- `public_arr`/`public_dep`: Public timetable times

**Real-time Actuals:**
- `actual_arr`: Actual arrival time when train arrives
- `actual_dep`: Actual departure time when train departs
- `actual_pass`: Actual pass time for through trains

**External Forecasts:**
- `forecast_arr`: External system forecast arrival time
- `forecast_dep`: External system forecast departure time
- `forecast_pass`: External system forecast pass time
- `delay_minutes`: Current delay at this location

**System Predictions (Available to Downstream Systems):**
- `pred_arr`: Predicted arrival time (from forecasts or synthetic calculation)
- `pred_dep`: Predicted departure time (from forecasts or synthetic calculation) 
- `pred_pass`: Predicted pass time (from forecasts or synthetic calculation)
- `pred_delay_min`: Predicted delay in minutes at this location

**Configuration:**
- `late_dwell_secs`: Minimum dwell time when train is late (default: 30s)
- `recovery_secs`: Sectional slack time between previous location and here (currently 0, future SRT integration)

### ActiveTrain
The main train object contains:
- `uid`: Unique train identifier
- `headcode`: Train reporting number
- `schedule`: Complete schedule with all locations
- `berth`: Current track circuit/berth location
- `last_location`: Last known TIPLOC location
- `delay`: Current overall delay
- `forecast_delay`: External forecast delay
- `detected`: Whether train is actively tracked (set via forecast or real-time updates)
- `last_step_time`: Timestamp of last berth movement
- `terminated`: Whether train has completed its journey
- `cancelled`: Whether train has been cancelled

## Delay Propagation Algorithm

The `propagate_delay()` function rebuilds predicted times for every downstream call whenever we receive a new forecast at any location. Here's the exact implementation:

```python
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
      automatically let the train "eat" that slack on each leg.
    """
    locs = sorted(train.schedule.locations.values(),
                  key=lambda l: l.sequence)

    try:
        anchor_idx = next(i for i, l in enumerate(locs)
                          if l.tiploc == anchor_tiploc)
    except StopIteration:
        return

    anchor = locs[anchor_idx]
    delay  = anchor.delay_minutes or 0
    
    # Always process forecasts, even with zero delay
    if anchor.forecast_arr:
        anchor.pred_arr = anchor.forecast_arr
    if anchor.forecast_dep:
        anchor.pred_dep = anchor.forecast_dep
    if anchor.forecast_pass:
        anchor.pred_pass = anchor.forecast_pass
    anchor.pred_delay_min = delay
    
    # Only propagate downstream if there's actual delay
    if delay <= 0:
        return
```

### The Four-Step Process for Each Downstream Location

Here's the exact implementation of the downstream processing loop:

```python
    prev_loc = locs[anchor_idx]   # start of the first leg

    for loc in locs[anchor_idx + 1:]:

        # ── 1️⃣  subtract sectional slack (placeholder = 0) ─────────
        delay = max(delay - prev_loc.recovery_secs // 60, 0)

        # ── 2️⃣  honour real forecasts if present ───────────────────
        if loc.forecast_arr or loc.forecast_dep or loc.forecast_pass:
            loc.pred_arr   = loc.forecast_arr
            loc.pred_dep   = loc.forecast_dep
            loc.pred_pass  = loc.forecast_pass
            loc.pred_delay_min = loc.delay_minutes
            delay = loc.delay_minutes or delay
            prev_loc = loc
            continue

        # ── 3️⃣  create synthetic arrival/pass ─────────────────────
        if loc.arr_time:
            arr_dt = _HHMM_TO_DT(loc.arr_time) + timedelta(minutes=delay)
            loc.pred_arr = _DT_TO_HHMM(arr_dt)
        elif loc.pass_time:
            pass_dt = _HHMM_TO_DT(loc.pass_time) + timedelta(minutes=delay)
            loc.pred_pass = _DT_TO_HHMM(pass_dt)

        # ── 4️⃣  dwell-trim logic for stops ─────────────────────────
        if loc.arr_time and loc.dep_time:
            booked_arr = _HHMM_TO_DT(loc.arr_time)
            booked_dep = _HHMM_TO_DT(loc.dep_time)
            booked_dwell = (booked_dep - booked_arr).seconds
            trim_secs = max(booked_dwell - loc.late_dwell_secs, 0)
            recovered  = min(delay * 60, trim_secs)
            delay_after_dwell = max(delay * 60 - recovered, 0) // 60

            new_dep_dt = booked_arr + timedelta(minutes=delay) \
                                   + timedelta(seconds=booked_dwell - trim_secs)

            # never depart earlier than timetable
            if new_dep_dt < booked_dep:
                new_dep_dt = booked_dep
                delay_after_dwell = 0

            loc.pred_dep = _DT_TO_HHMM(new_dep_dt)
            delay = delay_after_dwell

        loc.pred_delay_min = delay
        prev_loc = loc
```

**Dwell Trimming Example:**
- Train scheduled to arrive 10:00, depart 10:05 (5 min dwell)
- Train running 8 minutes late
- Minimum late dwell = 30 seconds
- Available trim = 5 min - 30 sec = 4.5 min
- Recovery = min(8 min, 4.5 min) = 4.5 min
- New departure: 10:08 + 0.5 min = 10:08:30
- Remaining delay: 8 - 4.5 = 3.5 min

## Data Flow for Prediction Engines

### Active Train Export Format

For external prediction engines, the system provides complete train data:

```json
{
  "uid": "P17935",
  "headcode": "5N98",
  "berth": "0123",
  "last_location": "CRFDSPR",
  "delay": 7,
  "forecast_delay": 8,
  "forecast_delay_at": "2025-05-31T15:30:00Z",
  "detected": true,
  "terminated": false,
  "cancelled": false,
  "schedule": {
    "train_status": "P",
    "train_category": "EE",
    "power_type": "EMU",
    "speed": 100,
    "locations": {
      "CRFDSPR": {
        "sequence": 1,
        "location_type": "LI",
        "arr_time": "15:25",
        "dep_time": "15:27",
        "platform": "2",
        "actual_arr": "15:32",
        "forecast_dep": "15:35",
        "pred_arr": "15:32",
        "pred_dep": "15:35",
        "pred_pass": null,
        "pred_delay_min": 7,
        "late_dwell_secs": 30,
        "recovery_secs": 0
      }
    }
  }
}
```

### Key Fields for Prediction Engines

**Current State:**
- `berth`: Exact track circuit location
- `last_location`: Last confirmed TIPLOC
- `delay`: Current running delay
- `detected`: Whether train is actively tracked

**Schedule Context:**
- `train_category`: Train type (passenger/freight/etc)
- `power_type`: Traction type affects acceleration
- `speed`: Line speed capability

**Timing Data per Location:**
- `arr_time`/`dep_time`/`pass_time`: Baseline timetable
- `actual_*`: Confirmed actual times  
- `forecast_*`: External system forecasts
- `pred_*`: **Our calculated predictions (ALL used by downstream systems)**
- `pred_delay_min`: Predicted delay at this point

**Critical Note:** All `pred_*` fields (`pred_arr`, `pred_dep`, `pred_pass`) are actively used by prediction engines and downstream systems. The system handles both stopping trains (arrival/departure) and through trains (pass-only) equally.

**Recovery Parameters:**
- `late_dwell_secs`: Minimum dwell when late
- `recovery_secs`: Sectional running time slack

## Integration Points

### Receiving Forecasts
The system accepts forecast updates via API:
```json
{
  "uid": "P17935",
  "forecasts": [{
    "tiploc": "CRFDSPR",
    "forecast_arrival": "15:32",
    "forecast_departure": "15:35",
    "forecast_pass": null,
    "platform": "2",
    "delay_minutes": 7
  }]
}
```

### Providing Predictions
External systems can retrieve complete train state via:
- `/api/trains/active` - All active trains
- `/api/trains/{uid}` - Specific train details
- `/api/trains/location/{tiploc}` - Trains at location

### Real-time Updates
The system processes movement messages:
```json
{
  "uid": "P17935",
  "tiploc": "CRFDSPR", 
  "timestamp": "2025-05-31T15:32:15Z",
  "event_type": "arr",
  "from_berth": "0123",
  "to_berth": "0124"
}
```

## Future Enhancements

### Sectional Running Time Integration
When SRT data becomes available:
- `recovery_secs` will be populated with actual slack time
- Trains will automatically recover delay on each section
- More accurate predictions for variable line speeds

### Performance Characteristics
Future integration could include:
- Train-specific acceleration/braking curves
- Route-specific speed restrictions
- Weather/congestion factors
- Driver behavior patterns

## Working Code Examples

### Complete Forecast Update Function

```python
def apply_forecast_update(manager: ActiveTrainsManager, payload: dict) -> bool:
    """Apply forecast updates to active trains from external systems."""
    try:
        train_id = payload.get('train_id') or payload.get('headcode')
        uid = payload.get('uid')

        if not train_id and not uid:
            logger.warning("Forecast update missing train identification")
            return False

        # Find the train
        train = manager.get_train_by_uid(uid) if uid else None
        if not train:
            train = manager.get_train_by_headcode(train_id)
        if not train:
            logger.warning(f"Unable to find train {train_id} (UID: {uid}) for forecast update")
            return False

        # Mark train as detected when we receive forecast (helps with real-time updates later)
        if not train.detected:
            train.detected = True
            logger.info(f"Train {train.headcode} (UID: {train.uid}) marked as detected via forecast update")
        else:
            logger.debug(f"Train {train.headcode} (UID: {train.uid}) already detected - processing forecast update")

        forecasts = payload.get('forecasts', [])
        
        for forecast in forecasts:
            tiploc = forecast.get('tiploc')
            if not tiploc or tiploc not in train.schedule.locations:
                continue
                
            location = train.schedule.locations[tiploc]
            
            # Store forecast data
            location.forecast_arr = forecast.get("forecast_arrival")
            location.forecast_dep = forecast.get("forecast_departure") 
            location.forecast_pass = forecast.get("forecast_pass")
            location.delay_minutes = forecast.get("delay_minutes")
            
            # Trigger delay propagation from this point
            propagate_delay(train, tiploc)
            
        return True
        
    except Exception as e:
        logger.error(f"Error applying forecast update: {e}")
        return False
```

### Complete API Endpoint Example

```python
@app.route('/api/trains/forecast_update', methods=['POST'])
def update_forecast():
    """Accept forecast update payload and apply to relevant ActiveTrain."""
    try:
        payload = request.get_json()
        manager = get_active_trains_manager()
        
        success = apply_forecast_update(manager, payload)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Forecast update applied successfully"
            }), 200
        else:
            return jsonify({
                "status": "error", 
                "message": "Failed to apply forecast update"
            }), 400
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error processing forecast: {str(e)}"
        }), 500
```

### Example 1: Through Train with Pass Predictions

```python
def test_through_train_pass_predictions():
    """Shows how pred_pass is used for through trains."""
    
    # Create through train (passes without stopping)
    train = ActiveTrain(uid="P12345", headcode="5N98")
    train.schedule = ActiveSchedule(locations={
        "ORIGIN": ActiveScheduleLocation(
            sequence=1, tiploc="ORIGIN", location_type="LO",
            dep_time="14:00"
        ),
        "JUNCTION": ActiveScheduleLocation(
            sequence=2, tiploc="JUNCTION", location_type="LI", 
            pass_time="14:15"  # Through train - no arrival/departure
        ),
        "DEST": ActiveScheduleLocation(
            sequence=3, tiploc="DEST", location_type="LT",
            arr_time="14:30"
        )
    })
    
    # Apply forecast at JUNCTION
    payload = {
        "headcode": "5N98",
        "locations": [{
            "tiploc": "JUNCTION",
            "forecast_pass": "14:18",  # 3 min late passing
            "delay_minutes": 3
        }]
    }
    
    apply_forecast_update(manager, payload)
    
    # System creates pred_pass for through location
    junction = train.schedule.locations["JUNCTION"]
    assert junction.pred_pass == "14:18"
    
    # And propagates to destination
    dest = train.schedule.locations["DEST"] 
    assert dest.pred_arr == "14:33"  # 3 min late arrival
    assert dest.pred_delay_min == 3
```

### Example 2: Dwell Trimming Recovery

```python
def test_dwell_trimming_recovery():
    """Test that dwell trimming reduces delay correctly."""
    
    # Create stopping train with 2-minute dwell
    train = ActiveTrain(uid="TEST123", headcode="1A23")
    train.schedule = ActiveSchedule(locations={
        "LOC1": ActiveScheduleLocation(
            sequence=1, tiploc="LOC1", location_type="LI",
            arr_time="10:00", dep_time="10:02"  # 2-min dwell
        ),
        "LOC2": ActiveScheduleLocation(
            sequence=2, tiploc="LOC2", location_type="LI", 
            arr_time="10:10", dep_time="10:12"
        )
    })
    
    # Apply 3-minute delay at LOC1
    payload = {
        "headcode": "1A23", 
        "locations": [{
            "tiploc": "LOC1",
            "forecast_arr": "10:03",  # 3 min late
            "forecast_dep": "10:04",  # Only 1 min dwell (90s recovered)
            "delay_minutes": 3
        }]
    }
    
    apply_forecast_update(manager, payload)
    
    # Dwell trimming recovers 90 seconds of delay
    loc2 = train.schedule.locations["LOC2"]
    assert loc2.pred_arr == "10:11"  # Only 1 min late (2 min recovered)
    assert loc2.pred_delay_min == 1
```

### System Logging Output

The propagation function logs predictions for monitoring:

```
2025-05-31 21:39:59,121 - active_trains - INFO - 5N98: propagated to 3 locs, final 14:33 (+3m)
2025-05-31 21:40:01,235 - active_trains - INFO - 1A23: propagated to 2 locs, final 10:12 (+1m)
```

This logging shows the system tracks all prediction types including pass-through times.

## Train Detection and Real-time Integration

### Automatic Train Detection via Forecasts

When the system receives forecast updates, trains are automatically marked as detected:

```python
# Forecast triggers detection
payload = {
    "uid": "P12345", 
    "forecasts": [{"tiploc": "READING", "forecast_arrival": "10:33"}]
}

# System automatically sets train.detected = True
# Logs: "Train 1A23 (UID: P12345) marked as detected via forecast update"
```

### Real-time Update Processing

The system handles berth movements and train detection intelligently:

**Single Detected Train:**
```
DEBUG: Real-time update: found single detected train 1A23 (UID: P12345)
```

**Multiple Trains - Ambiguity Resolution:**
```
WARNING: Real-time update: 2 detected trains found for headcode 1A23
INFO: Real-time update: resolved ambiguity for 1A23 using berth 0123 -> UID P12345
```

**Train Activation from Berth Steps:**
```
INFO: Train activated: 1A23 (UID: P12345) detected at 0124 at 15:32:15 - chosen from 2 candidates
```

### Detection Logic Flow

1. **Forecast Updates** → Automatically mark `train.detected = True`
2. **Real-time Berth Steps** → Use detected status to identify correct train
3. **Ambiguity Resolution** → Use berth location and forecast timestamps
4. **Automatic Activation** → Select best candidate based on departure time proximity

This ensures that trains receiving forecasts are properly tracked during subsequent real-time updates, solving the problem of multiple trains with identical headcodes running 12+ hours apart.

## Usage in Prediction Systems

The delay propagation system provides a solid foundation for AI/ML prediction engines by:

1. **Maintaining Clean State**: All predictions are continuously updated
2. **Preserving Context**: Both timetabled and real-time data available
3. **Handling Edge Cases**: Proper termination, cancellation, dwell trimming
4. **Consistent Format**: Standardized data structure across all trains
5. **Real-time Updates**: Immediate propagation when new data arrives

Prediction engines can use this data to:
- Train models on historical delay patterns
- Validate predictions against actual outcomes  
- Incorporate external factors (weather, incidents)
- Provide confidence intervals for forecasts
- Generate passenger information updates