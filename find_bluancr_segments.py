#!/usr/bin/env python3
"""
One-off script to find all segments that start or end at BLUANCR
Searches through CIF files and logs results to bluancr_segments.txt
"""

import os
import re
from datetime import datetime

def parse_cif_for_bluancr_segments():
    """Parse CIF files to find segments starting or ending at BLUANCR"""
    
    segments_found = []
    current_schedule = None
    current_locations = []
    
    # Look for CIF files
    cif_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.CIF') or file.endswith('.cif'):
                cif_files.append(os.path.join(root, file))
    
    print(f"Found {len(cif_files)} CIF files to process")
    
    for cif_file in cif_files:
        print(f"Processing: {cif_file}")
        
        try:
            with open(cif_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Basic Schedule (BS) record - start of a new schedule
                    if line.startswith('BS'):
                        # Process previous schedule if it had BLUANCR
                        if current_schedule and current_locations:
                            process_schedule_for_bluancr(current_schedule, current_locations, segments_found, cif_file)
                        
                        # Start new schedule
                        current_schedule = {
                            'type': 'BS',
                            'line_num': line_num,
                            'uid': line[3:9] if len(line) > 9 else '',
                            'runs_from': line[9:15] if len(line) > 15 else '',
                            'runs_to': line[15:21] if len(line) > 21 else '',
                            'days_run': line[21:28] if len(line) > 28 else '',
                            'train_identity': line[32:36] if len(line) > 36 else '',
                            'raw_line': line
                        }
                        current_locations = []
                    
                    # Location Intermediate (LI), Location Origin (LO), Location Terminating (LT)
                    elif line.startswith(('LI', 'LO', 'LT')):
                        if current_schedule:
                            tiploc = line[2:9].strip() if len(line) > 9 else ''
                            location_data = {
                                'type': line[:2],
                                'tiploc': tiploc,
                                'arr_time': line[10:14] if len(line) > 14 else '',
                                'dep_time': line[15:19] if len(line) > 19 else '',
                                'pass_time': line[20:24] if len(line) > 24 else '',
                                'platform': line[24:27] if len(line) > 27 else '',
                                'line': line[27:30] if len(line) > 30 else '',
                                'path': line[30:33] if len(line) > 33 else '',
                                'activity': line[33:45] if len(line) > 45 else '',
                                'raw_line': line
                            }
                            current_locations.append(location_data)
            
            # Process the last schedule in the file
            if current_schedule and current_locations:
                process_schedule_for_bluancr(current_schedule, current_locations, segments_found, cif_file)
                
        except Exception as e:
            print(f"Error processing {cif_file}: {e}")
    
    return segments_found

def process_schedule_for_bluancr(schedule, locations, segments_found, filename):
    """Check if schedule has BLUANCR and extract segment information"""
    
    bluancr_locations = [loc for loc in locations if 'BLUANCR' in loc['tiploc']]
    
    if not bluancr_locations:
        return
    
    # Find segments where BLUANCR is start or end
    for i, bluancr_loc in enumerate(bluancr_locations):
        bluancr_index = locations.index(bluancr_loc)
        
        # Segment starting at BLUANCR (BLUANCR -> next location)
        if bluancr_index < len(locations) - 1:
            next_loc = locations[bluancr_index + 1]
            segment = {
                'type': 'STARTS_AT_BLUANCR',
                'from_tiploc': bluancr_loc['tiploc'],
                'to_tiploc': next_loc['tiploc'],
                'from_time': bluancr_loc['dep_time'] or bluancr_loc['pass_time'],
                'to_time': next_loc['arr_time'] or next_loc['pass_time'],
                'train_uid': schedule['uid'],
                'train_identity': schedule['train_identity'],
                'runs_from': schedule['runs_from'],
                'runs_to': schedule['runs_to'],
                'days_run': schedule['days_run'],
                'filename': filename,
                'bluancr_platform': bluancr_loc['platform'],
                'bluancr_activity': bluancr_loc['activity']
            }
            segments_found.append(segment)
        
        # Segment ending at BLUANCR (previous location -> BLUANCR)
        if bluancr_index > 0:
            prev_loc = locations[bluancr_index - 1]
            segment = {
                'type': 'ENDS_AT_BLUANCR',
                'from_tiploc': prev_loc['tiploc'],
                'to_tiploc': bluancr_loc['tiploc'],
                'from_time': prev_loc['dep_time'] or prev_loc['pass_time'],
                'to_time': bluancr_loc['arr_time'] or bluancr_loc['pass_time'],
                'train_uid': schedule['uid'],
                'train_identity': schedule['train_identity'],
                'runs_from': schedule['runs_from'],
                'runs_to': schedule['runs_to'],
                'days_run': schedule['days_run'],
                'filename': filename,
                'bluancr_platform': bluancr_loc['platform'],
                'bluancr_activity': bluancr_loc['activity']
            }
            segments_found.append(segment)

def main():
    """Main function to find and log BLUANCR segments"""
    
    print("Starting search for segments that start or end at BLUANCR...")
    start_time = datetime.now()
    
    segments = parse_cif_for_bluancr_segments()
    
    # Write results to file
    output_file = 'bluancr_segments.txt'
    with open(output_file, 'w') as f:
        f.write(f"BLUANCR SEGMENTS ANALYSIS\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total segments found: {len(segments)}\n")
        f.write("=" * 80 + "\n\n")
        
        # Group by type
        starts_at_bluancr = [s for s in segments if s['type'] == 'STARTS_AT_BLUANCR']
        ends_at_bluancr = [s for s in segments if s['type'] == 'ENDS_AT_BLUANCR']
        
        f.write(f"SEGMENTS STARTING AT BLUANCR: {len(starts_at_bluancr)}\n")
        f.write("-" * 50 + "\n")
        for segment in starts_at_bluancr:
            f.write(f"Train: {segment['train_identity']} (UID: {segment['train_uid']})\n")
            f.write(f"Route: {segment['from_tiploc']} -> {segment['to_tiploc']}\n")
            f.write(f"Times: {segment['from_time']} -> {segment['to_time']}\n")
            f.write(f"Runs: {segment['runs_from']} to {segment['runs_to']}\n")
            f.write(f"Days: {segment['days_run']}\n")
            f.write(f"Platform: {segment['bluancr_platform']}\n")
            f.write(f"Activity: {segment['bluancr_activity']}\n")
            f.write(f"File: {segment['filename']}\n")
            f.write("\n")
        
        f.write(f"\nSEGMENTS ENDING AT BLUANCR: {len(ends_at_bluancr)}\n")
        f.write("-" * 50 + "\n")
        for segment in ends_at_bluancr:
            f.write(f"Train: {segment['train_identity']} (UID: {segment['train_uid']})\n")
            f.write(f"Route: {segment['from_tiploc']} -> {segment['to_tiploc']}\n")
            f.write(f"Times: {segment['from_time']} -> {segment['to_time']}\n")
            f.write(f"Runs: {segment['runs_from']} to {segment['runs_to']}\n")
            f.write(f"Days: {segment['days_run']}\n")
            f.write(f"Platform: {segment['bluancr_platform']}\n")
            f.write(f"Activity: {segment['bluancr_activity']}\n")
            f.write(f"File: {segment['filename']}\n")
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
        f.write(f"Train identities: {', '.join(sorted(unique_trains))}\n")
    
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()
    
    print(f"\nCompleted! Found {len(segments)} segments involving BLUANCR")
    print(f"- {len(starts_at_bluancr)} segments starting at BLUANCR")
    print(f"- {len(ends_at_bluancr)} segments ending at BLUANCR")
    print(f"Processing time: {processing_time:.2f} seconds")
    print(f"Results written to: {output_file}")

if __name__ == "__main__":
    main()