import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from app import app
from cif_parser import process_cif_files
from active_trains import get_active_trains_manager, get_london_now

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def scan_import_folder_job():
    """Job to scan import folder for new CIF files."""
    logger.info(f"Running scheduled scan of import folder at {get_london_now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    try:
        # Run within Flask application context
        with app.app_context():
            process_cif_files()
    except Exception as e:
        logger.exception(f"Error in scheduled import folder scan: {str(e)}")

def railway_day_rollover_job():
    """Job to handle railway day rollover at 02:00."""
    logger.info(f"Running railway day rollover at {get_london_now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    try:
        # Run within Flask application context
        with app.app_context():
            manager = get_active_trains_manager()
            manager.promote_tomorrow_trains()
    except Exception as e:
        logger.exception(f"Error in railway day rollover: {str(e)}")

def start_scheduler():
    """Start the background scheduler for periodic tasks."""
    london_tz = pytz.timezone('Europe/London')
    scheduler = BackgroundScheduler(timezone=london_tz)
    
    # Add job to scan import folder every 30 minutes
    scheduler.add_job(
        scan_import_folder_job,
        trigger=IntervalTrigger(minutes=30),
        id='scan_import_folder',
        name='Scan import folder for new CIF files',
        replace_existing=True
    )
    
    # Add railway day rollover job at 02:00 every day (London time)
    scheduler.add_job(
        railway_day_rollover_job,
        trigger=CronTrigger(hour=2, minute=0, timezone=london_tz),
        id='railway_day_rollover',
        name='Railway day rollover at 02:00',
        replace_existing=True
    )
    
    # Run once at startup
    scheduler.add_job(
        scan_import_folder_job,
        trigger='date',
        run_date=get_london_now(),
        id='initial_scan',
        name='Initial scan of import folder'
    )
    
    scheduler.start()
    logger.info("Started background scheduler")
    
    return scheduler

if __name__ == "__main__":
    # Test the scheduler
    scheduler = start_scheduler()
    
    try:
        # Keep the script running
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
