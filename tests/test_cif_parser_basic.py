import unittest
import os
import sys
from datetime import date
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cif_parser import CIFParser

class TestCIFParserBasic(unittest.TestCase):
    """Basic unit tests for CIF Parser that don't require database access"""
    
    def setUp(self):
        """Set up a CIF parser instance for each test"""
        # Patch the area_of_interest from app config
        with patch('cif_parser.app.config.get', return_value={'CHRX', 'WLOE'}):
            self.parser = CIFParser()
    
    def test_parse_cif_date(self):
        """Test that CIF dates are correctly parsed"""
        # Test valid date
        self.assertEqual(
            self.parser.parse_cif_date('230501'),
            date(2023, 5, 1)
        )
        
        # Test invalid date
        self.assertIsNone(self.parser.parse_cif_date('invalid'))
    
    def test_is_in_area_of_interest(self):
        """Test the area of interest filtering"""
        # Test with a location in the area of interest
        locations = [{'tiploc': 'CHRX'}, {'tiploc': 'WATERLOO'}]
        self.assertTrue(self.parser.is_in_area_of_interest(locations))
        
        # Test with no locations in the area of interest
        locations = [{'tiploc': 'NOWHERE'}, {'tiploc': 'SOMESTATION'}]
        self.assertFalse(self.parser.is_in_area_of_interest(locations))
        
        # Test with empty locations list
        self.assertFalse(self.parser.is_in_area_of_interest([]))

if __name__ == '__main__':
    unittest.main()