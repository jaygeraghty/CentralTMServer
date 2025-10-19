# UK Railway Data System Documentation

## Overview

This documentation covers the core components and functionality of our UK railway data system, which processes and analyzes Computerized Interchange Format (CIF) data for railway timetables.

## Key Features

- **CIF Parsing**: Efficiently processes UK railway Common Interface Format (CIF) files
- **STP Indicator Support**: Handles permanent schedules and Short Term Plan variations
- **Real-time Train Tracking**: Maintains in-memory representation of active trains
- **PostgreSQL Database**: Stores and organizes all railway schedule data
- **RESTful API**: Provides access to schedule and real-time train information
- **Platform Visualizations**: Displays train platform assignments

## Documentation Files

The documentation is organized into several sections:

1. [CIF Parser](CIF_Parser.md) - Details on the parser that processes railway schedule data
2. [Database Operations](Database_Operations.md) - Information on the database schema and operations
3. [API Documentation](API_Documentation.md) - Description of the RESTful API endpoints
4. [ActiveTrains System](ActiveTrains_System.md) - Documentation on the real-time train tracking system
5. [STP Indicators](STP_Indicators.md) - Explanation of Schedule Type Permanence indicators and their handling

## System Architecture

The system follows a layered architecture:

1. **Data Ingestion Layer**: CIF parser processes railway data files
2. **Storage Layer**: PostgreSQL database stores processed data with STP-specific tables
3. **Processing Layer**: ActiveTrains system and STP handling logic
4. **API Layer**: RESTful endpoints for data access
5. **Visualization Layer**: Web interfaces for displaying schedules and platform information

## Getting Started

To run the system:

1. Ensure PostgreSQL database is configured (DATABASE_URL environment variable)
2. Start the application using gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```

3. Access the web interface at http://localhost:5000
4. Access API endpoints at http://localhost:5000/api/

## Testing

Run the test suite to verify correct operation:

```bash
./run_tests.py
```

For STP-specific tests:

```bash
./run_stp_tests
```