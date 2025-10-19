import unittest
import os
import sys
import shutil
from datetime import date
import logging
from sqlalchemy import text

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
import simplified_stp_handler as stp
from cif_parser import CIFParser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestSTPPrecedence(unittest.TestCase):
    """Test STP precedence rules with the test_good.CIF data"""

    def setUp(self):
        """Set up test environment"""
        self.app = app
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Prepare and process test file
        self._reset_database()
        self._process_test_file()
        
    def tearDown(self):
        """Clean up after test"""
        self.app_context.pop()
        
    def _reset_database(self):
        """Reset the database tables"""
        tables = [
            "parsed_files",
            "schedule_locations_ltp",
            "schedule_locations_stp_new",
            "schedule_locations_stp_overlay",
            "schedule_locations_stp_cancellation",
            "schedules_ltp",
            "schedules_stp_new",
            "schedules_stp_overlay",
            "schedules_stp_cancellation",
            "associations_ltp",
            "associations_stp_new",
            "associations_stp_overlay",
            "associations_stp_cancellation"
        ]
        
        for table in tables:
            db.session.execute(text(f"DELETE FROM {table}"))
            
        db.session.commit()
        logger.info("Database reset for testing")
        
    def _process_test_file(self):
        """Process test_good.CIF file from test_data folder"""
        # Use absolute paths relative to project root
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Ensure test_data directory exists
        test_data_dir = os.path.join(base_dir, 'test_data')
        if not os.path.exists(test_data_dir):
            os.makedirs(test_data_dir)
            
        # Ensure import directory exists
        import_dir = os.path.join(base_dir, 'import')
        if not os.path.exists(import_dir):
            os.makedirs(import_dir)
            
        # Check if archive directory exists, if not create it
        archive_dir = os.path.join(base_dir, 'archive')
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
            
        # Check if we have test_good.CIF in archive
        archive_file = os.path.join(base_dir, 'archive/test_good.CIF')
        import_file = os.path.join(base_dir, 'import/test_good_temp.CIF')
        
        # Copy file from archive to import with a different name to avoid "already processed" check
        if os.path.exists(archive_file):
            shutil.copy(archive_file, import_file)
            logger.info(f"Copied {archive_file} to {import_file}")
            
            # Process the file
            parser = CIFParser()
            parser.process_file(import_file)
            logger.info("Test file processed")
            
            # Clean up
            if os.path.exists(import_file):
                os.remove(import_file)
                
        else:
            logger.error(f"Test file {archive_file} not found!")
            self.fail(f"Test file {archive_file} not found!")
        
    def test_get_db_status(self):
        """Test database status showing STP table counts"""
        from app import db
        
        # Count records in different STP tables
        ltp_count = db.session.execute(text("SELECT COUNT(*) FROM schedules_ltp")).scalar() or 0
        stp_new_count = db.session.execute(text("SELECT COUNT(*) FROM schedules_stp_new")).scalar() or 0
        stp_overlay_count = db.session.execute(text("SELECT COUNT(*) FROM schedules_stp_overlay")).scalar() or 0
        stp_cancel_count = db.session.execute(text("SELECT COUNT(*) FROM schedules_stp_cancellation")).scalar() or 0
        
        # Log the counts
        logger.info("STP Table Counts:")
        logger.info(f"  LTP Schedules (P): {ltp_count}")
        logger.info(f"  STP New Schedules (N): {stp_new_count}")
        logger.info(f"  STP Overlay Schedules (O): {stp_overlay_count}")
        logger.info(f"  STP Cancellation Schedules (C): {stp_cancel_count}")
        
        # Basic test for records in the tables
        self.assertTrue(ltp_count >= 2, "Should have at least 2 permanent schedules")
        self.assertTrue(stp_new_count >= 1, "Should have at least 1 STP New schedule")
        self.assertTrue(stp_overlay_count >= 1, "Should have at least 1 STP Overlay schedule")
        self.assertTrue(stp_cancel_count >= 1, "Should have at least 1 STP Cancellation schedule")
    
    def test_cancellation_precedence(self):
        """Test that cancellations (C) take highest precedence"""
        from app import db
        
        # Find a schedule with cancellation
        cancel_record = db.session.execute(text("""
            SELECT uid, train_identity, runs_from, runs_to FROM schedules_stp_cancellation 
            LIMIT 1
        """)).fetchone()
        
        if not cancel_record:
            self.fail("No cancellation record found for testing")
            return
            
        uid, train_id, cancel_from, cancel_to = cancel_record
        logger.info(f"Testing cancellation precedence for {uid} ({train_id}) on {cancel_from}")
        
        # Get the complete schedule info using the STP handler (which applies precedence)
        schedules_with_precedence = stp.get_schedules_with_stp_applied(
            search_date=cancel_from,
            location="CHRX"  # Known to be in test data
        )
        
        # Find the specific schedule we're testing
        test_schedule = next((s for s in schedules_with_precedence if s['uid'] == uid), None)
        
        # Verify the cancellation was applied correctly
        self.assertIsNotNone(test_schedule, f"Schedule {uid} should be in the results")
        if test_schedule:
            # Log the schedule details
            logger.info(f"Schedule {uid} on {cancel_from}:")
            logger.info(f"  STP Indicator: {test_schedule.get('effective_stp_indicator', 'Unknown')}")
            logger.info(f"  Is Cancelled: {test_schedule.get('is_cancelled', False)}")
            
            # Check that cancellation takes precedence
            self.assertEqual(
                test_schedule.get('effective_stp_indicator'),
                'C',
                f"Schedule {uid} should have effective STP indicator 'C' on {cancel_from}"
            )
            self.assertTrue(
                test_schedule.get('is_cancelled', False),
                f"Schedule {uid} should be marked as cancelled on {cancel_from}"
            )
    
    def test_overlay_precedence(self):
        """Test that overlays (O) take precedence over base schedules"""
        from app import db
        
        # Find a schedule with overlay
        overlay_record = db.session.execute(text("""
            SELECT uid, train_identity, runs_from, runs_to FROM schedules_stp_overlay 
            LIMIT 1
        """)).fetchone()
        
        if not overlay_record:
            self.fail("No overlay record found for testing")
            return
            
        uid, train_id, overlay_from, overlay_to = overlay_record
        logger.info(f"Testing overlay precedence for {uid} ({train_id}) on {overlay_from}")
        
        # Get the complete schedule info using the STP handler
        schedules_with_precedence = stp.get_schedules_with_stp_applied(
            search_date=overlay_from,
            location="CHRX"  # Known to be in test data
        )
        
        # Find the specific schedule we're testing
        test_schedule = next((s for s in schedules_with_precedence if s['uid'] == uid), None)
        
        # Verify the overlay was applied correctly
        self.assertIsNotNone(test_schedule, f"Schedule {uid} should be in the results")
        if test_schedule:
            # Log the schedule details
            logger.info(f"Schedule {uid} on {overlay_from}:")
            logger.info(f"  STP Indicator: {test_schedule.get('effective_stp_indicator', 'Unknown')}")
            logger.info(f"  Is Overlay: {test_schedule.get('is_overlay', False)}")
            
            # Check that overlay takes precedence
            self.assertEqual(
                test_schedule.get('effective_stp_indicator'),
                'O',
                f"Schedule {uid} should have effective STP indicator 'O' on {overlay_from}"
            )
            
            # Check for specific overlay changes (platform at HAYS should be 9)
            locations = test_schedule.get('locations', [])
            hays_loc = next((loc for loc in locations if loc['tiploc'] == 'HAYS'), None)
            
            if hays_loc:
                logger.info(f"  HAYS location in overlay: Platform {hays_loc.get('platform')}")
                self.assertEqual(
                    hays_loc.get('platform'),
                    '9',
                    "Platform at HAYS should be 9 in the overlay"
                )

if __name__ == "__main__":
    unittest.main()