# Prediction Cycle Integration Guide

## Overview

The system processes two main types of real-time updates that feed into the prediction cycle:
1. **Forecast Updates** - External predictions from other systems
2. **TD Events** - Real-time train detection/movement events

Each update type triggers different propagation logic and provides different data for prediction engines. The system automatically manages train detection status to resolve ambiguity when multiple trains share the same headcode.

## Forecast Update Processing

### What Happens When We Receive a Forecast

When a forecast update arrives via `/api/trains/forecast_update`:

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

**Step 1: Mark Train as Detected**
```python
# First time receiving forecast for this train
if not train.detected:
    train.detected = True
    logger.info(f"Train {train.headcode} (UID: {train.uid}) marked as detected via forecast update")
else:
    logger.debug(f"Train {train.headcode} (UID: {train.uid}) already detected - processing forecast update")
```

**Step 2: Store Forecast Data**
```python
location = train.schedule.locations[tiploc]
location.forecast_arr = "15:32"
location.forecast_dep = "15:35"
location.forecast_pass = None
location.delay_minutes = 7
location.forecast_platform = "2"
```

**Step 3: Trigger Delay Propagation**
The system calls `propagate_delay(train, tiploc)` for each forecast location:

```python
# At anchor location (CRFDSPR):
location.pred_arr = "15:32"    # Copy forecast to pred field
location.pred_dep = "15:35"    # Copy forecast to pred field  
location.pred_delay_min = 7    # Store delay

# For all downstream locations, synthetic predictions stored in:
for each_downstream_location:
    location.pred_arr = calculated_time      # Synthetic arrival prediction
    location.pred_dep = calculated_time      # Synthetic departure prediction
    location.pred_pass = calculated_time     # Synthetic pass prediction
    location.pred_delay_min = propagated_delay  # Predicted delay minutes
```

### What Gets Updated

**At Forecast Location:**
- `forecast_arr/dep/pass` - External predictions stored
- `pred_arr/dep/pass` - System predictions match forecasts
- `delay_minutes` - Current delay at this point
- `forecast_platform` - Platform prediction

**At All Downstream Locations:**
- `pred_arr/dep/pass` - Recalculated synthetic predictions
- `pred_delay_min` - Propagated delay values
- Dwell trimming applied at stopping points

**Train Level:**
- `forecast_delay` - Overall train delay
- `forecast_delay_at` - Timestamp of last forecast

## Storage of Synthetic Predictions in ActiveTrain Object

When forecast updates trigger delay propagation, synthetic predictions are stored in the `pred_*` fields of each `ActiveScheduleLocation` within the train's schedule:

### Location-Level Storage Structure
```python
train.schedule.locations[tiploc] = ActiveScheduleLocation(
    # Original timetabled times
    arr_time="15:25",           # Scheduled arrival
    dep_time="15:27",           # Scheduled departure
    pass_time=None,             # Scheduled pass (if non-stopping)
    
    # External forecasts (input data)
    forecast_arr="15:32",       # External system prediction
    forecast_dep="15:35",       # External system prediction
    forecast_pass=None,         # External system prediction
    delay_minutes=7,            # External delay estimate
    
    # System-generated predictions (our output)
    pred_arr="15:32",           # Our calculated/propagated arrival
    pred_dep="15:35",           # Our calculated/propagated departure  
    pred_pass=None,             # Our calculated/propagated pass
    pred_delay_min=7,           # Our calculated delay at this point
    
    # Real actuals (when available)
    actual_arr=None,            # Confirmed actual arrival
    actual_dep=None,            # Confirmed actual departure
)
```

### Prediction Precedence Rules
The `propagate_delay()` function follows this hierarchy:

1. **At forecast locations**: `pred_*` fields copy `forecast_*` values directly
2. **At downstream locations without forecasts**: `pred_*` fields contain synthetic calculations
3. **At locations with actuals**: `pred_*` fields may be overridden by real times

## Real-time Train Detection and Ambiguity Resolution

### Train Detection States

Each `ActiveTrain` has a `detected` flag that controls real-time processing:

