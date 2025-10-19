import os
import unittest
import tempfile
from datetime import date
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import app
from models import (
    Base, ParsedFile, BasicSchedule, ScheduleLocation, Association,
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation,
    AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation
)
from cif_parser import CIFParser
import database

class TestCIFParserIntegration(unittest.TestCase):
    """Integration tests for the CIF Parser with realistic test data"""
    
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
        
        # Set up a minimal area of interest
        self.parser.area_of_interest = {'CHRX', 'WLOE'}
    
    def tearDown(self):
        """Clear tables after each test"""
        self.session.rollback()
        self.session.close()
    
    def create_test_cif_file(self, content):
        """Create a temporary CIF file with the given content"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.CIF')
        temp_file.write(content.encode('utf-8'))
        temp_file.close()
        return temp_file.name
    
    def test_full_record_set_parsing(self):
        """Test parsing a complete set of CIF records including header, schedule, and locations"""
        # Create a test CIF file content with header, schedule, and locations
        cif_content = """HDTPS.UCFCATE.PD1905192305190001DFROC        FA250519112019
BSNY123452305192312311234567P      OO1Z125671234        D               
LOCHAINGHIL0915 0925H  TB                                               
LIMAYBOLE 0933 09341     TB         D                                   
LIAYR     0957 1000      TB         D                                   
LTIRVINE  1010      TB                                                  
BSNY123462305192312311234560P      OO2Y015679876        D               
LOIRVINE  1152 1154      TB                                             
LIAYR     1208 1211      TB         D                                   
LIMAYBOLE 1239 1242H     TB         D                                   
LTCHAINGHIL1256      TB                                                 
AAJJ123456NY123452305192512311234567CHRX    0290519N
ZZ"""
        
        file_path = self.create_test_cif_file(cif_content)
        
        try:
            # Process the file
            self.parser.process_file(file_path)
            
            # Verify that the file was recorded as processed
            parsed_files = self.session.query(ParsedFile).all()
            self.assertEqual(len(parsed_files), 1)
            self.assertEqual(parsed_files[0].file_ref, 'TPS.UCF')
            self.assertEqual(parsed_files[0].extract_type, 'F')
            
            # Verify basic schedules were stored
            schedules = self.session.query(BasicSchedule).all()
            self.assertEqual(len(schedules), 2)
            
            # Check the first schedule
            first_schedule = next(s for s in schedules if s.uid == 'NY12345')
            self.assertEqual(first_schedule.train_identity, '1Z12')
            self.assertEqual(first_schedule.days_run, '1234567')
            self.assertEqual(first_schedule.runs_from, date(2023, 5, 19))
            self.assertEqual(first_schedule.runs_to, date(2023, 12, 31))
            
            # Verify schedule locations
            first_schedule_locations = self.session.query(ScheduleLocation).filter(
                ScheduleLocation.schedule_id == first_schedule.id
            ).order_by(ScheduleLocation.sequence).all()
            
            self.assertEqual(len(first_schedule_locations), 4)
            
            # Check origin
            self.assertEqual(first_schedule_locations[0].location_type, 'LO')
            self.assertEqual(first_schedule_locations[0].tiploc, 'CHAINGHIL')
            self.assertEqual(first_schedule_locations[0].dep, '0925')
            
            # Check terminating location
            self.assertEqual(first_schedule_locations[3].location_type, 'LT')
            self.assertEqual(first_schedule_locations[3].tiploc, 'IRVINE')
            self.assertEqual(first_schedule_locations[3].arr, '1010')
            
            # Verify associations
            associations = self.session.query(Association).all()
            self.assertEqual(len(associations), 1)
            self.assertEqual(associations[0].main_uid, 'JJ12345')
            self.assertEqual(associations[0].assoc_uid, 'NY12345')
            self.assertEqual(associations[0].location, 'CHRX')
            self.assertEqual(associations[0].days_run, '1234567')
            
        finally:
            # Clean up temp file
            os.unlink(file_path)
    
    def test_location_filtering(self):
        """Test that schedules are correctly filtered by location"""
        # Create a test CIF file with two schedules, only one with locations in area of interest
        cif_content = """HDTPS.UCFCATE.PD1905192305190001DFROC        FA250519112019
