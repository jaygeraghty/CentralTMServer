import os
import unittest
import tempfile
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app import app
from models import (
    Base, ParsedFile, BasicSchedule, ScheduleLocation, Association,
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation,
    AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation
)
from cif_parser import CIFParser
import database

class TestCIFParser(unittest.TestCase):
    """Tests for the CIF Parser functionality"""
    
    @classmethod
    def setUpClass(cls):
        """Set up an in-memory SQLite database for testing"""
        cls.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        
    def setUp(self):
        """Create a new session for each test"""
        self.session = self.SessionLocal()
        
        # Patch the database.get_db function to use our test session
        self.db_patcher = patch('database.get_db', return_value=self.session)
        self.mock_db = self.db_patcher.start()
        
        # Set up Flask app context for the test
        self.app_context = app.app_context()
        self.app_context.push()
        
        # Create the parser after patching the database
        self.parser = CIFParser()
        
        self.addCleanup(self.db_patcher.stop)
        self.addCleanup(self.app_context.pop)
    
    def tearDown(self):
        """Clear tables after each test"""
        self.session.rollback()
        self.session.close()
        
    def _clear_all_schedules(self):
        """Clear all schedule-related tables for clean state"""
        self.session.query(ScheduleLocationLTP).delete()
        self.session.query(ScheduleLocationSTPNew).delete()
        self.session.query(ScheduleLocationSTPOverlay).delete()
        self.session.query(ScheduleLocationSTPCancellation).delete()
        self.session.query(ScheduleLTP).delete()
        self.session.query(ScheduleSTPNew).delete()
        self.session.query(ScheduleSTPOverlay).delete()
        self.session.query(ScheduleSTPCancellation).delete()
        self.session.query(ScheduleLocation).delete()
        self.session.query(BasicSchedule).delete()
        self.session.commit()
    
    def create_test_cif_file(self, content):
        """Create a temporary CIF file with the given content"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.CIF')
        temp_file.write(content.encode('utf-8'))
        temp_file.close()
        return temp_file.name
    
    def test_parse_cif_date(self):
        """Test that CIF dates are correctly parsed"""
        parser = CIFParser()
        
        # Test valid dates
        self.assertEqual(parser.parse_cif_date("210101"), date(2021, 1, 1))
        self.assertEqual(parser.parse_cif_date("251231"), date(2025, 12, 31))
        
        # Test edge cases
        self.assertEqual(parser.parse_cif_date("200229"), date(2020, 2, 29))  # Leap year
        
        # Test invalid dates
        self.assertIsNone(parser.parse_cif_date(""))  # Empty string
        self.assertIsNone(parser.parse_cif_date("abcdef"))  # Non-numeric
        self.assertIsNone(parser.parse_cif_date("999999"))  # Invalid date
        self.assertIsNone(parser.parse_cif_date("210230"))  # February 30 doesn't exist
        
    def test_stp_indicator_precedence(self):
        """Test STP indicator precedence with overlapping schedules
        
        This test creates:
        1. A permanent schedule (LTP) for Jan-May
        2. A cancellation for April
        3. A new STP schedule for April to 'replace' the cancelled one
        4. An overlay to change a platform code for March
        
        Then it verifies the correct schedules are retrieved based on STP precedence rules.
        """
        self._clear_all_schedules()
        
        # Common data for all schedules
        uid = "A12345"
        train_identity = "1A01"
        days_run = "1111100"  # Mon-Fri
        
        # Create a permanent schedule for Jan-May
        perm_schedule = ScheduleLTP()
        perm_schedule.uid = uid
        perm_schedule.train_identity = train_identity
        perm_schedule.train_category = "OO"
        perm_schedule.stp_indicator = "P"
        perm_schedule.transaction_type = "N"
        perm_schedule.runs_from = date(2025, 1, 1)
        perm_schedule.runs_to = date(2025, 5, 31)
        perm_schedule.days_run = days_run
        perm_schedule.train_status = "P"
        perm_schedule.service_code = "12345"
        perm_schedule.power_type = "EMU"
        perm_schedule.speed = 100
        self.session.add(perm_schedule)
        self.session.flush()  # Get the ID
        
        # Add locations to permanent schedule
        locations = [
            {"sequence": 1, "location_type": "LO", "tiploc": "CHRX", "dep": "0900", "platform": "1"},
            {"sequence": 2, "location_type": "LI", "tiploc": "KNGX", "arr": "0915", "dep": "0917", "platform": "5"},
            {"sequence": 3, "location_type": "LT", "tiploc": "EUSTON", "arr": "0930", "platform": "8"}
        ]
        
        for loc_data in locations:
            loc = ScheduleLocationLTP()
            loc.schedule_id = perm_schedule.id
            for key, value in loc_data.items():
                setattr(loc, key, value)
            self.session.add(loc)
        
        # Create a cancellation for April
        cancel_schedule = ScheduleSTPCancellation()
        cancel_schedule.uid = uid
        cancel_schedule.train_identity = train_identity
        cancel_schedule.train_category = "OO"
        cancel_schedule.stp_indicator = "C"
        cancel_schedule.transaction_type = "N"
        cancel_schedule.runs_from = date(2025, 4, 1)
        cancel_schedule.runs_to = date(2025, 4, 30)
        cancel_schedule.days_run = days_run
        cancel_schedule.train_status = "P"
        cancel_schedule.service_code = "12345"
        cancel_schedule.power_type = "EMU"
        cancel_schedule.speed = 100
        self.session.add(cancel_schedule)
        self.session.flush()  # Get the ID
        
        # Add the same locations to cancellation (for reference)
        for loc_data in locations:
            loc = ScheduleLocationSTPCancellation()
            loc.schedule_id = cancel_schedule.id
            for key, value in loc_data.items():
                setattr(loc, key, value)
            self.session.add(loc)
        
        # Create a new schedule for April (to replace the cancelled one)
        new_schedule = ScheduleSTPNew()
        new_schedule.uid = uid + "NEW"  # Different UID as it's a new schedule
        new_schedule.train_identity = train_identity
        new_schedule.train_category = "OO"
        new_schedule.stp_indicator = "N"
        new_schedule.transaction_type = "N"
        new_schedule.runs_from = date(2025, 4, 1)
        new_schedule.runs_to = date(2025, 4, 30)
        new_schedule.days_run = days_run
        new_schedule.train_status = "P"
        new_schedule.service_code = "12345"
        new_schedule.power_type = "EMU"
        new_schedule.speed = 100
        self.session.add(new_schedule)
        self.session.flush()  # Get the ID
        
        # Add slightly different locations to new schedule (different times)
        new_locations = [
            {"sequence": 1, "location_type": "LO", "tiploc": "CHRX", "dep": "0910", "platform": "2"},
            {"sequence": 2, "location_type": "LI", "tiploc": "KNGX", "arr": "0925", "dep": "0927", "platform": "6"},
            {"sequence": 3, "location_type": "LT", "tiploc": "EUSTON", "arr": "0940", "platform": "9"}
        ]
        
        for loc_data in new_locations:
            loc = ScheduleLocationSTPNew()
            loc.schedule_id = new_schedule.id
            for key, value in loc_data.items():
                setattr(loc, key, value)
            self.session.add(loc)
        
        # Create an overlay for March to change platform at Kings Cross
        overlay_schedule = ScheduleSTPOverlay()
        overlay_schedule.uid = uid
        overlay_schedule.train_identity = train_identity
        overlay_schedule.train_category = "OO"
        overlay_schedule.stp_indicator = "O"
        overlay_schedule.transaction_type = "N"
        overlay_schedule.runs_from = date(2025, 3, 1)
        overlay_schedule.runs_to = date(2025, 3, 31)
        overlay_schedule.days_run = days_run
        overlay_schedule.train_status = "P"
        overlay_schedule.service_code = "12345"
        overlay_schedule.power_type = "EMU"
        overlay_schedule.speed = 100
        self.session.add(overlay_schedule)
        self.session.flush()  # Get the ID
        
        # Add modified locations to overlay (different platform at Kings Cross)
        overlay_locations = [
            {"sequence": 1, "location_type": "LO", "tiploc": "CHRX", "dep": "0900", "platform": "1"},
            {"sequence": 2, "location_type": "LI", "tiploc": "KNGX", "arr": "0915", "dep": "0917", "platform": "10"},
            {"sequence": 3, "location_type": "LT", "tiploc": "EUSTON", "arr": "0930", "platform": "8"}
        ]
        
        for loc_data in overlay_locations:
            loc = ScheduleLocationSTPOverlay()
            loc.schedule_id = overlay_schedule.id
            for key, value in loc_data.items():
                setattr(loc, key, value)
            self.session.add(loc)
        
        self.session.commit()
        
        from sqlalchemy import text
        
        # Test 1: February - should return permanent schedule
        test_date = date(2025, 2, 15)
        result = self.session.execute(
            text("""
            WITH combined_schedules AS (
                -- 1. Cancellations (highest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 1 as priority
                FROM 
                    schedules_stp_cancellation
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 2. Overlays
                SELECT 
                    id, uid, train_identity, stp_indicator, 2 as priority
                FROM 
                    schedules_stp_overlay
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 3. New schedules
                SELECT 
                    id, uid, train_identity, stp_indicator, 3 as priority
                FROM 
                    schedules_stp_new
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 4. Permanent/LTP schedules (lowest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 4 as priority
                FROM 
                    schedules_ltp
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
            )
            -- Select the highest precedence record for each UID
            SELECT 
                cs.*
            FROM 
                combined_schedules cs
            JOIN (
                SELECT 
                    uid,
                    MIN(priority) as min_priority
                FROM 
                    combined_schedules
                GROUP BY 
                    uid
            ) as priority_selection
            ON 
                cs.uid = priority_selection.uid AND 
                cs.priority = priority_selection.min_priority
            """),
            {"uid": uid, "date": test_date}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for February")
        self.assertEqual(result[0].stp_indicator, "P", "February should return permanent schedule")
        
        # Test 2: March - should return overlay schedule
        test_date = date(2025, 3, 15)
        result = self.session.execute(
            text("""
            WITH combined_schedules AS (
                -- 1. Cancellations (highest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 1 as priority
                FROM 
                    schedules_stp_cancellation
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 2. Overlays
                SELECT 
                    id, uid, train_identity, stp_indicator, 2 as priority
                FROM 
                    schedules_stp_overlay
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 3. New schedules
                SELECT 
                    id, uid, train_identity, stp_indicator, 3 as priority
                FROM 
                    schedules_stp_new
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 4. Permanent/LTP schedules (lowest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 4 as priority
                FROM 
                    schedules_ltp
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
            )
            -- Select the highest precedence record for each UID
            SELECT 
                cs.*
            FROM 
                combined_schedules cs
            JOIN (
                SELECT 
                    uid,
                    MIN(priority) as min_priority
                FROM 
                    combined_schedules
                GROUP BY 
                    uid
            ) as priority_selection
            ON 
                cs.uid = priority_selection.uid AND 
                cs.priority = priority_selection.min_priority
            """),
            {"uid": uid, "date": test_date}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for March")
        self.assertEqual(result[0].stp_indicator, "O", "March should return overlay schedule")
        
        # Check the platform at Kings Cross in March
        kx_location = self.session.execute(
            text("""
            SELECT platform FROM schedule_locations_stp_overlay
            WHERE schedule_id = :schedule_id AND tiploc = 'KNGX'
            """),
            {"schedule_id": result[0].id}
        ).fetchone()
        
        self.assertEqual(kx_location.platform, "10", "Kings Cross platform should be 10 in March")
        
        # Test 3: April - should return cancellation (and no services for this train)
        test_date = date(2025, 4, 15)
        result = self.session.execute(
            text("""
            WITH combined_schedules AS (
                -- 1. Cancellations (highest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 1 as priority
                FROM 
                    schedules_stp_cancellation
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 2. Overlays
                SELECT 
                    id, uid, train_identity, stp_indicator, 2 as priority
                FROM 
                    schedules_stp_overlay
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 3. New schedules
                SELECT 
                    id, uid, train_identity, stp_indicator, 3 as priority
                FROM 
                    schedules_stp_new
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 4. Permanent/LTP schedules (lowest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 4 as priority
                FROM 
                    schedules_ltp
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
            )
            -- Select the highest precedence record for each UID
            SELECT 
                cs.*
            FROM 
                combined_schedules cs
            JOIN (
                SELECT 
                    uid,
                    MIN(priority) as min_priority
                FROM 
                    combined_schedules
                GROUP BY 
                    uid
            ) as priority_selection
            ON 
                cs.uid = priority_selection.uid AND 
                cs.priority = priority_selection.min_priority
            """),
            {"uid": uid, "date": test_date}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for April")
        self.assertEqual(result[0].stp_indicator, "C", "April should return cancellation")
        
        # Test 4: April - but for the new replacement schedule
        test_date = date(2025, 4, 15)
        result = self.session.execute(
            text("""
            WITH combined_schedules AS (
                -- 1. Cancellations (highest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 1 as priority
                FROM 
                    schedules_stp_cancellation
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 2. Overlays
                SELECT 
                    id, uid, train_identity, stp_indicator, 2 as priority
                FROM 
                    schedules_stp_overlay
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 3. New schedules
                SELECT 
                    id, uid, train_identity, stp_indicator, 3 as priority
                FROM 
                    schedules_stp_new
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 4. Permanent/LTP schedules (lowest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 4 as priority
                FROM 
                    schedules_ltp
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
            )
            -- Select the highest precedence record for each UID
            SELECT 
                cs.*
            FROM 
                combined_schedules cs
            JOIN (
                SELECT 
                    uid,
                    MIN(priority) as min_priority
                FROM 
                    combined_schedules
                GROUP BY 
                    uid
            ) as priority_selection
            ON 
                cs.uid = priority_selection.uid AND 
                cs.priority = priority_selection.min_priority
            """),
            {"uid": uid + "NEW", "date": test_date}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for April replacement")
        self.assertEqual(result[0].stp_indicator, "N", "April replacement should be New STP")
        
        # Test 5: May - should return permanent schedule (after cancellation period)
        test_date = date(2025, 5, 15)
        result = self.session.execute(
            text("""
            WITH combined_schedules AS (
                -- 1. Cancellations (highest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 1 as priority
                FROM 
                    schedules_stp_cancellation
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 2. Overlays
                SELECT 
                    id, uid, train_identity, stp_indicator, 2 as priority
                FROM 
                    schedules_stp_overlay
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 3. New schedules
                SELECT 
                    id, uid, train_identity, stp_indicator, 3 as priority
                FROM 
                    schedules_stp_new
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
                
                UNION ALL
                
                -- 4. Permanent/LTP schedules (lowest precedence)
                SELECT 
                    id, uid, train_identity, stp_indicator, 4 as priority
                FROM 
                    schedules_ltp
                WHERE 
                    uid = :uid
                    AND runs_from <= :date
                    AND runs_to >= :date
                    AND SUBSTRING(days_run, 1, 1) = '1'
            )
            -- Select the highest precedence record for each UID
            SELECT 
                cs.*
            FROM 
                combined_schedules cs
            JOIN (
                SELECT 
                    uid,
                    MIN(priority) as min_priority
                FROM 
                    combined_schedules
                GROUP BY 
                    uid
            ) as priority_selection
            ON 
                cs.uid = priority_selection.uid AND 
                cs.priority = priority_selection.min_priority
            """),
            {"uid": uid, "date": test_date}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for May")
        self.assertEqual(result[0].stp_indicator, "P", "May should return permanent schedule")
        # Test valid date
        self.assertEqual(
            self.parser.parse_cif_date('230501'),
            date(2023, 5, 1)
        )
        
        # Test invalid date
        self.assertIsNone(self.parser.parse_cif_date('invalid'))
    
    def test_parse_basic_schedule(self):
        """Test parsing of BS (Basic Schedule) records"""
        # Create a minimal BS record
        bs_record = (
            "BSNY123451905131912131234567P      O6D125671234        P "
            "070 75MPH                                                  "
        )
        
        # Create temp CIF file with just this record
        file_path = self.create_test_cif_file(bs_record)
        
        try:
            # Process the file
            with patch.object(self.parser, 'is_in_area_of_interest', return_value=True):
                with patch.object(self.parser, 'flush_bs_buffer') as mock_flush:
                    self.parser.load_file_data(file_path)
                    
                    # Check that flush_bs_buffer was called with correct data
                    mock_flush.assert_called_once()
                    buffer = mock_flush.call_args[0][0]
                    self.assertEqual(len(buffer), 1)
                    
                    # Verify the parsed data
                    schedule = buffer[0]
                    self.assertEqual(schedule['uid'], 'NY12345')
                    self.assertEqual(schedule['transaction_type'], 'N')
                    self.assertEqual(schedule['runs_from'], date(2019, 5, 13))
                    self.assertEqual(schedule['runs_to'], date(2019, 12, 13))
                    self.assertEqual(schedule['days_run'], '1234567')
                    self.assertEqual(schedule['train_status'], 'P')
                    self.assertEqual(schedule['train_category'], 'OO')
                    self.assertEqual(schedule['train_identity'], '6D12')
                    self.assertEqual(schedule['headcode'], '6D12')
                    self.assertEqual(schedule['service_code'], '56712')
                    self.assertEqual(schedule['power_type'], '34')
                    self.assertEqual(schedule['speed'], 75)
        finally:
            # Clean up temp file
            os.unlink(file_path)
    
    def test_parse_schedule_locations(self):
        """Test parsing of LO, LI, LT (Location) records"""
        # Create test records for origin, intermediate, terminating locations
        lo_record = "LOTIPLOC1 0915 0920   TB         D               "
        li_record = "LITIPLOC2 0940 0942   TB         D               "
        lt_record = "LTTIPLOC3 1010      TB                           "
        
        # Create a test file with BS record followed by location records
        bs_record = (
            "BSNY123451905131912131234567P      O6D125671234        P "
            "070 75MPH                                                  "
        )
        
        file_content = bs_record + "\n" + lo_record + "\n" + li_record + "\n" + lt_record
        file_path = self.create_test_cif_file(file_content)
        
        try:
            # Process the file
            with patch.object(self.parser, 'is_in_area_of_interest', return_value=True):
                with patch.object(self.parser, 'flush_bs_buffer') as mock_flush_bs:
                    # Mock to return schedule IDs when BS records are flushed
                    mock_flush_bs.return_value = [{'uid': 'NY12345', 'id': 1}]
                    
                    with patch.object(self.parser, 'flush_sl_buffer') as mock_flush_sl:
                        self.parser.load_file_data(file_path)
                        
                        # Check that flush_sl_buffer was called
                        mock_flush_sl.assert_called_once()
                        buffer = mock_flush_sl.call_args[0][0]
                        
                        # Verify we have 3 location records
                        self.assertEqual(len(buffer), 3)
                        
                        # Verify the origin location
                        origin = buffer[0]
                        self.assertEqual(origin['schedule_id'], 1)
                        self.assertEqual(origin['location_type'], 'LO')
                        self.assertEqual(origin['tiploc'], 'TIPLOC1')
                        self.assertEqual(origin['dep'], '0920')
                        self.assertEqual(origin['platform'], 'TB')
                        
                        # Verify the intermediate location
                        intermediate = buffer[1]
                        self.assertEqual(intermediate['schedule_id'], 1)
                        self.assertEqual(intermediate['location_type'], 'LI')
                        self.assertEqual(intermediate['tiploc'], 'TIPLOC2')
                        self.assertEqual(intermediate['arr'], '0940')
                        self.assertEqual(intermediate['dep'], '0942')
                        
                        # Verify the terminating location
                        terminating = buffer[2]
                        self.assertEqual(terminating['schedule_id'], 1)
                        self.assertEqual(terminating['location_type'], 'LT')
                        self.assertEqual(terminating['tiploc'], 'TIPLOC3')
                        self.assertEqual(terminating['arr'], '1010')
        finally:
            # Clean up temp file
            os.unlink(file_path)
    
    def test_parse_associations(self):
        """Test parsing of AA (Association) records"""
        # Create a test AA record
        aa_record = (
            "AAJJ123456NY123452305192512311234567TIPLOC PS290519N"
        )
        
        file_path = self.create_test_cif_file(aa_record)
        
        try:
            # Process the file
            with patch.object(self.parser, 'flush_aa_buffer') as mock_flush:
                self.parser.load_file_data(file_path)
                
                # Check that flush_aa_buffer was called with correct data
                mock_flush.assert_called_once()
                buffer = mock_flush.call_args[0][0]
                
                # Verify we have one association
                self.assertEqual(len(buffer), 1)
                
                # Verify the association details
                association = buffer[0]
                self.assertEqual(association['main_uid'], 'JJ12345')
                self.assertEqual(association['assoc_uid'], 'NY12345')
                self.assertEqual(association['category'], 'JJ')  # Join
                self.assertEqual(association['date_from'], date(2023, 5, 19))
                self.assertEqual(association['date_to'], date(2025, 12, 31))
                self.assertEqual(association['days_run'], '1234567')
                self.assertEqual(association['location'], 'TIPLOC')
                self.assertEqual(association['base_suffix'], 'P')
                self.assertEqual(association['assoc_suffix'], 'S')
                self.assertEqual(association['transaction_type'], 'N')
        finally:
            # Clean up temp file
            os.unlink(file_path)
    
    def test_area_of_interest_filtering(self):
        """Test that only schedules in area of interest are processed"""
        # Create test records
        bs_record = (
            "BSNY123451905131912131234567P      O6D125671234        P "
            "070 75MPH                                                  "
        )
        lo_record = "LOWLOO    0915 0920   TB         D               "  # In area of interest
        lt_record = "LTOTHERST 1010      TB                           "  # Not in area of interest
        
        file_content = bs_record + "\n" + lo_record + "\n" + lt_record
        file_path = self.create_test_cif_file(file_content)
        
        try:
            # Configure area of interest to include only WLOO
            self.parser.area_of_interest = {'WLOO'}
            
            # Process the file
            with patch.object(self.parser, 'flush_bs_buffer') as mock_flush_bs:
                # Mock to return schedule IDs when BS records are flushed
                mock_flush_bs.return_value = [{'uid': 'NY12345', 'id': 1}]
                
                with patch.object(self.parser, 'flush_sl_buffer') as mock_flush_sl:
                    self.parser.load_file_data(file_path)
                    
                    # Check if the schedule passed the area of interest filter
                    self.assertTrue(mock_flush_bs.called)
                    
                    # Change area of interest to exclude WLOO
                    self.parser.area_of_interest = {'ANOTHERSTATION'}
                    
                    # Reset mocks
                    mock_flush_bs.reset_mock()
                    mock_flush_sl.reset_mock()
                    
                    # Process the file again
                    self.parser.load_file_data(file_path)
                    
                    # Check that the schedule was filtered out
                    self.assertFalse(mock_flush_bs.called)
        finally:
            # Clean up temp file
            os.unlink(file_path)

    def test_flush_bs_buffer(self):
        """Test that BasicSchedule records are correctly flushed to database"""
        # Create a test buffer
        buffer = [{
            'uid': 'NY12345',
            'transaction_type': 'N',
            'runs_from': date(2023, 5, 1),
            'runs_to': date(2023, 12, 31),
            'days_run': '1234567',
            'stp_indicator': 'P',
            'train_status': 'P',
            'train_category': 'OO',
            'train_identity': '6D12',
            'headcode': '6D12',
            'service_code': '56712',
            'power_type': '34',
            'speed': 75,
            'operating_chars': 'D',
        }]
        
        # Flush the buffer
        result = self.parser.flush_bs_buffer(buffer)
        
        # Verify that records were inserted
        schedules = self.session.query(BasicSchedule).all()
        self.assertEqual(len(schedules), 1)
        
        # Verify the data
        schedule = schedules[0]
        self.assertEqual(schedule.uid, 'NY12345')
        self.assertEqual(schedule.transaction_type, 'N')
        self.assertEqual(schedule.runs_from, date(2023, 5, 1))
        self.assertEqual(schedule.runs_to, date(2023, 12, 31))
        self.assertEqual(schedule.days_run, '1234567')
        self.assertEqual(schedule.train_status, 'P')
        
        # Verify that IDs were returned
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], schedule.id)
    
    def test_flush_sl_buffer(self):
        """Test that ScheduleLocation records are correctly flushed to database"""
        # Create a test schedule first
        schedule = BasicSchedule(
            uid='NY12345',
            transaction_type='N',
            runs_from=date(2023, 5, 1),
            runs_to=date(2023, 12, 31),
            days_run='1234567',
            stp_indicator='P',
            train_status='P',
            train_category='OO',
            train_identity='6D12',
            service_code='56712',
            power_type='34',
            speed=75
        )
        self.session.add(schedule)
        self.session.commit()
        
        # Create a test buffer for locations
        buffer = [
            {
                'schedule_id': schedule.id,
                'sequence': 1,
                'location_type': 'LO',
                'tiploc': 'TIPLOC1',
                'arr': None,
                'dep': '0920',
                'pass_time': None,
                'public_arr': None,
                'public_dep': None,
                'platform': 'TB',
                'line': None,
                'path': None,
                'activity': None,
                'stp_indicator': 'P'  # Add STP indicator field
            },
            {
                'schedule_id': schedule.id,
                'sequence': 2,
                'location_type': 'LT',
                'tiploc': 'TIPLOC3',
                'arr': '1010',
                'dep': None,
                'pass_time': None,
                'public_arr': None,
                'public_dep': None,
                'platform': 'TC',
                'line': None,
                'path': None,
                'activity': None,
                'stp_indicator': 'P'  # Add STP indicator field
            }
        ]
        
        # Flush the buffer
        self.parser.flush_sl_buffer(buffer)
        
        # Verify that records were inserted
        locations = self.session.query(ScheduleLocation).order_by(ScheduleLocation.sequence).all()
        self.assertEqual(len(locations), 2)
        
        # Verify the origin location
        origin = locations[0]
        self.assertEqual(origin.schedule_id, schedule.id)
        self.assertEqual(origin.location_type, 'LO')
        self.assertEqual(origin.tiploc, 'TIPLOC1')
        self.assertEqual(origin.dep, '0920')
        self.assertEqual(origin.platform, 'TB')
        
        # Verify the terminating location
        terminating = locations[1]
        self.assertEqual(terminating.schedule_id, schedule.id)
        self.assertEqual(terminating.location_type, 'LT')
        self.assertEqual(terminating.tiploc, 'TIPLOC3')
        self.assertEqual(terminating.arr, '1010')
        self.assertEqual(terminating.platform, 'TC')

    def test_flush_aa_buffer(self):
        """Test that Association records are correctly flushed to database"""
        # Create a test buffer
        buffer = [{
            'main_uid': 'JJ12345',
            'assoc_uid': 'NY12345',
            'category': 'JJ',
            'date_from': date(2023, 5, 1),
            'date_to': date(2023, 12, 31),
            'days_run': '1234567',
            'location': 'TIPLOC',
            'base_suffix': 'P',
            'assoc_suffix': 'S',
            'date_indicator': None,
            'stp_indicator': 'P',
            'transaction_type': 'N'
        }]
        
        # Flush the buffer
        self.parser.flush_aa_buffer(buffer)
        
        # Verify that records were inserted
        associations = self.session.query(Association).all()
        self.assertEqual(len(associations), 1)
        
        # Verify the data
        association = associations[0]
        self.assertEqual(association.main_uid, 'JJ12345')
        self.assertEqual(association.assoc_uid, 'NY12345')
        self.assertEqual(association.category, 'JJ')
        self.assertEqual(association.date_from, date(2023, 5, 1))
        self.assertEqual(association.date_to, date(2023, 12, 31))
        self.assertEqual(association.days_run, '1234567')
        self.assertEqual(association.location, 'TIPLOC')

if __name__ == '__main__':
    unittest.main()