- **Not Detected** (`detected = False`): Train exists in timetable but not yet active
- **Detected** (`detected = True`): Train is actively tracked via forecasts or berth movements

### Detection Triggers

**Forecast Updates:**
```python
# Receiving any forecast automatically marks train as detected
train.detected = True
logger.info(f"Train {train.headcode} (UID: {train.uid}) marked as detected via forecast update")
```

**Berth Movements:**
```python
# Train activation from first berth step
chosen.detected = True
logger.info(f"Train activated: {headcode} (UID: {chosen.uid}) detected at {to_berth}")
```

### Ambiguity Resolution for Multiple Trains

When multiple trains share the same headcode (common for services 12+ hours apart):

**Single Detected Train:**
```
DEBUG: Real-time update: found single detected train 1A23 (UID: P12345)
```

**Multiple Detected Trains:**
```
WARNING: Real-time update: 2 detected trains found for headcode 1A23
INFO: Real-time update: resolved ambiguity for 1A23 using berth 0123 -> UID P12345
```

**Train Activation from Candidates:**
```
INFO: Train activated: 1A23 (UID: P12345) detected at 0124 - chosen from 2 candidates
```

This detection system ensures forecast and real-time data are correctly associated with the intended train service.

### Synthetic Calculation Details
For downstream locations without external forecasts:

```python
# Arrival predictions
if location.arr_time:
    arrival_dt = parse_time(location.arr_time) + timedelta(minutes=propagated_delay)
    location.pred_arr = format_time(arrival_dt)

# Pass predictions  
elif location.pass_time:
    pass_dt = parse_time(location.pass_time) + timedelta(minutes=propagated_delay)
    location.pred_pass = format_time(pass_dt)

# Departure predictions (with dwell trimming)
if location.dep_time:
    # Complex dwell trimming logic applies here
    location.pred_dep = calculated_departure_with_recovery
    
# Delay propagation
location.pred_delay_min = calculated_delay_after_recovery
```

### Data Available for Prediction Engines

After forecast processing, prediction engines have access to:

```json
{
  "train": {
    "uid": "P17935",
    "forecast_delay": 7,
    "forecast_delay_at": "2025-05-31T15:30:00Z",
    "schedule": {
      "locations": {
        "CRFDSPR": {
          "sequence": 1,
          "arr_time": "15:25",        // Timetabled
          "dep_time": "15:27",        // Timetabled
          "forecast_arr": "15:32",    // External forecast
          "forecast_dep": "15:35",    // External forecast
          "pred_arr": "15:32",        // Our prediction (matches forecast)
          "pred_dep": "15:35",        // Our prediction (matches forecast)
          "delay_minutes": 7,         // Delay at this point
          "forecast_platform": "2"
        },
        "NEXTSTN": {
          "sequence": 2,
          "arr_time": "15:40",        // Timetabled
          "dep_time": "15:42",        // Timetabled
          "pred_arr": "15:47",        // Synthetic prediction (15:40 + 7 min)
          "pred_dep": "15:48",        // After dwell trimming
          "pred_delay_min": 6         // Reduced due to dwell recovery
        }
      }
    }
  }
}
```

## TD Event Processing (Real-Time Movement)

### What Happens When We Detect Train Movement

When a TD event arrives via `/api/trains/realtime_update`:

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

**Step 1: Store Actual Time**
```python
location = train.schedule.locations["CRFDSPR"]
location.actual_arr = "15:32"  # Converted from timestamp
```

**Step 2: Calculate Real Delay**
```python
# Compare actual vs scheduled
sched_time = datetime.strptime("15:25", "%H:%M")  # arr_time
actual_time = timestamp  # 15:32:15
delay = (actual_time - sched_time).total_seconds() // 60  # 7 minutes
location.delay_minutes = 7
```

**Step 3: Update Train Position**
```python
train.last_location = "CRFDSPR"
train.berth = "0124"  # to_berth
train.last_step_time = timestamp
train.detected = True
```

**Step 4: Check for Termination**
```python
if tiploc == final_tiploc_in_schedule:
    train.terminated = True
    train.terminated_time = timestamp
    # Remove from active trains
```

