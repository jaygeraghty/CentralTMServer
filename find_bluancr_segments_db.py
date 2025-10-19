#!/usr/bin/env python3
"""
Script to find all segments that start or end at BLUANCR by querying the database
"""

import sys
from datetime import datetime
from database import get_db

def find_bluancr_segments():
    """Query database for segments starting or ending at BLUANCR"""
    
    db = get_db()
    segments_found = []
    
    try:
        # Query for schedules that have BLUANCR in their locations
        # We need to check all STP tables for comprehensive results
        
        stp_tables = [
            ('schedules_ltp', 'schedule_locations_ltp'),
            ('schedules_stp', 'schedule_locations_stp'), 
            ('schedules_overlay', 'schedule_locations_overlay'),
            ('schedules_cancellation', 'schedule_locations_cancellation')
        ]
        
        print(f"Searching for BLUANCR segments in database...")
        
        for schedule_table, location_table in stp_tables:
            print(f"Checking {schedule_table} and {location_table}...")
            
            # Find schedules with BLUANCR locations
            query = f"""
            SELECT DISTINCT s.id, s.uid, s.train_identity, s.runs_from, s.runs_to, 
                   s.days_run, s.train_status, s.train_category, s.stp_indicator
            FROM {schedule_table} s
            WHERE EXISTS (
                SELECT 1 FROM {location_table} sl 
                WHERE sl.schedule_id = s.id AND sl.tiploc = 'BLUANCR'
            )
            ORDER BY s.train_identity, s.uid
            """
            
            result = db.session.execute(query)
            schedules_with_bluancr = result.fetchall()
            
            print(f"Found {len(schedules_with_bluancr)} schedules with BLUANCR in {schedule_table}")
            
            # For each schedule, get the complete location sequence
            for schedule in schedules_with_bluancr:
                schedule_id = schedule[0]
                
                # Get all locations for this schedule in sequence order
                locations_query = f"""
                SELECT tiploc, sequence, location_type, arr_time, dep_time, pass_time,
                       platform, line, path, activity
                FROM {location_table}
                WHERE schedule_id = %s
                ORDER BY sequence
                """
                
                locations_result = db.session.execute(locations_query, (schedule_id,))
                locations = locations_result.fetchall()
                
                # Find BLUANCR positions and extract segments
                for i, location in enumerate(locations):
                    if location[0] == 'BLUANCR':  # tiploc
                        
                        # Segment starting at BLUANCR (BLUANCR -> next location)
                        if i < len(locations) - 1:
                            next_loc = locations[i + 1]
                            segment = {
                                'type': 'STARTS_AT_BLUANCR',
                                'schedule_table': schedule_table,
                                'schedule_id': schedule_id,
                                'uid': schedule[1],
                                'train_identity': schedule[2],
                                'runs_from': schedule[3],
                                'runs_to': schedule[4],
                                'days_run': schedule[5],
                                'train_status': schedule[6],
                                'train_category': schedule[7],
                                'stp_indicator': schedule[8],
                                'from_tiploc': location[0],
                                'from_sequence': location[1],
                                'from_type': location[2],
                                'from_dep_time': location[4],
                                'from_pass_time': location[5],
                                'from_platform': location[6],
                                'from_activity': location[9],
                                'to_tiploc': next_loc[0],
                                'to_sequence': next_loc[1],
                                'to_type': next_loc[2],
                                'to_arr_time': next_loc[3],
                                'to_pass_time': next_loc[5],
                                'to_platform': next_loc[6],
                                'to_activity': next_loc[9]
                            }
                            segments_found.append(segment)
                        
                        # Segment ending at BLUANCR (previous location -> BLUANCR)
                        if i > 0:
                            prev_loc = locations[i - 1]
                            segment = {
                                'type': 'ENDS_AT_BLUANCR',
                                'schedule_table': schedule_table,
                                'schedule_id': schedule_id,
                                'uid': schedule[1],
                                'train_identity': schedule[2],
                                'runs_from': schedule[3],
                                'runs_to': schedule[4],
                                'days_run': schedule[5],
                                'train_status': schedule[6],
                                'train_category': schedule[7],
                                'stp_indicator': schedule[8],
                                'from_tiploc': prev_loc[0],
                                'from_sequence': prev_loc[1],
                                'from_type': prev_loc[2],
                                'from_dep_time': prev_loc[4],
                                'from_pass_time': prev_loc[5],
                                'from_platform': prev_loc[6],
                                'from_activity': prev_loc[9],
                                'to_tiploc': location[0],
                                'to_sequence': location[1],
                                'to_type': location[2],
                                'to_arr_time': location[3],
                                'to_pass_time': location[5],
                                'to_platform': location[6],
                                'to_activity': location[9]
                            }
                            segments_found.append(segment)
    
    except Exception as e:
        print(f"Database error: {e}")
        return []
    
    finally:
        db.close()
    
    return segments_found

