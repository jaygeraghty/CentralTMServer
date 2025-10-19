#!/usr/bin/env python3
"""
Simple script to fix the database transaction issues in the platform docker functionality.
This will reset the database session state to resolve the 'PendingRollbackError' issue.
"""
import logging
from sqlalchemy import text
from database import get_db

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def reset_db_connection():
    """Reset the database connection to fix any pending transaction issues."""
    db = get_db()
    try:
        # Try to rollback any pending transactions
        db.session.rollback()
        logger.info("Successfully rolled back pending transactions")
        
        # Test a simple query to make sure the connection is working
        result = db.session.execute(text("SELECT 1"))
        for row in result:
            logger.info(f"Test query result: {row[0]}")
        
        db.session.commit()
        logger.info("Database connection reset successfully")
        return True
    except Exception as e:
        logger.error(f"Error resetting database connection: {str(e)}")
        return False

if __name__ == "__main__":
    reset_db_connection()