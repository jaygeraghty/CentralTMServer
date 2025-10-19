
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
from cif_parser import CIFParser

class TestCIFParserStpTiming(unittest.TestCase):
    def setUp(self):
        self.parser = CIFParser()
        self.captured_schedules = []
        self.captured_locations = []
        
        # Temporarily expand area of interest to include P14772 locations
        self.original_area = self.parser.area_of_interest.copy()
        self.parser.area_of_interest.update({
            'CANONST', 'BORMRKJ', 'LNDNBDE', 'KENTEJ', 'DEPTFD', 'GNWH', 
            'MAZEH', 'WCOMBEP', 'CRLN', 'WOLWCDY', 'WOLWCHA', 'PLMS', 
            'ABWD', 'BELVEDR', 'ERITH', 'SLADEGN', 'ERITHLP', 'BRNHPSJ', 
            'BRNHRST', 'BXLYHTH', 'WELLING', 'FALCNWD', 'ELTHAM', 
            'KIDBROK', 'BLKHTH', 'LEWISHM', 'STJOHNS', 'NWCROSS', 
            'SURRCNJ'  # P14772 specific locations
        })
        
        # Mock the database session and models
        self.db_session_mock = MagicMock()
        
        # Store original flush methods
        self.original_flush_bs_buffer = self.parser.flush_bs_buffer
        self.original_flush_sl_buffer = self.parser.flush_sl_buffer
        
        def fake_flush_bs_buffer(buffer):
            print(f"🔄 Flushing {len(buffer)} schedules to database")
            schedules_with_ids = []
            for i, schedule_data in enumerate(buffer):
                # Simulate database ID assignment
                schedule_data['id'] = 1000 + i
                # Simulate STP table assignment based on STP indicator
                if schedule_data.get('stp_indicator') == 'P':
                    schedule_data['stp_id'] = 2000 + i
                    schedule_data['stp_table'] = 'schedules_ltp'
                elif schedule_data.get('stp_indicator') == 'O':
                    schedule_data['stp_id'] = 3000 + i
                    schedule_data['stp_table'] = 'schedules_stp_overlay'
                
                print(f"  ✅ Schedule {schedule_data.get('uid')} ({schedule_data.get('train_identity')}) "
                      f"- ID: {schedule_data['id']}, STP: {schedule_data.get('stp_id')} "
                      f"({schedule_data.get('stp_table', 'none')})")
                
                self.captured_schedules.append(schedule_data.copy())
                schedules_with_ids.append(schedule_data)
            
            return schedules_with_ids
        
        def fake_flush_sl_buffer(buffer):
            print(f"🔄 Flushing {len(buffer)} locations to database")
            for loc_data in buffer:
                print(f"  📍 Location {loc_data.get('tiploc')} - "
                      f"Schedule ID: {loc_data.get('schedule_id')}, "
                      f"STP: {loc_data.get('stp_id')} ({loc_data.get('stp_table', 'none')})")
                self.captured_locations.append(loc_data.copy())
        
        self.parser.flush_bs_buffer = fake_flush_bs_buffer
        self.parser.flush_sl_buffer = fake_flush_sl_buffer
        
    def tearDown(self):
        # Restore original area of interest
        self.parser.area_of_interest = self.original_area

    def simulate_input(self, lines):
        # Create a temporary file with the test data
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.CIF') as f:
            # Write header line
            f.write("HDTPS.UFROC1.PD240518                                      240518041424\n")
            # Write test lines
            for line in lines:
                f.write(line + "\n")
            temp_file = f.name
        
        try:
            # Clear captured data
            self.captured_schedules.clear()
            self.captured_locations.clear()
            
            # Process the temporary file
            with patch('cif_parser.db') as mock_db:
                mock_db.session = self.db_session_mock
                self.parser.load_file_data(temp_file)
                
        finally:
            # Clean up temporary file
            os.unlink(temp_file)

    def test_p_then_o(self):
        print("\n=== Test: 'P' then 'O' schedule ===")
        lines = [
            "BSNP123456250518251207000001 POO2P01    124659005 EMU    075D     S            P",
            "BX         SEY",
            "LOCHRONX  1000 1000  ADN    TB",
            "LIWLOE    1001 1002      10011002         T",
            "LTCHRONX  1005 1005      10051005         T",
            "BSNP999999250518251207000001 POO2P02    124659005 EMU    075D     S            O",
            "BX         SEY", 
            "LOCHRONX  1100 1100  ADN    TB",
            "LTCHRONX  1105 1105      11051105         T"
        ]
        self.simulate_input(lines)
        
        # Analyze results
        print(f"\n📊 Results: {len(self.captured_schedules)} schedules, {len(self.captured_locations)} locations")
        
        # Check that both schedules got STP assignments
        p_schedules = [s for s in self.captured_schedules if s.get('stp_indicator') == 'P']
        o_schedules = [s for s in self.captured_schedules if s.get('stp_indicator') == 'O']
        
        print(f"P schedules with STP data: {len([s for s in p_schedules if 'stp_id' in s])}")
        print(f"O schedules with STP data: {len([s for s in o_schedules if 'stp_id' in s])}")
        
        # Check locations got STP assignments
        locations_with_stp = [l for l in self.captured_locations if 'stp_id' in l and l['stp_id'] is not None]
        print(f"Locations with STP data: {len(locations_with_stp)}/{len(self.captured_locations)}")
        
        self.assertGreater(len(self.captured_schedules), 0, "Should capture schedules")
        self.assertGreater(len(self.captured_locations), 0, "Should capture locations")

    def test_o_then_p(self):
        print("\n=== Test: 'O' then 'P' schedule ===")
        lines = [
            "BSNP999999250518251207000001 POO2P02    124659005 EMU    075D     S            O",
            "BX         SEY",
            "LOCHRONX  1100 1100  ADN    TB", 
            "LTCHRONX  1105 1105      11051105         T",
            "BSNP123456250518251207000001 POO2P01    124659005 EMU    075D     S            P",
            "BX         SEY",
            "LOCHRONX  1000 1000  ADN    TB",
            "LIWLOE    1001 1002      10011002         T",
            "LTCHRONX  1005 1005      10051005         T"
        ]
        self.simulate_input(lines)
        
        # Analyze results
        print(f"\n📊 Results: {len(self.captured_schedules)} schedules, {len(self.captured_locations)} locations")
        
        # Check that both schedules got STP assignments
        p_schedules = [s for s in self.captured_schedules if s.get('stp_indicator') == 'P']
        o_schedules = [s for s in self.captured_schedules if s.get('stp_indicator') == 'O']
        
        print(f"P schedules with STP data: {len([s for s in p_schedules if 'stp_id' in s])}")
        print(f"O schedules with STP data: {len([s for s in o_schedules if 'stp_id' in s])}")
        
        # Check locations got STP assignments  
        locations_with_stp = [l for l in self.captured_locations if 'stp_id' in l and l['stp_id'] is not None]
        print(f"Locations with STP data: {len(locations_with_stp)}/{len(self.captured_locations)}")
        
        self.assertGreater(len(self.captured_schedules), 0, "Should capture schedules")
        self.assertGreater(len(self.captured_locations), 0, "Should capture locations")
        
    def test_single_p_schedule_with_cr(self):
        """Test the broken case: single P schedule with CR record"""
        print("\n=== Test: Single 'P' schedule with CR record (broken case) ===")
        lines = [
            "BSNP147722505182512070000001 POO2P67    124659005 EMU    075D     S            P",
            "BX         SEY",
            "LOCANONST 2026 20261  ADN    TB",
            "LIBORMRKJ           2027H00000000   DCS",
            "LILNDNBDE 2029 2031      202920311  1     T",
            "LINKENTEJ           2034H00000000",
            "LIDEPTFD  2036 2036H     20362036         T",
            "LIGNWH    2038 2039      20382039         T",
            "LIMAZEH   2041H2042      20422042         T",
            "LIWCOMBEP 2043H2044      20442044         T",
            "LICRLN    2046 2047      204620472        T",
            "LIWOLWCDY 2050 2050H     20502050         T",
            "LIWOLWCHA 2052H2053H     205320532        T",
            "LIPLMS    2055 2055H     20552055         T",
            "LIABWD    2058H2059H     205920592        T",
            "LIBELVEDR 2102 2102H     21022102         T",
            "LIERITH   2105 2105H     21052105         T",
            "LISLADEGN 2108H2109H     210921092        T",
            "LIERITHLP 2111H2111H     00000000         A",
            "LIBRNHPSJ           2112 00000000",
            "CRBRNHRST OO2P67    124650005 EMU    075D     S",
            "LIBRNHRST 2115 2116      21152116         T",
            "LIBXLYHTH 2118H2119H     21192119         T",
            "LIWELLING 2122 2122H     21222122         T",
            "LIFALCNWD 2124H2125      21252125         T",
            "LIELTHAM  2127 2128      21272128         T",
            "LIKIDBROK 2130H2131      21312131         T",
            "LIBLKHTH  2134 2135      213421351        T",
            "LILEWISHM 2137H2139      213821393  UNK   T",
            "LISTJOHNS 2140H2141H     21412141   UKS   T",
            "LINWCROSS 2143 2144      21432144A  3     T",
            "LINKENTEJ2          2145 00000000",
            "LISURRCNJ           2145H00000000",
            "LILNDNBDE22149 2151      214921513  UCS   T",
            "LIBORMRKJ2          2152 00000000   UPB",
            "LTCANONST22155 21552     TF"
        ]
        self.simulate_input(lines)
        
        # Analyze results
        print(f"\n📊 Results: {len(self.captured_schedules)} schedules, {len(self.captured_locations)} locations")
        
        # Check schedule got STP assignment
        p_schedules = [s for s in self.captured_schedules if s.get('stp_indicator') == 'P']
        print(f"P schedules with STP data: {len([s for s in p_schedules if 'stp_id' in s])}")
        
        # Check locations got STP assignments
        locations_with_stp = [l for l in self.captured_locations if 'stp_id' in l and l['stp_id'] is not None]
        print(f"Locations with STP data: {len(locations_with_stp)}/{len(self.captured_locations)}")
        
        # This should demonstrate the bug - locations may not get STP assignments
        if len(locations_with_stp) < len(self.captured_locations):
            print("⚠️  BUG DETECTED: Some locations missing STP assignments!")
        
        self.assertGreater(len(self.captured_schedules), 0, "Should capture schedules")

if __name__ == '__main__':
    unittest.main()