def write_results_to_file(segments):
    """Write results to bluancr_segments.txt"""
    
    output_file = 'bluancr_segments.txt'
    
    with open(output_file, 'w') as f:
        f.write(f"BLUANCR SEGMENTS ANALYSIS (Database Query)\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total segments found: {len(segments)}\n")
        f.write("=" * 80 + "\n\n")
        
        # Group by type
        starts_at_bluancr = [s for s in segments if s['type'] == 'STARTS_AT_BLUANCR']
        ends_at_bluancr = [s for s in segments if s['type'] == 'ENDS_AT_BLUANCR']
        
        f.write(f"SEGMENTS STARTING AT BLUANCR: {len(starts_at_bluancr)}\n")
        f.write("-" * 50 + "\n")
        for segment in starts_at_bluancr:
            f.write(f"Train: {segment['train_identity']} (UID: {segment['uid']})\n")
            f.write(f"Route: {segment['from_tiploc']} -> {segment['to_tiploc']}\n")
            f.write(f"Times: {segment['from_dep_time'] or segment['from_pass_time']} -> {segment['to_arr_time'] or segment['to_pass_time']}\n")
            f.write(f"Runs: {segment['runs_from']} to {segment['runs_to']}\n")
            f.write(f"Days: {segment['days_run']}\n")
            f.write(f"Status: {segment['train_status']} | Category: {segment['train_category']} | STP: {segment['stp_indicator']}\n")
            f.write(f"BLUANCR Platform: {segment['from_platform']} | Activity: {segment['from_activity']}\n")
            f.write(f"Next Platform: {segment['to_platform']} | Activity: {segment['to_activity']}\n")
            f.write(f"Table: {segment['schedule_table']} | ID: {segment['schedule_id']}\n")
            f.write("\n")
        
        f.write(f"\nSEGMENTS ENDING AT BLUANCR: {len(ends_at_bluancr)}\n")
        f.write("-" * 50 + "\n")
        for segment in ends_at_bluancr:
            f.write(f"Train: {segment['train_identity']} (UID: {segment['train_identity']})\n")
            f.write(f"Route: {segment['from_tiploc']} -> {segment['to_tiploc']}\n")
            f.write(f"Times: {segment['from_dep_time'] or segment['from_pass_time']} -> {segment['to_arr_time'] or segment['to_pass_time']}\n")
            f.write(f"Runs: {segment['runs_from']} to {segment['runs_to']}\n")
            f.write(f"Days: {segment['days_run']}\n")
            f.write(f"Status: {segment['train_status']} | Category: {segment['train_category']} | STP: {segment['stp_indicator']}\n")
            f.write(f"Previous Platform: {segment['from_platform']} | Activity: {segment['from_activity']}\n")
            f.write(f"BLUANCR Platform: {segment['to_platform']} | Activity: {segment['to_activity']}\n")
            f.write(f"Table: {segment['schedule_table']} | ID: {segment['schedule_id']}\n")
            f.write("\n")
        
        # Summary statistics
        f.write("\nSUMMARY STATISTICS\n")
        f.write("-" * 30 + "\n")
        f.write(f"Total segments: {len(segments)}\n")
        f.write(f"Segments starting at BLUANCR: {len(starts_at_bluancr)}\n")
        f.write(f"Segments ending at BLUANCR: {len(ends_at_bluancr)}\n")
        
        # Unique train identities
        unique_trains = set(s['train_identity'] for s in segments if s['train_identity'])
        f.write(f"Unique train identities: {len(unique_trains)}\n")
        if unique_trains:
            f.write(f"Train identities: {', '.join(sorted(unique_trains))}\n")
        
        # By STP indicator
        by_stp = {}
        for segment in segments:
            stp = segment['stp_indicator']
            by_stp[stp] = by_stp.get(stp, 0) + 1
        
        f.write(f"\nBy STP Indicator:\n")
        for stp, count in sorted(by_stp.items()):
            f.write(f"  {stp}: {count} segments\n")

def main():
    """Main function"""
    
    print("Searching database for segments that start or end at BLUANCR...")
    start_time = datetime.now()
    
    segments = find_bluancr_segments()
    
    if segments:
        write_results_to_file(segments)
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        starts_at = len([s for s in segments if s['type'] == 'STARTS_AT_BLUANCR'])
        ends_at = len([s for s in segments if s['type'] == 'ENDS_AT_BLUANCR'])
        
        print(f"\nCompleted! Found {len(segments)} segments involving BLUANCR")
        print(f"- {starts_at} segments starting at BLUANCR")
        print(f"- {ends_at} segments ending at BLUANCR")
        print(f"Processing time: {processing_time:.2f} seconds")
        print(f"Results written to: bluancr_segments.txt")
    else:
        print("No segments found involving BLUANCR")

if __name__ == "__main__":
    main()