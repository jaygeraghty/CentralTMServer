import unittest
from datetime import date
from unittest.mock import patch, MagicMock
from flask import jsonify

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import (
    Base, BasicSchedule, ScheduleLocation, Association,
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation
)
from api import get_platform_docker

class TestPlatformDockerAPI(unittest.TestCase):
    """Tests for the Platform Docker API functionality"""
    
    @classmethod
    def setUpClass(cls):
        """Set up an in-memory SQLite database for testing"""
        cls.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)
    
    def setUp(self):
        """Set up test data before each test"""
        self.session = self.SessionLocal()
        self._create_test_data()
    
    def tearDown(self):
        """Clean up after each test"""
        self.session.rollback()
        self.session.close()
    
    def _create_test_data(self):
        """Create test data for platform docker API tests"""
        # Create test schedules
        schedule1 = BasicSchedule(
            uid='NY12345',
            stp_indicator='P',
            transaction_type='N',
            runs_from=date(2025, 5, 19),
            runs_to=date(2025, 12, 31),
            days_run='1234567',  # All days
            train_status='P',
            train_category='OO',
            train_identity='1A12',
            service_code='56712',
            power_type='EMU',
            speed=100
        )
        
        schedule2 = BasicSchedule(
            uid='NY12346',
            stp_indicator='P',
            transaction_type='N',
            runs_from=date(2025, 5, 19),
            runs_to=date(2025, 12, 31),
            days_run='1234567',  # All days
            train_status='P',
            train_category='XX',
            train_identity='2A12',
            service_code='56713',
            power_type='DMU',
            speed=75
        )
        
        # Add schedules to session
        self.session.add(schedule1)
        self.session.add(schedule2)
        self.session.flush()
        
        # Create locations for first schedule (arriving and departing at CHRX)
        loc1_1 = ScheduleLocation(
            schedule_id=schedule1.id,
            sequence=1,
            location_type='LO',
            tiploc='WATERLOO',
            dep='0900',
            platform='1'
        )
        
        loc1_2 = ScheduleLocation(
            schedule_id=schedule1.id,
            sequence=2,
            location_type='LI',
            tiploc='CHRX',
            arr='0930',
            dep='0935',
            platform='6'
        )
        
        loc1_3 = ScheduleLocation(
            schedule_id=schedule1.id,
            sequence=3,
            location_type='LT',
            tiploc='VICTORIS',
            arr='1000',
            platform='3'
        )
        
        # Create locations for second schedule (terminating at CHRX)
        loc2_1 = ScheduleLocation(
            schedule_id=schedule2.id,
            sequence=1,
            location_type='LO',
            tiploc='VICTORIS',
            dep='1100',
            platform='4'
        )
        
        loc2_2 = ScheduleLocation(
            schedule_id=schedule2.id,
            sequence=2,
            location_type='LT',
            tiploc='CHRX',
            arr='1130',
            platform='6'
        )
        
        # Add locations to session
        self.session.add_all([loc1_1, loc1_2, loc1_3, loc2_1, loc2_2])
        
        # Create association between schedules
        association = Association(
            main_uid='NY12345',
            assoc_uid='NY12346',
            category='JJ',  # Join
            date_from=date(2025, 5, 19),
            date_to=date(2025, 12, 31),
            days_run='1234567',
            location='CHRX',
            stp_indicator='P',
            transaction_type='N'
        )
        
        self.session.add(association)
        self.session.commit()
    
    @patch('database.get_db')
    def test_get_platform_docker_basic(self, mock_get_db):
        """Test the basic platform docker API response structure"""
        # Set up the mock to return our test session
        mock_get_db.return_value = self.session
        
        # Mock app request arguments
        mock_args = {
            'location': 'CHRX',
            'date_str': '2025-05-19',
            'start_time': '0700',
            'end_time': '1900'
        }
        
        # Call the API function
        result = get_platform_docker(mock_args)
        
        # Check the top-level structure
        self.assertTrue('success' in result)
        self.assertTrue(result['success'])
        self.assertTrue('platforms' in result)
        
        # Check that we have the right platform
        platforms = result['platforms']
        self.assertEqual(len(platforms), 1)  # One platform (6)
        self.assertEqual(platforms[0]['name'], '6')
        
        # Check that both trains appear on platform 6
        trains = platforms[0]['events']
        self.assertEqual(len(trains), 2)
        
        # Find trains by UID
        train1 = next(t for t in trains if t['uid'] == 'NY12345')
        train2 = next(t for t in trains if t['uid'] == 'NY12346')
        
        # Check first train details
        self.assertEqual(train1['headcode'], '1A12')
        self.assertEqual(train1['arrival_time'], '0930')
        self.assertEqual(train1['departure_time'], '0935')
        self.assertEqual(train1['category'], 'OO')
        self.assertTrue(train1['has_associations'])
        
        # Check second train details
        self.assertEqual(train2['headcode'], '2A12')
        self.assertEqual(train2['arrival_time'], '1130')
        self.assertFalse('departure_time' in train2)  # Terminating
        self.assertEqual(train2['category'], 'XX')
        self.assertTrue(train2['has_associations'])
    
    @patch('api.db')
    def test_get_platform_docker_time_filtering(self, mock_db):
        """Test platform docker API time filtering"""
        # Set up the mock to return our test session
        mock_db.session = self.session
        
        # Test with narrow time range that excludes the second train
        mock_args = {
            'location': 'CHRX',
            'date_str': '2025-05-19',
            'start_time': '0900',
            'end_time': '1000'  # Excludes the 11:30 arrival
        }
        
        # Call the API function
        result = get_platform_docker(mock_args)
        
        # Check that we only have the first train
        platforms = result['platforms']
        self.assertEqual(len(platforms), 1)
        
        trains = platforms[0]['events']
        self.assertEqual(len(trains), 1)
        self.assertEqual(trains[0]['uid'], 'NY12345')
    
    @patch('api.db')
    def test_get_platform_docker_days_filtering(self, mock_db):
        """Test platform docker API day of week filtering"""
        # Set up the mock to return our test session
        mock_db.session = self.session
        
        # Update one schedule to run only on weekdays
        schedule = self.session.query(BasicSchedule).filter_by(uid='NY12346').first()
        schedule.days_run = '1111100'  # Monday to Friday only
        self.session.commit()
        
        # Test with date that's a weekend (Sunday = index 6)
        mock_args = {
            'location': 'CHRX',
            'date_str': '2025-05-25',  # A Sunday when NY12346 doesn't run
            'start_time': '0700',
            'end_time': '1900'
        }
        
        # Call the API function
        result = get_platform_docker(mock_args)
        
        # Check that we only have the first train
        platforms = result['platforms']
        self.assertEqual(len(platforms), 1)
        
        trains = platforms[0]['events']
        self.assertEqual(len(trains), 1)
        self.assertEqual(trains[0]['uid'], 'NY12345')
    
    @patch('api.db')
    def test_get_platform_docker_date_range_filtering(self, mock_db):
        """Test platform docker API date range filtering"""
        # Set up the mock to return our test session
        mock_db.session = self.session
        
        # Update one schedule with a limited date range
        schedule = self.session.query(BasicSchedule).filter_by(uid='NY12346').first()
        schedule.runs_from = date(2025, 6, 1)  # Starts later
        self.session.commit()
        
        # Test with date before the second train starts running
        mock_args = {
            'location': 'CHRX',
            'date_str': '2025-05-20',  # Before NY12346 starts (June 1)
            'start_time': '0700',
            'end_time': '1900'
        }
        
        # Call the API function
        result = get_platform_docker(mock_args)
        
        # Check that we only have the first train
        platforms = result['platforms']
        self.assertEqual(len(platforms), 1)
        
        trains = platforms[0]['events']
        self.assertEqual(len(trains), 1)
        self.assertEqual(trains[0]['uid'], 'NY12345')
    
    @patch('api.db')
    def test_get_platform_docker_no_data(self, mock_db):
        """Test platform docker API with no matching data"""
        # Set up the mock to return our test session
        mock_db.session = self.session
        
        # Test with location that has no schedules
        mock_args = {
            'location': 'NOWHERE',
            'date_str': '2025-05-19',
            'start_time': '0700',
            'end_time': '1900'
        }
        
        # Call the API function
        result = get_platform_docker(mock_args)
        
        # Check that we get a successful but empty response
        self.assertTrue(result['success'])
        self.assertEqual(len(result['platforms']), 0)
    
    @patch('api.db')
    def test_get_platform_docker_association_info(self, mock_db):
        """Test platform docker API includes association information"""
        # Set up the mock to return our test session
        mock_db.session = self.session
        
        # Mock app request arguments
        mock_args = {
            'location': 'CHRX',
            'date_str': '2025-05-19',
            'start_time': '0700',
            'end_time': '1900'
        }
        
        # Call the API function
        result = get_platform_docker(mock_args)
        
        # Check that associations are correctly marked
        platforms = result['platforms']
        trains = platforms[0]['events']
        
        # Both trains should be marked as having associations
        train1 = next(t for t in trains if t['uid'] == 'NY12345')
        train2 = next(t for t in trains if t['uid'] == 'NY12346')
        
        self.assertTrue(train1['has_associations'])
        self.assertTrue(train2['has_associations'])

if __name__ == '__main__':
    unittest.main()