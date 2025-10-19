"""
Configuration settings for the UK Railway Timetable API Server.
All configurable constants and settings are centralized here.
"""

import os

# =============================================================================
# AREA OF INTEREST - Geographic filtering for timetable data
# =============================================================================

# Stations we care about - only schedules touching these locations will be processed
AREA_OF_INTEREST = {'CHRX', 'CANONST'}  # Charing Cross, Cannon Street

# =============================================================================
# API AUTHENTICATION
# =============================================================================

# API key for external real-time update endpoints
API_KEY = "AIL7DYIPyGKQVXNzCdjl5OvciXTdVzGBZ8R5TMUFFkbm8rmG2J7dCrmGNIRPKheWIHkzKA7J966e2VWPNYPX2eOrHPf2JMkj0pLN0p1YnhStKGEHmH1ly1LBu1IKpg8U"

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# Database connection URL - pulled from environment
DATABASE_URL = os.environ.get("DATABASE_URL")

# SQLAlchemy engine options for connection pooling and reliability
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Disable SQLAlchemy modification tracking for performance
SQLALCHEMY_TRACK_MODIFICATIONS = False

# =============================================================================
# FLASK APPLICATION SETTINGS
# =============================================================================

# Secret key for session management - fallback for development
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-for-testing")

# Debug mode setting
DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() in ('true', '1', 'yes')

# Server host and port
HOST = "0.0.0.0"
PORT = 5000

# =============================================================================
# TIMEZONE CONFIGURATION
# =============================================================================

# Primary timezone for the application (UK railway operations)
TIMEZONE = 'Europe/London'

# Set system timezone environment variable
os.environ['TZ'] = TIMEZONE

# =============================================================================
# TRAIN MATCHING AND DETECTION
# =============================================================================

# Time window for matching real-time updates to scheduled trains (in minutes)
TIMETABLE_MATCHING_THRESHOLD_MINS = 6 * 60  # 6 hours

# =============================================================================
# CORS CONFIGURATION
# =============================================================================

# CORS settings for API access
CORS_CONFIG = {
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-API-Key"]
    }
}

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Default logging level
LOG_LEVEL = "INFO"

# =============================================================================
# CIF PROCESSING CONFIGURATION
# =============================================================================

# Directory for importing CIF files
CIF_IMPORT_DIRECTORY = "import"

# Buffer sizes for batch database operations
CIF_SCHEDULE_BUFFER_SIZE = 1000
CIF_LOCATION_BUFFER_SIZE = 5000
CIF_ASSOCIATION_BUFFER_SIZE = 1000

# =============================================================================
# ACTIVE TRAINS SYSTEM
# =============================================================================

# Maximum number of trains to return in paginated responses
MAX_TRAINS_PER_PAGE = 100

# Default page size for train listings
DEFAULT_PAGE_SIZE = 50

# =============================================================================
# API VERSION AND METADATA
# =============================================================================

API_VERSION = "2.0.0"
API_NAME = "UK Railway Timetable API Server"
API_DESCRIPTION = "API for accessing UK railway schedule information from CIF files"

# =============================================================================
# LOCATION DISPLAY NAMES
# =============================================================================

# Human-readable names for TIPLOC codes
LOCATION_NAMES = {
    'CHRX': 'Charing Cross',
    'CANONST': 'Cannon Street',
    'WLOE': 'Waterloo East',
    'LNDNBDE': 'London Bridge'
}

# =============================================================================
# SYSTEM HEALTH AND MONITORING
# =============================================================================

# Health check endpoint paths
HEALTH_ENDPOINTS = ["/health", "/api/trains/status", "/api/db_status"]

# Maximum age for health check data (seconds)
HEALTH_CHECK_MAX_AGE = 60