# API Documentation

## Overview

This document describes the API endpoints available in our UK railway data system. The API provides access to railway schedule information, focusing on train movements, timetables, and real-time status.

## Base URL

All API endpoints are relative to the base URL of the server, typically:

```
http://localhost:5000/api/
```

## Response Format

Unless otherwise specified, all responses are in JSON format. Success responses use standard HTTP 200 status codes, while error responses use appropriate 4xx or 5xx codes.

## Authentication

Currently, the API does not require authentication for access. This may change in future versions.

## API Endpoints

### Schedules API

#### Get Schedules

```
GET /api/schedules
```

Retrieves schedules for a specific location and date, with options for filtering by platform, line, and path.

**Query Parameters:**
- `location` (required): TIPLOC code of the location
- `date_str` (required): Date in YYYY-MM-DD format
- `platform` (optional): Platform code to filter by
- `line` (optional): Line code to filter by
- `path` (optional): Path code to filter by

**Response:**

```json
{
  "schedules": [
    {
      "uid": "P19424",
      "train_identity": "1V14",
      "runs_from": "2023-02-01",
      "runs_to": "2023-12-31",
      "days_run": "1111111",
      "arrival": null,
      "departure": "07:15",
      "platform": "14",
      "line": "DL",
      "path": "MP",
      "stp_indicator": "P",
      "associations": [
        {
          "assoc_uid": "P12345",
          "category": "JJ",
          "location": "CHRX",
          "stp_indicator": "P"
        }
      ]
    }
  ]
}
```

**Example Request:**

```bash
curl "http://localhost:5000/api/schedules?location=CHRX&date_str=2023-05-01"
```

#### Applying STP Precedence

When retrieving schedules, the API automatically applies STP precedence rules:

1. **C** (Cancellation): Takes highest precedence 
2. **O** (Overlay): Applied if no cancellation exists
3. **N** (New): Applied if no cancellation or overlay exists
4. **P** (Permanent): Base schedule used if no STP variations exist

```python
def get_schedules():
    """
    Get schedules for a specific location and date.
    
    Query Parameters:
        location: TIPLOC code of the location
        date_str: Date in YYYY-MM-DD format
        platform: Optional platform code to filter by
        line: Optional line code to filter by
        path: Optional path code to filter by
        
    Returns:
        JSON response with schedules and associations
    """
    location = request.args.get('location')
    date_str = request.args.get('date_str')
    platform = request.args.get('platform')
    line = request.args.get('line')
    path = request.args.get('path')
    
    if not location or not date_str:
        return jsonify({'error': 'Location and date are required parameters'}), 400
    
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    # Get the day of week (1-7, where 1 is Monday)
    day_of_week = query_date.isoweekday()
    
    # Use a sequential approach to STP precedence - check each schedule type in order
    schedules = simplified_stp_handler.get_schedules_for_location_and_date(
        location, query_date, platform, line, path
    )
    
    # Format the response
    formatted_schedules = []
    for schedule in schedules:
        # Format schedule data...
        formatted_schedules.append(schedule_data)
    
    return jsonify({'schedules': formatted_schedules})
```

### Database Status API

#### Get Database Status

```
GET /api/db_status
```

Retrieves current database status showing counts of different schedule and association types.

**Response:**

```json
{
  "schedules": {
    "ltp": 10243,
    "stp_new": 156,
    "stp_overlay": 822,
    "stp_cancellation": 47,
    "total": 11268
  },
  "associations": {
    "ltp": 1243,
    "stp_new": 23,
    "stp_overlay": 53,
    "stp_cancellation": 12,
    "total": 1331
  }
}
```

**Example Request:**

```bash
curl "http://localhost:5000/api/db_status"
```

### Active Trains API

The Active Trains API provides access to information about trains currently running in the system.

#### Get Active Trains Status

```
GET /api/active/status
```

Returns information about the ActiveTrains system status.

**Response:**

```json
{
  "status": "active",
  "train_count": 458,
  "last_updated": "2023-05-01T09:15:32Z"
}
```

#### Refresh Active Trains

```
POST /api/active/refresh
```

Refreshes the ActiveTrains system with current data.

**Response:**

```json
{
  "status": "success",
  "message": "Active trains refreshed",
  "train_count": 462
}
```

