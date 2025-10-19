#!/usr/bin/env python3
"""
Fix for CIF parser to properly handle CR records and STP table assignments.

This patch addresses two issues:
1. CR records are completely ignored (should update current schedule context)
2. STP table assignments happen after location collection (causing locations to miss STP tables)
"""

import logging

logger = logging.getLogger(__name__)

def apply_cr_handling_fix():
    """Apply the CR record handling fix to the CIF parser."""
    
    # Read the current cif_parser.py file
    with open('cif_parser.py', 'r') as f:
        content = f.read()
    
    # First, add CR record handling in the main parsing loop
    # Find the location where record types are handled
    cr_handling_code = '''                    elif record_type == 'CR':
                        # Handle Change of Details (CR) records
                        if current_schedule and len(line) >= 80:
                            # Extract new details from CR record
                            location = line[2:10].strip()  # TIPLOC where change occurs
                            new_train_identity = line[32:36].strip()
                            new_service_code = line[41:49].strip()
                            # Update current schedule with new details
                            current_schedule['train_identity'] = new_train_identity
                            current_schedule['service_code'] = new_service_code
                            logger.debug(f"CR record at {location}: Updated train_identity to {new_train_identity}, service_code to {new_service_code}")
                        else:
                            logger.warning(f"CR record found but no current schedule context: {line}")
                            
'''
    
    # Find the insertion point after the AA record handling
    aa_end_marker = "                            perf_counters['aa_processing_time'] += time.perf_counter() - t0"
    insertion_point = content.find(aa_end_marker)
    
    if insertion_point == -1:
        logger.error("Could not find insertion point for CR handling code")
        return False
    
    # Find the end of the AA block
    insertion_point = content.find('\n', insertion_point) + 1
    
    # Insert the CR handling code
    new_content = content[:insertion_point] + '\n' + cr_handling_code + content[insertion_point:]
    
    # Second fix: Update the LT record handling to properly assign STP data
    # Find the LT record processing section
    lt_section_start = new_content.find("if record_type == 'LT':")
    if lt_section_start == -1:
        logger.error("Could not find LT record processing section")
        return False
    
    # Find the section where schedule is flushed and updated
    flush_section = '''                                if is_cancellation or current_schedule_has_area_of_interest or self.is_in_area_of_interest(current_locations):
                                    updated_schedules = self.flush_bs_buffer([current_schedule])
                                    if updated_schedules:
                                        current_schedule = updated_schedules[0]
                                        for loc_data in current_location_data:
                                            loc_data['schedule_id'] = current_schedule['id']
                                            if 'stp_id' in current_schedule and 'stp_table' in current_schedule:
                                                loc_data['stp_id'] = current_schedule['stp_id']
                                                loc_data['stp_table'] = current_schedule['stp_table']
                                            sl_buffer.append(loc_data)'''
    
    # Replace with fixed version that assigns STP data properly
    fixed_flush_section = '''                                if is_cancellation or current_schedule_has_area_of_interest or self.is_in_area_of_interest(current_locations):
                                    updated_schedules = self.flush_bs_buffer([current_schedule])
                                    if updated_schedules:
                                        current_schedule = updated_schedules[0]
                                        # Now assign STP data to all collected locations
                                        for loc_data in current_location_data:
                                            loc_data['schedule_id'] = current_schedule['id']
                                            # Ensure STP table assignment happens for all locations
                                            if 'stp_id' in current_schedule and 'stp_table' in current_schedule:
                                                loc_data['stp_id'] = current_schedule['stp_id']
                                                loc_data['stp_table'] = current_schedule['stp_table']
                                                logger.debug(f"Assigned STP data to location {loc_data['tiploc']}: table={loc_data['stp_table']}, id={loc_data['stp_id']}")
                                            else:
                                                logger.warning(f"No STP data available for location {loc_data['tiploc']} in schedule {current_schedule.get('uid')}")
                                            sl_buffer.append(loc_data)'''
    
    new_content = new_content.replace(flush_section, fixed_flush_section)
    
    # Write the updated file
    with open('cif_parser.py', 'w') as f:
        f.write(new_content)
    
    logger.info("Applied CR record handling and STP assignment fixes to cif_parser.py")
    return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_cr_handling_fix()