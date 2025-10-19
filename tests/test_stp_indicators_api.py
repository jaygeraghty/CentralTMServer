import unittest
from datetime import date
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models import (
    Base, 
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation
)
from api import api_bp

class TestSTPIndicatorsAPI(unittest.TestCase):
    """Tests for the STP Indicator functionality in API endpoints"""
    
    @classmethod
    def setUpClass(cls):
        """Set up an in-memory SQLite database for testing"""
        cls.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        
    def setUp(self):
        """Create a new session for each test"""
        self.session = self.SessionLocal()
        self._create_test_data()
        
    def tearDown(self):
        """Clear tables after each test"""
        self._clear_all_tables()
        self.session.close()
        
    def _clear_all_tables(self):
        """Clear all schedule-related tables for clean state"""
        self.session.query(ScheduleLocationLTP).delete()
        self.session.query(ScheduleLocationSTPNew).delete()
        self.session.query(ScheduleLocationSTPOverlay).delete()
        self.session.query(ScheduleLocationSTPCancellation).delete()
        self.session.query(ScheduleLTP).delete()
        self.session.query(ScheduleSTPNew).delete()
        self.session.query(ScheduleSTPOverlay).delete()
        self.session.query(ScheduleSTPCancellation).delete()
        self.session.commit()
    
    def _create_test_data(self):
        """Create test data for STP indicator tests"""
        # Common data for all schedules
        uid = "A12345"
        train_identity = "1A01"
        days_run = "1111100"  # Mon-Fri
        
        # 1. Create a permanent schedule for Jan-May
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
        
        # 2. Create a cancellation for April
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
        
        # 3. Create a new schedule for April (to replace the cancelled one)
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
        
        # 4. Create an overlay for March to change platform at Kings Cross
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

    def test_query_february_returns_permanent(self):
        """Test February query returns permanent schedule"""
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
            {"uid": "A12345", "date": date(2025, 2, 15)}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for February")
        self.assertEqual(result[0].stp_indicator, "P", "February should return permanent schedule")

    def test_query_march_returns_overlay(self):
        """Test March query returns overlay schedule"""
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
            {"uid": "A12345", "date": date(2025, 3, 15)}
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

    def test_query_april_returns_cancellation(self):
        """Test April query returns cancellation"""
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
            {"uid": "A12345", "date": date(2025, 4, 15)}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for April")
        self.assertEqual(result[0].stp_indicator, "C", "April should return cancellation")

    def test_query_april_returns_new_replacement(self):
        """Test April query returns new replacement schedule"""
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
            {"uid": "A12345NEW", "date": date(2025, 4, 15)}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for April replacement")
        self.assertEqual(result[0].stp_indicator, "N", "April replacement should be New STP")

    def test_query_may_returns_permanent(self):
        """Test May query returns permanent schedule (after cancellation period)"""
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
            {"uid": "A12345", "date": date(2025, 5, 15)}
        ).fetchall()
        
        self.assertEqual(len(result), 1, "Should find 1 schedule for May")
        self.assertEqual(result[0].stp_indicator, "P", "May should return permanent schedule")


if __name__ == '__main__':
    unittest.main()