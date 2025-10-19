"""
Log Management System for Active Trains API
Provides file rotation and web interface for viewing logs
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import threading

class ActiveTrainsLogManager:
    def __init__(self, log_file='logs/active_trains.log', max_lines=7000, backup_count=3):
        self.log_file = log_file
        self.max_lines = max_lines
        self.backup_count = backup_count
        self.lock = threading.Lock()
        
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Set up rotating file handler
        self.setup_logger()
    
    def setup_logger(self):
        """Set up the logger with file rotation based on line count"""
        # Create custom formatter with timestamp
        formatter = logging.Formatter(
            '%(asctime)s BST - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Set up logging for both api_active_trains and active_trains modules
        loggers_to_setup = ['api_active_trains', 'active_trains']
        
        for logger_name in loggers_to_setup:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            logger.propagate = False  # Prevent duplicate logging
            
            # Remove ALL existing handlers and close them properly
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)
            
            # Create NEW file handler for this logger
            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=1024*1024*5,  # 5MB fallback
                backupCount=self.backup_count
            )
            file_handler.setFormatter(formatter)
            
            # Create NEW console handler for this logger
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            
            # Add new handlers
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
        
        # Keep reference to the main logger
        self.logger = logging.getLogger('api_active_trains')
        return self.logger
    
    def check_and_rotate_by_lines(self):
        """Check if log file exceeds line limit and rotate if needed"""
        with self.lock:
            if not os.path.exists(self.log_file):
                return
            
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    line_count = sum(1 for _ in f)
                
                if line_count > self.max_lines:
                    # Backup current log
                    backup_file = f"{self.log_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    os.rename(self.log_file, backup_file)
                    
                    # Create new log file with rotation message
                    with open(self.log_file, 'w', encoding='utf-8') as f:
                        f.write(f"# Log rotated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} BST\n")
                        f.write(f"# Previous log saved as: {os.path.basename(backup_file)}\n")
                    
                    # CRITICAL: Reinitialize all logger handlers to point to new file
                    self.setup_logger()
                    
                    # Log the rotation event to the NEW file
                    self.logger.info(f"Log rotated - exceeded {self.max_lines} lines, previous saved as {os.path.basename(backup_file)}")
                    
            except Exception as e:
                print(f"Error checking log rotation: {e}")
    
    def get_recent_logs(self, lines=500):
        """Get recent log entries for web display"""
        if not os.path.exists(self.log_file):
            return []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            
            # Return last N lines
            return all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        except Exception as e:
            return [f"Error reading log file: {e}"]
    
    def get_log_stats(self):
        """Get statistics about the log file"""
        if not os.path.exists(self.log_file):
            return {"exists": False}
        
        try:
            stat = os.stat(self.log_file)
            with open(self.log_file, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
            
            return {
                "exists": True,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "line_count": line_count,
                "max_lines": self.max_lines,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            return {"exists": True, "error": str(e)}

# Global instance
log_manager = ActiveTrainsLogManager()

def get_log_manager():
    """Get the global log manager instance"""
    return log_manager

def setup_api_logging():
    """Set up logging for the API module"""
    return log_manager.setup_logger()