BSNY123452305192312311234567P      OO1Z125671234        D               
LOCHAINGHIL0915 0925H  TB                                               
LICHRX    0933 09341     TB         D                                   
LIAYR     0957 1000      TB         D                                   
LTIRVINE  1010      TB                                                  
BSNY123462305192312311234560P      OO2Y015679876        D               
LOOTHERL  1152 1154      TB                                             
LIANOTHERST1208 1211      TB         D                                   
LTSOMEWHR 1256      TB                                                 
ZZ"""
        
        file_path = self.create_test_cif_file(cif_content)
        
        try:
            # Process the file
            self.parser.process_file(file_path)
            
            # Verify that only schedules with locations in area of interest were processed
            schedules = self.session.query(BasicSchedule).all()
            self.assertEqual(len(schedules), 1)
            self.assertEqual(schedules[0].uid, 'NY12345')
            
            # Check that the second schedule was filtered out
            second_schedule = self.session.query(BasicSchedule).filter(
                BasicSchedule.uid == 'NY12346'
            ).first()
            self.assertIsNone(second_schedule)
            
        finally:
            # Clean up temp file
            os.unlink(file_path)
    
    def test_schedule_with_associations(self):
        """Test parsing schedules with associations and verify linked UIDs"""
        # Create a test CIF file with two schedules and an association
        cif_content = """HDTPS.UCFCATE.PD1905192305190001DFROC        FA250519112019
BSNY123452305192312311234567P      OO1Z125671234        D               
LOCHRX    0915 0925H  TB                                               
LIWLOE    0933 09341     TB         D                                   
LTOTHERSTAT1010      TB                                                  
BSJJ123452305192312311234567P      OO1A125671234        D               
LOOTHERSTAT1020 1025      TB                                             
LIWLOE    1033 10341     TB         D                                   
LTCHRX    1050      TB                                                 
AAJJ123456NY123452305192512311234567WLOE    0290519N
ZZ"""
        
        file_path = self.create_test_cif_file(cif_content)
        
        try:
            # Process the file
            self.parser.process_file(file_path)
            
            # Verify that both schedules were processed
            schedules = self.session.query(BasicSchedule).all()
            self.assertEqual(len(schedules), 2)
            
            # Find schedules by UID
            first_schedule = next(s for s in schedules if s.uid == 'NY12345')
            second_schedule = next(s for s in schedules if s.uid == 'JJ12345')
            
            # Verify association
            associations = self.session.query(Association).all()
            self.assertEqual(len(associations), 1)
            
            # Check association links the two schedules
            self.assertEqual(associations[0].main_uid, 'JJ12345')
            self.assertEqual(associations[0].assoc_uid, 'NY12345')
            self.assertEqual(associations[0].location, 'WLOE')
            
            # Check association date ranges
            self.assertEqual(associations[0].date_from, date(2023, 5, 19))
            self.assertEqual(associations[0].date_to, date(2025, 12, 31))
            
        finally:
            # Clean up temp file
            os.unlink(file_path)
    
    def test_parse_train_characteristics(self):
        """Test parsing various train characteristics from BS records"""
        # Create a test CIF file with schedules having different characteristics
        cif_content = """HDTPS.UCFCATE.PD1905192305190001DFROC        FA250519112019
BSNY123452305192312311234567P      OO1Z125671234        D               
LOCHRX    0915 0925H  TB                                               
LTWLOE    1010      TB                                                  
BSJJ123462305192312311234567P      EE2A125671234        E 100 100MPH    
LOWLOE    1020 1025H  TC                                               
LTCHRX    1050      TD                                                 
BSP123472305192312311234560O      XX3B125671234        EMU120 90MPH    
LOCHRX    1120 1125H  TC                                               
LTWLOE    1150      TD
ZZ"""
        
        file_path = self.create_test_cif_file(cif_content)
        
        try:
            # Process the file
            self.parser.process_file(file_path)
            
            # Verify that all schedules were processed
            schedules = self.session.query(BasicSchedule).all()
            self.assertEqual(len(schedules), 3)
            
            # Find and check first schedule
            first_schedule = next(s for s in schedules if s.uid == 'NY12345')
            self.assertEqual(first_schedule.train_category, 'OO')
            self.assertEqual(first_schedule.train_identity, '1Z12')
            self.assertEqual(first_schedule.headcode, '1Z12')
            self.assertEqual(first_schedule.power_type, '567')
            self.assertEqual(first_schedule.operating_chars, 'D')
            
            # Find and check second schedule
            second_schedule = next(s for s in schedules if s.uid == 'JJ12346')
            self.assertEqual(second_schedule.train_category, 'EE')
            self.assertEqual(second_schedule.train_identity, '2A12')
            self.assertEqual(second_schedule.speed, 100)
            
            # Find and check third schedule
            third_schedule = next(s for s in schedules if s.uid == 'P12347')
            self.assertEqual(third_schedule.train_category, 'XX')
            self.assertEqual(third_schedule.train_identity, '3B12')
            self.assertEqual(third_schedule.power_type, 'EMU')
            self.assertEqual(third_schedule.speed, 90)
            self.assertEqual(third_schedule.stp_indicator, 'O')  # Overlay
            
        finally:
            # Clean up temp file
            os.unlink(file_path)
    
    def test_integration_with_real_schedule_format(self):
        """Test parser against a sample formatted closest to a real CIF file"""
        # Create a test CIF file with realistic formatting
        cif_content = """HDTPS.UCFCATE.PD1905192305190001DFROC        FA250519112019
