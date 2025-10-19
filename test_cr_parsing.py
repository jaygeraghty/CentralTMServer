#!/usr/bin/env python3
"""
Standalone test to reproduce the CR record parsing issue.
Tests parsing of the broken P14772 schedule without database operations.
"""

import os
from datetime import datetime
from typing import List, Dict, Any

class MockCIFParser:
    """Mock CIF parser to test CR record handling without database operations."""
    
    def __init__(self):
        self.area_of_interest = {'CANONST', 'BORMRKJ', 'LNDNBDE', 'KENTEJ', 'DEPTFD', 'GNWH', 'MAZEH', 
                                'WCOMBEP', 'CRLN', 'WOLWCDY', 'WOLWCHA', 'PLMS', 'ABWD', 'BELVEDR', 
                                'ERITH', 'SLADEGN', 'ERITHLP', 'BRNHPSJ', 'BRNHRST', 'BXLYHTH', 
                                'WELLING', 'FALCNWD', 'ELTHAM', 'KIDBROK', 'BLKHTH', 'LEWISHM', 
                                'STJOHNS', 'NWCROSS', 'SURRCNJ'}
        
    def parse_test_schedule(self, cif_lines: List[str]) -> Dict[str, Any]:
        """Parse a test schedule and return the results."""
        current_schedule = None
        location_seq = 0
        current_locations = []
        current_location_data = []
        current_schedule_has_area_of_interest = False
        
        results = {
            'schedules_found': 0,
            'locations_found': 0,
            'cr_records_found': 0,
            'cr_records_ignored': 0,
            'area_of_interest_locations': [],
            'parsing_log': [],
            'stp_assignment_flow': []
        }
        
        for line_num, line in enumerate(cif_lines, 1):
            line = line.rstrip()
            if not line or len(line) < 2:
                continue
                
            record_type = line[0:2]
            results['parsing_log'].append(f"Line {line_num}: {record_type} - {line[:50]}...")
            
            if record_type == 'CR':
                results['cr_records_found'] += 1
                results['cr_records_ignored'] += 1
                results['parsing_log'].append(f"  ❌ CR RECORD IGNORED: {line}")
                continue  # This is the bug - CR records are completely ignored!
                
            elif record_type in ['LO', 'LI', 'LT']:
                if current_schedule and len(current_schedule) > 0:
                    location_seq += 1
                    tiploc = line[2:10].strip()
                    results['locations_found'] += 1
                    
                    current_locations.append({'tiploc': tiploc})
                    if tiploc in self.area_of_interest:
                        current_schedule_has_area_of_interest = True
                        results['area_of_interest_locations'].append(tiploc)
                        results['parsing_log'].append(f"  ✅ AREA OF INTEREST: {tiploc}")
                    
                    # Parse location data (simplified)
                    location_data = {
                        'sequence': location_seq,
                        'location_type': record_type,
                        'tiploc': tiploc,
                    }
                    current_location_data.append(location_data)
                    
                    if record_type == 'LT':
                        # End of schedule - would normally save to database here
                        results['parsing_log'].append(f"  📝 END OF SCHEDULE: {len(current_location_data)} locations")
                        if current_schedule_has_area_of_interest:
                            results['parsing_log'].append(f"  ✅ WOULD SAVE: Schedule has area of interest locations")
                        else:
                            results['parsing_log'].append(f"  ❌ WOULD SKIP: No area of interest locations")
                
            elif record_type == 'BS':
                # Start of new schedule
                if len(line) >= 80:
                    uid = line[3:9]
                    train_identity = line[32:36]
                    stp_indicator = line[79:80]
                    
                    current_schedule = {
                        'uid': uid,
                        'train_identity': train_identity,
                        'stp_indicator': stp_indicator,
                    }
                    results['schedules_found'] += 1
                    results['parsing_log'].append(f"  📋 NEW SCHEDULE: {uid} ({train_identity}) STP:{stp_indicator}")
                    
                    # Reset state
                    current_locations = []
                    current_location_data = []
                    location_seq = 0
                    current_schedule_has_area_of_interest = False
        
        return results

def test_broken_schedule():
    """Test parsing of the broken P14772 schedule."""
    
    # The actual CIF data for P14772 (2P67)
    cif_data = [
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
        "CRBRNHRST OO2P67    124650005 EMU    075D     S",  # ❌ THIS CR RECORD IS IGNORED!
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
        "LTCANONST22155 21552     TF",
    ]
    
    parser = MockCIFParser()
    results = parser.parse_test_schedule(cif_data)
    
    print("="*80)
    print("🔍 CR RECORD PARSING TEST RESULTS")
    print("="*80)
    print(f"Schedules found: {results['schedules_found']}")
    print(f"Locations found: {results['locations_found']}")
    print(f"CR records found: {results['cr_records_found']}")
    print(f"CR records ignored: {results['cr_records_ignored']}")
    print(f"Area of interest locations: {len(results['area_of_interest_locations'])}")
    print(f"Area of interest TIPLOCs: {', '.join(results['area_of_interest_locations'])}")
    
    print("\n📝 PARSING LOG:")
    print("-"*80)
    for log_entry in results['parsing_log']:
        print(log_entry)
    
    print("\n🔍 ANALYSIS:")
    print("-"*80)
    if results['cr_records_found'] > 0:
        print("❌ PROBLEM IDENTIFIED: CR records are being completely ignored!")
        print("   This means locations after CR records are still processed,")
        print("   but the CR record itself (which changes service details) is lost.")
        print("   This breaks the schedule continuity and may cause database issues.")
    
    if len(results['area_of_interest_locations']) > 0:
        print("✅ Schedule HAS area of interest locations and SHOULD be saved")
        print("   The fact that it's not being saved to STP tables suggests")
        print("   the CR record handling bug is breaking the save process.")
    else:
        print("❌ No area of interest locations found")
    
    return results

if __name__ == "__main__":
    test_broken_schedule()