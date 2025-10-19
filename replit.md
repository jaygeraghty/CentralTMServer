# UK Railway Data Visualization and Tracking System

## Overview
This project is a comprehensive Python-based railway data visualization and tracking system. Its primary purpose is to process UK Computerized Interchange Format (CIF) data, providing advanced real-time analytics and interactive visualization capabilities. The system aims to offer dynamic railway schedule retrieval, ultra-wide timeline and detailed train tracking, and robust handling of UK railway day operations with timezone awareness. Key capabilities include a powerful CIF data parser, a delay propagation algorithm with minute-level prediction updates, and an active trains system for in-memory management of railway operations. The project's ambition is to deliver an accurate and resilient platform for monitoring and understanding UK railway movements.

## User Preferences
- **Debugging Approach**: Avoid restarting application during debugging
- **Solution Style**: Keep solutions simple and focused, avoid overcomplication
- **Data Integrity**: Use authentic CIF data, no mock or placeholder data
- **Error Handling**: Comprehensive logging without affecting production database

## System Architecture

### UI/UX Decisions
- **D3.js Visualization**: Utilizes D3.js for advanced interactive visualizations, including an ultra-wide timeline and detailed train tracking.
- **Web Interface**: Provides professional, dark-themed web interfaces for logs and train schedules, featuring filtering, search, auto-refresh, and color-coded displays.
- **Train Schedule Viewer**: Comprehensive HTML interface displaying full train schedules, associations, activities, and engineering allowances with responsive table design and color-coded time displays.
- **Current Location Tracking**: Visual highlighting and arrow indicators in the schedule viewer for current train position, with CSS classes for "at station," "between stations," and "journey complete" states.
- **Smart Prediction Display**: Integration of smart prediction data with vibrant orange AI columns and purple confidence displays in the train schedule viewer.

### Technical Implementations
- **Backend**: Built with FastAPI/Flask for dynamic railway schedule retrieval and API endpoint management.
- **CIF Data Parser**: Robust parser with enhanced error handling, schedule extraction, and allowance support. It extracts allowances from specific positions within the CIF format.
- **Active Trains System**: In-memory management of active trains, handling UK railway day operations (02:00 rollover) and applying STP precedence rules (C > O > N > P).
- **Delay Propagation Algorithm**: Implemented with seconds-based precision, handling both delays and early running (earliness propagates, but departures/passes are forced to scheduled times).
- **Timezone Management**: Comprehensive handling of BST/GMT for accurate UK railway operations, with `pytz` for London timezone.
- **API Logging**: Integrated `log_manager.py` with automatic file rotation and BST-aware timestamps for all API logs.
- **Smart Prediction System**: External API integration for AI prediction cycles, including smart prediction fields (`smart_pred_arr/dep/pass`, `smart_pred_confidence`, `smart_pred_timestamp`).
- **Bidirectional Associations**: Implementation of bidirectional associations (e.g., NP creating PR) at the location level within `ActiveScheduleLocation` objects.
- **Railway Day Rollover**: Automated rollover system at 02:00 London time, promoting tomorrow's trains to today's, with fallback mechanisms and robust logging.
- **Scheduler**: APScheduler with CronTrigger for precise timing of background tasks like railway day rollover.
- **TD System Integration**: Records actual TD system timestamps (`current_berth_entry_time`) and `previous_berth` for movement tracking and step event handling.

### Feature Specifications
- **Real-time Updates**: Supports forecast updates and movement tracking with `Authorization: Bearer` for external API authentication.
- **API Routes**: Comprehensive API endpoints for schedules, active trains, real-time updates, system management, and specific train filtering (by headcode, UID).
- **Train Schedule Page Refresh**: "Refresh Train Data" button and auto-refresh functionality (30-second intervals) with toggle and status indicators.
- **Status Fields**: `detected`, `terminated`, `cancelled` fields integrated into external API response to reflect train state.

### System Design Choices
- **Singleton Pattern**: `ActiveTrainsManager` uses a singleton pattern to manage train collections.
- **Database Schema**: Designed for CIF data, including separate tables for STP types (P, N, O, C schedules) and location-based association cross-references.
- **Data Structures**: Utilizes proper dictionary copying for railway day rollover to prevent shallow reference issues.

## External Dependencies
- **FastAPI/Flask**: Backend framework for API development.
- **D3.js**: Frontend library for advanced data visualization.
- **APScheduler**: Python library for scheduling periodic tasks, used for the railway day rollover.
- **pytz**: Python library for timezone calculations, specifically for London time (BST/GMT).