#### Get List of Active Trains

```
GET /api/active/trains
```

Returns a list of all active trains.

**Query Parameters:**
- `limit` (optional): Maximum number of trains to return (default: 100)
- `offset` (optional): Offset for pagination (default: 0)

**Response:**

```json
{
  "trains": [
    {
      "uid": "P19424",
      "headcode": "1V14",
      "origin": "CHRX",
      "destination": "WLOE",
      "current_location": "LONBDGE",
      "delay": 5
    },
    // More trains...
  ],
  "total": 462,
  "limit": 100,
  "offset": 0
}
```

#### Get Train Details

```
GET /api/active/trains/{uid}
```

Returns detailed information about a specific train identified by its UID.

**Response:**

```json
{
  "uid": "P19424",
  "headcode": "1V14",
  "schedule": {
    "origin": "CHRX",
    "destination": "WLOE",
    "departure": "07:15",
    "arrival": "09:45",
    "train_category": "OO",
    "power_type": "EMU"
  },
  "locations": [
    {
      "tiploc": "CHRX",
      "departure": "07:15",
      "platform": "14"
    },
    {
      "tiploc": "LONBDGE",
      "arrival": "07:28",
      "departure": "07:30",
      "platform": "3"
    },
    // More locations...
  ],
  "associations": [
    {
      "main_uid": "P19424",
      "assoc_uid": "P12345",
      "category": "JJ",
      "location": "CHRX"
    }
  ],
  "real_time": {
    "current_location": "LONBDGE",
    "delay": 5,
    "predicted_arrival": "09:50"
  }
}
```

#### Get Trains at Location

```
GET /api/active/location/{tiploc}
```

Returns all trains passing through a specific location.

**Query Parameters:**
- `time_from` (optional): Only include trains arriving/departing after this time (HH:MM format)
- `time_to` (optional): Only include trains arriving/departing before this time (HH:MM format)

**Response:**

```json
{
  "location": "CHRX",
  "trains": [
    {
      "uid": "P19424",
      "headcode": "1V14",
      "origin": "CHRX",
      "destination": "WLOE",
      "departure": "07:15",
      "platform": "14",
      "delay": 0
    },
    // More trains...
  ],
  "count": 36
}
```

### Platform Docker API

The Platform Docker API provides information about train platforms at stations.

#### Get Platform Docker

```
GET /api/platform_docker
```

Returns platform docker information for a specific location and date.

**Query Parameters:**
- `location` (required): TIPLOC code of the location
- `date_str` (required): Date in YYYY-MM-DD format
- `format` (optional): Response format, either "html" or "json" (default: "html")

**Response (JSON format):**

```json
{
  "location": "CHRX",
  "date": "2023-05-01",
  "platforms": [
    {
      "platform": "1",
      "trains": [
        {
          "uid": "P19424",
          "headcode": "1V14",
          "departure": "07:15",
          "destination": "WLOE",
          "length": 75
        },
        // More trains...
      ]
    },
    // More platforms...
  ]
}
```

**Example Request:**

```bash
curl "http://localhost:5000/api/platform_docker?location=CHRX&date_str=2023-05-01&format=json"
```

## STP Indicators API

The STP Indicators API provides specialized access to schedules based on STP indicators.

#### Get Schedule by Date and UID

```
GET /api/stp/schedule
```

Retrieves schedule information for a specific date and UID, applying STP precedence rules.

**Query Parameters:**
- `date_str` (required): Date in YYYY-MM-DD format
- `uid` (required): Schedule UID

**Response:**

```json
{
  "schedule": {
    "uid": "P19424",
    "train_identity": "1V14",
    "stp_indicator": "O",
    "runs_from": "2023-03-01",
    "runs_to": "2023-03-31",
    "days_run": "1111111",
    "locations": [
      {
        "tiploc": "CHRX",
        "departure": "07:20",
        "platform": "14"
      },
      // More locations...
    ]
  },
  "source_table": "schedules_stp_overlay"
}
```

## API Implementation Details

### 1. Active Trains API

The Active Trains API is implemented using a Flask Blueprint:

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
    
    @active_api.route('/refresh', methods=['POST'])
    def refresh_active_trains():
        """Refresh the ActiveTrains system with current data."""
        manager = get_active_trains_manager()
        manager.refresh_data()
        return jsonify({
            'status': 'success',
            'message': 'Active trains refreshed',
            'train_count': len(manager.trains_by_uid)
        })
    
    # ... more endpoints ...
    
    app.register_blueprint(active_api)
