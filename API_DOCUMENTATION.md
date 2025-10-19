
# UK Railway Timetable API Server - Complete Documentation

## Overview
A pure data API server providing UK railway schedule and train tracking information. This server processes CIF (Common Interface File) data and provides real-time train information through RESTful endpoints.

**Base URL:** `http://localhost:5000`  
**Version:** 2.0.0  
**Service Type:** Pure API Server (No Web Interface)

## Core Endpoints

### 1. System Information

#### GET `/`
Returns complete API documentation and endpoint listing.
```json
{
  "service": "UK Railway Timetable API Server",
  "version": "2.0.0",
  "description": "Pure data API for railway schedule and train tracking information",
  "endpoints": [...],
  "parameter_guide": {...}
}
```

#### GET `/health`
Server health check endpoint.
```json
{
  "status": "ok",
  "timestamp": "2025-05-30 14:29:45.138097"
}
```

### 2. Timetable Data Endpoints

#### GET `/api/schedules`
Get train schedules for a specific location and date.

**Parameters:**
- `location` (required) - 4-letter TIPLOC code (e.g., CHRX, WLOE)
- `date_str` (required) - Date in YYYY-MM-DD format
- `platform` (optional) - Platform number/identifier
- `line` (optional) - Line code
- `path` (optional) - Path code

**Example:**
```
GET /api/schedules?location=CHRX&date_str=2025-05-30&platform=1
```

#### POST `/api/platform_docker`
Get platform visualization data with train events timeline.

**Request Body:**
```json
{
  "location": "CHRX",
  "date": "2025-05-30",
  "page": 1,
  "per_page": 10
}
```

**Returns:** Platform layout with train arrival/departure times formatted for timeline visualization.

#### POST `/api/train_graph_schedules`
Get schedules for multiple locations (train graph functionality).

**Request Body:**
```json
{
  "locations": ["CHRX", "WLOE"],
  "date": "2025-05-30"
}
```

**Returns:** Combined schedule data for all specified locations, suitable for train graph visualization.

#### GET `/api/db_status`
Database status with schedule and association counts.

**Returns:** Statistics about loaded timetable data including counts by STP indicator.

### 3. Active Trains System

#### GET `/api/active_trains`
Get all active trains with complete schedule and real-time information.

**Parameters:**
- `limit` (optional) - Maximum records to return (default: no limit)
- `offset` (optional) - Records to skip for pagination

**Example:**
```
GET /api/active_trains?limit=50&offset=0
```

**Response Format:**
Returns an array of active train objects with the following structure:

```json
[
  {
    "train_id": "5N98",
    "uid": "P17935",
    "headcode": "5N98",
    "last_step_time": null,
    "schedule_start_date": "2025-05-30",
    "current_berth_id": "TRACK_7935",
    "schedule": {
      "uid": "P17935",
      "headcode": "5N98",
      "service_code": "24657005",
      "start_date": "2025-05-27",
      "end_date": "2025-05-30",
      "days_run": "0111100",
      "train_status": "P",
      "train_category": "EE",
      "locations": {
        "CHRX": {
          "tiploc": "CHRX",
          "platform": "5",
          "path": "",
          "line": "FL",
          "activities": "TB",
          "departure_time": "2025-05-30T10:00:00",
          "public_departure": "2025-05-30T00:00:00"
        },
        "WLOE": {
          "tiploc": "WLOE",
          "platform": "C",
          "path": "",
          "line": "",
          "activities": "",
          "pass_time": "2025-05-30T10:02:30",
          "public_arrival": "2025-05-30T00:00:00",
          "public_departure": "2025-05-30T00:00:00"
        }
      }
    },
    "forecast_locations": []
  }
]
```

**Location Object Fields:**
- `tiploc` - 4-letter location code
- `platform` - Platform number/identifier  
- `path` - Path code
- `line` - Line code
- `activities` - Activity codes (TB=Terminates/Begins, OP=Operational Stop, TF=Terminates From, etc.)
- `arrival_time` - Scheduled arrival time (ISO 8601 format)
- `departure_time` - Scheduled departure time (ISO 8601 format)
- `pass_time` - Scheduled pass time for non-stopping locations (ISO 8601 format)
- `public_arrival` - Public arrival time (passenger-facing)
- `public_departure` - Public departure time (passenger-facing)

**Train Categories:**
- `EE` - Empty Coaching Stock
- `OO` - Ordinary Passenger
- `XX` - Express Passenger
- `SS` - Ship
- `PP` - Parcels

**Activity Codes:**
- `TB` - Train Begins/Terminates
- `OP` - Operational Stop
- `TF` - Train Terminates From
- `T` - Stops to take up and set down passengers
- `U` - Stops to take up passengers only
- `D` - Stops to set down passengers only

#### GET `/api/active_trains/status`
Active trains system status and health.

**Returns:**
```json
{
  "status": "online",
  "timestamp": "2025-05-30T14:40:26.896000",
  "total_trains": 1039,
  "train_ids": ["P17935", "P18001", "..."],
  "api_version": "1.0"
}
```

### 4. External Integration Endpoints

These endpoints support real-time data integration from external systems.

#### POST `/api/forecast_update`
Submit forecast updates from external systems (Darwin format).

**Authentication:** Optional - depends on configuration
**Request Body:** Darwin-format forecast data

**Example Request:**
```json
{
  "uid": "P12345",
  "train_id": "1A23",
  "forecasts": [
    {
      "tiploc": "READING",
      "forecast_arrival": "15:32",
      "forecast_departure": "15:35",
      "delay_minutes": 7
    }
  ]
}
```

