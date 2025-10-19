import os
import logging
from app import app, db
from models import (
    # Legacy tables
    ParsedFile, BasicSchedule, ScheduleLocation, Association,
    # STP-specific tables
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation,
    AssociationLTP, AssociationSTPNew, AssociationSTPOverlay, AssociationSTPCancellation
)
from cif_parser import process_cif_files, CIFParser

# Set up logging
logger = logging.getLogger(__name__)

def reset_database():
    """Reset the database tables."""
    logger.info("Resetting database tables...")
    with app.app_context():
        # Use raw SQL DROP/TRUNCATE for legacy tables
        try:
            # Legacy tables
            db.session.execute(db.text("TRUNCATE TABLE schedule_locations CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE basic_schedules CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE associations CASCADE"))
            
            # STP-specific tables
            db.session.execute(db.text("TRUNCATE TABLE schedule_locations_ltp CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE schedule_locations_stp_new CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE schedule_locations_stp_overlay CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE schedule_locations_stp_cancellation CASCADE"))
            
            db.session.execute(db.text("TRUNCATE TABLE schedules_ltp CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE schedules_stp_new CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE schedules_stp_overlay CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE schedules_stp_cancellation CASCADE"))
            
            db.session.execute(db.text("TRUNCATE TABLE associations_ltp CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE associations_stp_new CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE associations_stp_overlay CASCADE"))
            db.session.execute(db.text("TRUNCATE TABLE associations_stp_cancellation CASCADE"))
            
            # Keep track of processed files
            db.session.execute(db.text("TRUNCATE TABLE parsed_files CASCADE"))
            
            db.session.commit()
            logger.info("Database tables truncated successfully")
        except Exception as e:
            logger.error(f"Error truncating tables: {str(e)}")
            
            # Fallback - use ORM to delete records if TRUNCATE fails
            try:
                logger.info("Falling back to ORM delete operations...")
                # Legacy tables
                db.session.query(ScheduleLocation).delete()
                db.session.query(BasicSchedule).delete()
                db.session.query(Association).delete()
                
                # STP-specific tables
                db.session.query(ScheduleLocationLTP).delete()
                db.session.query(ScheduleLocationSTPNew).delete()
                db.session.query(ScheduleLocationSTPOverlay).delete()
                db.session.query(ScheduleLocationSTPCancellation).delete()
                
                db.session.query(ScheduleLTP).delete()
                db.session.query(ScheduleSTPNew).delete()
                db.session.query(ScheduleSTPOverlay).delete()
                db.session.query(ScheduleSTPCancellation).delete()
                
                db.session.query(AssociationLTP).delete()
                db.session.query(AssociationSTPNew).delete()
                db.session.query(AssociationSTPOverlay).delete()
                db.session.query(AssociationSTPCancellation).delete()
                
                db.session.query(ParsedFile).delete()
                db.session.commit()
                logger.info("Database cleared using ORM delete operations")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error clearing database with ORM: {str(e)}")
                raise
    
    logger.info("Database reset complete.")
    return True

def reload_cif_files():
    """Process all CIF files in the import folder."""
    logger.info("Starting CIF file processing...")
    
    try:
        # Create a parser instance and process files
        parser = CIFParser()
        files_processed = parser.process_all_files()
        
        logger.info(f"Processed {files_processed} CIF files.")
        return {'success': True, 'files_processed': files_processed}
    except Exception as e:
        logger.error(f"Error processing CIF files: {str(e)}")
        return {'success': False, 'error': str(e)}

def reset_and_reload():
    """Reset database and reload CIF files."""
    logger.info("Starting database reset and reload operation...")
    
    try:
        # Step 1: Reset database
        reset_result = reset_database()
        if not reset_result:
            return {'success': False, 'error': 'Database reset failed'}
        
        # Step 2: Reload CIF files
        reload_result = reload_cif_files()
        
        if reload_result.get('success', False):
            return {
                'success': True, 
                'message': 'Database reset and CIF files reloaded successfully',
                'files_processed': reload_result.get('files_processed', 0)
            }
        else:
            return {
                'success': False,
                'error': f"CIF file processing failed: {reload_result.get('error', 'Unknown error')}"
            }
    except Exception as e:
        logger.error(f"Error in reset_and_reload: {str(e)}")
        return {'success': False, 'error': str(e)}

if __name__ == "__main__":
    reset_database()