**Step 5: Trigger Delay Propagation**
Same propagation logic runs, but now using real actual times as anchor.

### What Gets Updated

**At Detection Location:**
- `actual_arr/dep/pass` - Real confirmed time
- `delay_minutes` - Calculated from actual vs scheduled
- Position tracking updated

**Train Level:**
- `last_location` - Current confirmed location
- `berth` - Exact track circuit position
- `last_step_time` - When this update occurred
- `detected` - Marked as actively tracked
- `terminated` - If at final destination

**All Downstream Locations:**
- `pred_arr/dep/pass` - Recalculated based on real delay
- `pred_delay_min` - Propagated from actual delay

### Data Available for Prediction Engines

After TD event processing:

```json
{
  "train": {
    "uid": "P17935",
    "berth": "0124",              // Exact position
    "last_location": "CRFDSPR",   // Confirmed location
    "last_step_time": "2025-05-31T15:32:15Z",
    "detected": true,             // Actively tracked
    "schedule": {
      "locations": {
        "CRFDSPR": {
          "arr_time": "15:25",      // Timetabled
          "actual_arr": "15:32",    // Real arrival time
          "delay_minutes": 7,       // Calculated delay
          "pred_dep": "15:35"       // Predicted departure
        },
        "NEXTSTN": {
          "pred_arr": "15:47",      // Based on real 7-min delay
          "pred_delay_min": 6       // After dwell recovery
        }
      }
    }
  }
}
```

## Prediction Cycle Integration Scenarios

### Scenario 1: Forecast-Only Prediction
**Input:** External forecast at CRFDSPR (7 min late)
**System Response:**
- Store forecast data
- Propagate 7-min delay downstream
- Apply dwell trimming at stops
- Provide synthetic predictions for all locations

**Prediction Engine Use:**
- Use forecast as ground truth for that location
- Use synthetic predictions for planning
- Monitor actual arrivals to validate forecasts

### Scenario 2: Real Movement Validation
**Input:** TD event shows actual arrival at CRFDSPR (7 min late)
**System Response:**
- Store actual arrival time
- Calculate real delay (7 minutes)
- Re-propagate delay downstream
- Update position tracking

**Prediction Engine Use:**
- Validate previous forecasts against reality
- Update confidence in prediction models
- Use real delay for more accurate downstream predictions

### Scenario 3: Mixed Forecast + Reality
**Timeline:**
1. 15:25 - Forecast received: "Will arrive CRFDSPR at 15:32"
2. 15:32 - TD event: "Actually arrived CRFDSPR at 15:33"
3. System updates with 8-min actual delay, re-propagates

**Prediction Engine Benefits:**
- Can measure forecast accuracy
- Adjust model confidence based on reality
- Provide corrected predictions downstream

## Key Data Points for Prediction Engines

### Real-Time State Indicators
- `detected`: Is train actively tracked?
- `last_step_time`: When did we last see this train?
- `berth`: Exact track circuit location
- `terminated`: Has journey completed?

### Timing Data Layers
- `*_time`: Scheduled baseline times
- `actual_*`: Confirmed real times 
- `forecast_*`: External predictions
- `pred_*`: Our calculated predictions
- `delay_minutes`: Current delay at each location

### Prediction Confidence Indicators
- Locations with `actual_*` times = high confidence
- Locations with `forecast_*` times = medium confidence  
- Locations with only `pred_*` times = model-dependent confidence
- `forecast_delay_at`: Freshness of forecast data

### Recovery Mechanisms
- `late_dwell_secs`: Minimum dwell when late
- `recovery_secs`: Sectional slack available
- Dwell trimming calculations show recovery potential

## External Prediction Engine Integration

Prediction engines can leverage this system by:

1. **Consuming Clean State**: All trains have consistent data structure
2. **Validating Models**: Compare predictions against actual outcomes
3. **Incorporating Context**: Use train characteristics and route data
4. **Providing Forecasts**: Submit predictions back to the system
5. **Monitoring Performance**: Track prediction accuracy over time

The system maintains a complete audit trail of scheduled → forecast → actual times, enabling sophisticated analysis of prediction accuracy and model improvement.