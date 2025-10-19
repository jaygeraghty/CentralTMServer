"""
Simple fix for the area of interest filtering in the CIF parser.
"""

import os
import shutil

# Make a backup of the original file
original_file = "cif_parser.py"
backup_file = "cif_parser.py.bak"

# Create backup if it doesn't exist
if not os.path.exists(backup_file):
    shutil.copy(original_file, backup_file)
    print(f"Created backup: {backup_file}")

# Replace the is_in_area_of_interest method to improve its effectiveness
with open(original_file, 'r') as f:
    content = f.read()

# Find and replace the is_in_area_of_interest method
old_method = """    def is_in_area_of_interest(self, locations):
        \"\"\"
        Check if any location in the schedule is in our area of interest.
        
        Args:
            locations: List of location dictionaries with tiploc codes
            
        Returns:
            bool: True if at least one location is in area of interest
        \"\"\"
        # Fast early return if no filtering needed
        if not self.area_of_interest:
            return True
            
        # Check each location
        for location in locations:
            tiploc = location.get('tiploc')
            if tiploc in self.area_of_interest:
                return True
                
        return False"""

new_method = """    def is_in_area_of_interest(self, locations):
        \"\"\"
        Check if any location in the schedule is in our area of interest.
        
        Args:
            locations: List of location dictionaries with tiploc codes
            
        Returns:
            bool: True if at least one location is in area of interest
        \"\"\"
        # Fast early return if no filtering needed
        if not self.area_of_interest:
            return True
            
        # Check each location
        for location in locations:
            # Handle different data types (dict or string)
            if isinstance(location, dict):
                tiploc = location.get('tiploc')
            else:
                tiploc = location
                
            if tiploc in self.area_of_interest:
                return True
                
        return False"""

# Replace the method
if old_method in content:
    new_content = content.replace(old_method, new_method)
    
    # Write the updated file
    with open(original_file, 'w') as f:
        f.write(new_content)
    
    print("Successfully updated is_in_area_of_interest method")
else:
    print("Could not find the is_in_area_of_interest method to replace")

print("To test this fix:")
print("1. Run 'python reset_db.py' to reset the database")
print("2. Run 'python run_cif_processing.py' to process CIF files with the fixed area filtering")