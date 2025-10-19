import logging
import time

# Import configuration first to set timezone
import config

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

# Configure logging with London timezone
import datetime
import pytz

class LondonFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        london_tz = pytz.timezone(config.TIMEZONE)
        ct = datetime.datetime.fromtimestamp(record.created, tz=london_tz)
        return ct.strftime('%Y-%m-%d %H:%M:%S %Z')

# Set timezone before other operations
time.tzset()

# Set up logging with London timezone
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger()
for handler in logger.handlers:
    handler.setFormatter(LondonFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = config.SQLALCHEMY_ENGINE_OPTIONS
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = config.SQLALCHEMY_TRACK_MODIFICATIONS

# Enable CORS for external API access
CORS(app, resources=config.CORS_CONFIG)

# Set secret key for session management
app.secret_key = config.SECRET_KEY

# Set area of interest (stations we care about)
app.config["AREA_OF_INTEREST"] = config.AREA_OF_INTEREST

# Initialize SQLAlchemy
db = SQLAlchemy(app)