```

### 2. Platform Docker API

The Platform Docker API combines schedule data with platform layout information:

```python
def get_platform_docker():
    """
    Get platform docker information for a specific location and date.
    
    Query Parameters:
        location: TIPLOC code of the location
        date_str: Date in YYYY-MM-DD format
        format: Response format, either "html" or "json"
        
    Returns:
        Platform docker information in the requested format
    """
    location = request.args.get('location')
    date_str = request.args.get('date_str')
    response_format = request.args.get('format', 'html')
    
    if not location or not date_str:
        if response_format == 'json':
            return jsonify({'error': 'Location and date are required parameters'}), 400
        else:
            return "Location and date are required parameters", 400
    
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        if response_format == 'json':
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            return "Invalid date format. Use YYYY-MM-DD", 400
    
    # Get schedules for this location and date
    schedules = simplified_stp_handler.get_schedules_for_location_and_date(location, query_date)
    
    # Organize schedules by platform
    platforms = {}
    for schedule in schedules:
        platform = schedule.get('platform', 'Unknown')
        if platform not in platforms:
            platforms[platform] = []
        platforms[platform].append(schedule)
    
    # Sort trains on each platform by departure time
    for platform in platforms:
        platforms[platform].sort(key=lambda x: x.get('departure', '00:00'))
    
    if response_format == 'json':
        # Format response as JSON
        platform_list = []
        for platform_id, trains in platforms.items():
            platform_list.append({
                'platform': platform_id,
                'trains': trains
            })
        
        return jsonify({
            'location': location,
            'date': date_str,
            'platforms': platform_list
        })
    else:
        # Render HTML template
        return render_template(
            'platform_docker.html',
            location=location,
            date=date_str,
            platforms=platforms
        )
```

### 3. STP Indicators API

The STP Indicators API applies precedence rules to retrieve the correct schedule version:

```python
def get_schedule_for_date():
    """
    Get schedule information for a specific date and UID, applying STP precedence rules.
    
    Query Parameters:
        date_str: Date in YYYY-MM-DD format
        uid: Schedule UID
        
    Returns:
        JSON response with schedule information
    """
    date_str = request.args.get('date_str')
    uid = request.args.get('uid')
    
    if not date_str or not uid:
        return jsonify({'error': 'Date and UID are required parameters'}), 400
    
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    # Apply STP precedence rules to find the correct schedule
    result = simplified_stp_handler.get_schedule_for_date_and_uid(date_str, uid)
    
    if not result:
        return jsonify({'error': 'No schedule found for this date and UID'}), 404
    
    schedule = result['schedule']
    source_table = result['source_table']
    
    # Get locations for this schedule
    locations = get_locations_for_schedule(schedule.id, source_table)
    
    # Format response
    schedule_data = {
        'uid': schedule.uid,
        'train_identity': schedule.train_identity,
        'stp_indicator': schedule.stp_indicator,
        'runs_from': schedule.runs_from.strftime('%Y-%m-%d'),
        'runs_to': schedule.runs_to.strftime('%Y-%m-%d'),
        'days_run': schedule.days_run,
        'locations': locations
    }
    
    return jsonify({
        'schedule': schedule_data,
        'source_table': source_table
    })
```

## Error Handling

All API endpoints include error handling for common cases:

1. Missing required parameters
2. Invalid date formats
3. No data found
4. Database errors

Example error response:

```json
{
  "error": "Invalid date format. Use YYYY-MM-DD"
}
```

## Cross-Origin Resource Sharing (CORS)

The API supports CORS to allow access from web applications on different domains:

```python
@app.after_request
def add_cors_headers(response):
    """Add CORS headers to allow cross-origin requests."""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE')
    return response
```

## Rate Limiting

Currently, the API does not implement rate limiting, but this may be added in future versions.

## API Versioning

The current API does not include versioning in the URL structure. Future versions may introduce versioned endpoints (e.g., `/api/v1/schedules`).

## API Extension Points

The API is designed to be extensible. New functionality can be added through additional blueprints or endpoints without disrupting existing clients.