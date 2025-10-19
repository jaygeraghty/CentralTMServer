# API Server Separation Plan

## Current Problem
- Mixed responsibilities between web templates and API logic
- `web_blueprint.py` contains substantial database queries that should be pure API endpoints
- No clear separation between data server and presentation layer

## Proposed Architecture

### Timetable/Train Tracking Server (This App)
**Purpose**: Pure data API server - no HTML, CSS, or frontend
**Files**:
- `main_api_server.py` - New main entry point (API only)
- `api_core.py` - Core timetable data endpoints
- `api_active_trains.py` - Active trains management
- `api_active_trains_external.py` - External system integration
- `api.py` - Existing schedule/association endpoints

**Endpoints**:
```
GET  /api/schedules?location=CHRX&date=2025-05-30
POST /api/platform_docker (JSON body)
GET  /api/active_trains
GET  /api/active_trains/status
GET  /api/active_trains (external format)
GET  /health
GET  /api/db_status
```

### Web Server (Future Separate App)
**Purpose**: Frontend presentation and user interface
**Responsibilities**:
- Serve HTML templates, CSS, JavaScript
- Handle user interactions and forms
- Make HTTP requests to timetable server APIs
- Render platform docker visualizations
- Manage train graph interfaces

## Migration Steps

### Step 1: Extract API Logic from Web Blueprint
- Move `platform_docker_data()` logic to `api_core.py` ✓
- Move `train_graph_schedules()` to pure API endpoint
- Extract schedule querying logic from web routes

### Step 2: Create Pure API Server
- `main_api_server.py` replaces `main.py` for API-only mode ✓
- Remove all web template dependencies
- Focus on JSON-only responses

### Step 3: Update Web Templates (Future)
- Modify frontend to call `/api/` endpoints instead of local functions
- Use fetch() calls to get data from API server
- Separate web server will host all HTML/CSS/JS

## Benefits

1. **Clear Separation**: Data server vs presentation server
2. **Scalability**: Can scale API server independently
3. **Maintainability**: Cleaner codebase with single responsibilities
4. **Flexibility**: Frontend can be any technology (React, Vue, etc.)
5. **Testing**: Easier to test pure API endpoints
6. **Deployment**: Independent deployment of data and web servers

## Current Status

- ✅ Created `api_core.py` with extracted platform docker logic
- ✅ Created `main_api_server.py` for pure API server mode
- ✅ External active trains API already implemented
- 🔄 Need to extract remaining web logic to API endpoints
- 🔄 Need to test API server independently

## Next Steps

1. Complete extraction of web blueprint logic to API endpoints
2. Test pure API server functionality
3. Document all API endpoints clearly
4. Plan migration strategy for existing web clients