**Effect:** Automatically marks the train as detected and triggers delay propagation for downstream locations.

#### POST `/api/realtime_update`
Submit real-time movement updates (TD feed format).

**Authentication:** Required - Bearer token via Authorization header
**Request Body:** TD feed format movement data

**Example Request:**
```json
{
  "headcode": "1A23",
  "event_type": "step",
  "from_berth": "0123",
  "to_berth": "0124",
  "timestamp": "2025-05-31T15:32:15Z"
}
```

**Features:** Includes intelligent train detection and ambiguity resolution for multiple trains with the same headcode.

## Data Format Reference

### Location Codes (TIPLOC)
Common station codes:
- `CHRX` - Charing Cross
- `WLOE` - Waterloo East  
- `CANONST` - Cannon Street
- `LNDNBDE` - London Bridge
- `LEWISHM` - Lewisham

### Date/Time Formats
- **Dates:** ISO format `YYYY-MM-DD` (e.g., `2025-05-30`)
- **Times:** ISO 8601 format `YYYY-MM-DDTHH:MM:SS` (e.g., `2025-05-30T10:00:00`)
- **CIF Times:** May include half-second indicator (e.g., `1812H` = 18:12:30)

### STP Indicators
The system handles multiple schedule types with precedence:
- `C` - Cancellation (highest precedence)
- `O` - Overlay
- `N` - New  
- `P` - Permanent (lowest precedence)

### Days Run Format
7-character string representing days of the week:
- Position 1: Monday (1=runs, 0=doesn't run)
- Position 2: Tuesday
- Position 3: Wednesday
- Position 4: Thursday
- Position 5: Friday
- Position 6: Saturday
- Position 7: Sunday

Example: `0111100` = Tuesday through Friday only

## System Status

### Current Data
- **Active Trains:** 1,039 trains currently tracked
- **Database Status:** Multiple STP tables loaded with schedule data
- **Real-time Processing:** Time parsing system active with CIF format validation
- **Background Processing:** Scheduler running for CIF file updates every hour

### Performance Notes
- Large dataset responses may take several seconds
- Active trains endpoint serves 1000+ records efficiently  
- Platform docker data optimized for visualization
- Train graph supports multiple location queries
- Time parsing handles both standard and half-second CIF formats

## Integration Examples

### Basic Schedule Query
```bash
curl "http://localhost:5000/api/schedules?location=CHRX&date_str=2025-05-30"
```

### Get All Active Trains
```bash
curl "http://localhost:5000/api/active_trains"
```

### Get Active Trains with Pagination
```bash
curl "http://localhost:5000/api/active_trains?limit=10&offset=0"
```

### Platform Timeline Data
```bash
curl -X POST http://localhost:5000/api/platform_docker \
  -H "Content-Type: application/json" \
  -d '{"location": "CHRX", "date": "2025-05-30", "page": 1, "per_page": 5}'
```

### Multi-Location Train Graph
```bash
curl -X POST http://localhost:5000/api/train_graph_schedules \
  -H "Content-Type: application/json" \
  -d '{"locations": ["CHRX", "WLOE"], "date": "2025-05-30"}'
```

### Active Trains Status
```bash
curl "http://localhost:5000/api/active_trains/status"
```

### Submit Real-time Update (requires authentication)
```bash
curl -X POST http://localhost:5000/api/realtime_update \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "headcode": "5N98",
    "tiploc": "CHRX", 
    "event_type": "departure",
    "from_berth": "TRACK_7935",
    "to_berth": "TRACK_8001",
    "actual_step_time": "2025-05-30T10:00:15Z",
    "calculated_event_time": "2025-05-30T10:00:00Z"
  }'
```

## Architecture Notes

This is a **pure API server** with no web interface. It's designed to:
- Provide clean JSON data for external consumption
- Support high-volume queries with proper pagination  
- Handle real-time updates from external systems
- Maintain data integrity with STP precedence rules
- Process large CIF datasets efficiently
- Parse complex time formats including half-second precision

### Active Trains System
The Active Trains system maintains real-time state for over 1,000 trains including:
- Complete schedule information with all stopping points
- Real-time position tracking via berth IDs
- Forecast data integration from external prediction systems
- Association handling for joined/split services
- Comprehensive location data with timing information
- Intelligent train detection and ambiguity resolution
- Automatic delay propagation with synthetic predictions

### Train Detection System
The system includes sophisticated train detection logic to handle real-world scenarios:

**Detection States:**
- `detected = false`: Train exists in timetable but not yet active
- `detected = true`: Train is actively tracked via forecasts or berth movements

**Ambiguity Resolution:**
When multiple trains share the same headcode (common for services 12+ hours apart):
1. **Single Detected Train**: Direct match used
2. **Multiple Detected Trains**: Resolved using berth location
3. **No Detected Trains**: Best candidate chosen by departure time proximity

**Logging Examples:**
```
INFO: Train 1A23 (UID: P12345) marked as detected via forecast update
DEBUG: Real-time update: found single detected train 1A23 (UID: P12345)
WARNING: Real-time update: 2 detected trains found for headcode 1A23
INFO: Real-time update: resolved ambiguity for 1A23 using berth 0123 -> UID P12345
INFO: Train activated: 1A23 (UID: P12345) detected at 0124 - chosen from 2 candidates
```

### External API Integration
The server supports external integration through:
- Pull-based architecture for real-time train data
- Darwin feed compatibility for forecast updates
- TD (Train Describer) feed integration for movement data
- Configurable API authentication
- Robust fallback mechanisms

The server runs on port 5000 and is ready for integration with web frontends, mobile applications, or other railway systems requiring UK timetable data.
