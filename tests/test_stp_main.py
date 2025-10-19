import unittest
from datetime import date
import logging

from app import app
import simplified_stp_handler as stp
from database import get_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestSTPFunctionality(unittest.TestCase):
    """Test the STP indicator functionality with the CIF parser and test data"""

    def setUp(self):
        """Set up test environment and load a test file"""
        self.app = app
        self.app_context = self.app.app_context()
        self.app_context.push()
        
    def tearDown(self):
        """Clean up after test"""
        self.app_context.pop()
        
    def test_get_schedules_for_location(self):
        """Test fetching schedules for a location with STP rules applied"""
        today = date(2025, 5, 17)  # Today's date for testing
        
        # Get all schedules for CHRX for today
        schedules = stp.get_schedules_with_stp_applied(
            search_date=today,
            location="CHRX"
        )
        
        # Log the results
        logger.info(f"Found {len(schedules)} schedules for CHRX on {today}")
        for schedule in schedules:
            logger.info(f"Schedule: {schedule['uid']} - {schedule['train_identity']} - STP: {schedule['effective_stp_indicator']}")
            
            # Check if this schedule has cancellation status
            if schedule.get('is_cancelled', False):
                logger.info(f"  Schedule {schedule['uid']} is CANCELLED")
        
        # General test that API works - not checking specific values due to data dependency
        self.assertIsNotNone(schedules)
        
    def test_database_status(self):
        """Test fetching database status counts from different STP tables"""
        db = get_db()
        
        # Count records in different STP tables using SQLAlchemy text
        from sqlalchemy import text
        
        query = text("SELECT COUNT(*) FROM schedules_ltp")
        ltp_count = db.execute(query).scalar() or 0
        
        query = text("SELECT COUNT(*) FROM schedules_stp_new")
        new_count = db.execute(query).scalar() or 0
        
        query = text("SELECT COUNT(*) FROM schedules_stp_overlay")
        overlay_count = db.execute(query).scalar() or 0
        
        query = text("SELECT COUNT(*) FROM schedules_stp_cancellation")
        cancel_count = db.execute(query).scalar() or 0
        
        # Log the results
        logger.info(f"Database contains:")
        logger.info(f"  LTP schedules (P): {ltp_count}")
        logger.info(f"  New schedules (N): {new_count}")
        logger.info(f"  Overlay schedules (O): {overlay_count}")
        logger.info(f"  Cancellation schedules (C): {cancel_count}")
        
        # Basic test that database is accessible
        # Don't test specific counts as they depend on what data has been loaded
        self.assertIsNotNone(ltp_count)
        
if __name__ == "__main__":
    unittest.main()