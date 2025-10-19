#!/usr/bin/env python3
"""
Extract the complete CIF data for all 7 broken schedules.
"""

import gzip
import re

def extract_schedule(uid, train_id):
    """Extract complete schedule data for a specific UID and train ID."""
    schedule_data = []
    found_schedule = False
    
    with gzip.open('import/POINTA CIF.gz', 'rt') as f:
        for line in f:
            line = line.rstrip()
            
            # Look for the BS record with matching UID and train ID
            if line.startswith('BSN') and uid in line and train_id in line:
                found_schedule = True
                schedule_data.append(line)
                continue
            
            # If we found our schedule, collect all related records
            if found_schedule:
                # Collect BX, LO, LI, LT, CR records
                if line.startswith(('BX', 'LO', 'LI', 'LT', 'CR')):
                    schedule_data.append(line)
                    
                    # Stop at LT record ending with TF
                    if line.startswith('LT') and line.endswith('TF'):
                        break
                # Stop if we hit another BS record (different schedule)
                elif line.startswith('BS'):
                    break
    
    return schedule_data

# Extract all 7 broken schedules
broken_schedules = [
    ('P14772', '2P67'),
    ('P14773', '2P65'), 
    ('P14774', '2P63'),
    ('P14775', '2P61'),
    ('P14776', '2P59'),
    ('P14777', '2P57'),
    ('P14778', '2P55')
]

print("=" * 80)
print("COMPLETE CIF DATA FOR ALL 7 BROKEN SCHEDULES")
print("=" * 80)

for uid, train_id in broken_schedules:
    print(f"\n{'='*20} {uid} ({train_id}) {'='*20}")
    schedule_data = extract_schedule(uid, train_id)
    
    if schedule_data:
        for line in schedule_data:
            print(line)
    else:
        print(f"No data found for {uid} ({train_id})")
    
    print(f"{'='*60}")