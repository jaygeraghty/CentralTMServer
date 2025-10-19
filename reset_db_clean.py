"""
Reset database by dropping and recreating all tables.
This script completely clears the database and starts fresh.
"""

import os
import sys
from app import app, db
from models import (
    Base,
    BasicSchedule, ScheduleLocation, Association,
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation,
    AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation
)

def reset_database():
    """Drop and recreate all database tables"""
    print("Resetting database...")
    
    try:
        # Drop all tables
        Base.metadata.drop_all(bind=db.engine)
        print("All tables dropped.")
        
        # Recreate tables
        Base.metadata.create_all(bind=db.engine)
        print("All tables recreated.")
        
        print("Database reset complete.")
    except Exception as e:
        print(f"Error during database reset: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Use the Flask app context
    with app.app_context():
        reset_database()