TIPWOKINGSS                                                             
TICLPHMJN                                                               
TISURBITON                                                              
TICHRX   CHARING CROSS                                                  
BSNY123462705221712250000010P      EE1A125671234        D               
LOCHRX    0556H0600      1         T                                    
LIWATERLOO0606 0608      2                                              
LICLAPHAM J0616 0617                                                    
LIWOKING  0641 0643H     3         T                                    
LTGUILDFD 0655      4         T                                         
BSNY123472705221712251234560P      XX2Y125671234        EMU120 90MPH    
LOGUILDFD 0710 0712      1         T                                    
LIWOKING  0725 0728      2         T                                    
LISURBITON0748 0750      3                                              
LICLAPHAM J0806 0808                                                    
LIWATERLOO0818 0820                                                     
LTCHRX    0830      1         T                                         
AANY123467NY123472305192512311234567WOKING  F 290519N
ZZ"""
        
        file_path = self.create_test_cif_file(cif_content)
        
        try:
            # Process the file
            self.parser.process_file(file_path)
            
            # Verify that the file was recorded as processed
            parsed_files = self.session.query(ParsedFile).all()
            self.assertEqual(len(parsed_files), 1)
            
            # Verify basic schedules were stored
            schedules = self.session.query(BasicSchedule).all()
            self.assertEqual(len(schedules), 2)
            
            # Check the first schedule details
            first_schedule = next(s for s in schedules if s.uid == 'NY12346')
            self.assertEqual(first_schedule.train_identity, '1A12')
            self.assertEqual(first_schedule.days_run, '0000010')  # Saturday only
            self.assertEqual(first_schedule.runs_from, date(2027, 5, 22))
            self.assertEqual(first_schedule.runs_to, date(2017, 12, 25))  # Past date for testing
            
            # Check the second schedule details
            second_schedule = next(s for s in schedules if s.uid == 'NY12347')
            self.assertEqual(second_schedule.train_identity, '2Y12')
            self.assertEqual(second_schedule.days_run, '1234560')  # Monday to Saturday
            self.assertEqual(second_schedule.power_type, 'EMU')
            self.assertEqual(second_schedule.speed, 90)
            
            # Check locations for first schedule
            first_locations = self.session.query(ScheduleLocation).filter(
                ScheduleLocation.schedule_id == first_schedule.id
            ).order_by(ScheduleLocation.sequence).all()
            
            self.assertEqual(len(first_locations), 5)
            
            # Check the origin location
            origin = first_locations[0]
            self.assertEqual(origin.tiploc, 'CHRX')
            self.assertEqual(origin.platform, '1')
            self.assertEqual(origin.dep, '0600')
            self.assertEqual(origin.activity, 'T')
            
            # Verify associations
            associations = self.session.query(Association).all()
            self.assertEqual(len(associations), 1)
            self.assertEqual(associations[0].main_uid, 'NY12346')
            self.assertEqual(associations[0].assoc_uid, 'NY12347')
            self.assertEqual(associations[0].location, 'WOKING')
            self.assertEqual(associations[0].date_indicator, 'F')  # From
            
        finally:
            # Clean up temp file
            os.unlink(file_path)

if __name__ == '__main__':
    unittest.main()