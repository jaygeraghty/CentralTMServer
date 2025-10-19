import os
import sys
import subprocess
import logging
import time
import signal
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("runner")

# Keep track of processes
processes = []

def signal_handler(sig, frame):
    """Handle Ctrl+C and termination signals."""
    logger.info("Shutting down...")
    for proc in processes:
        if proc.poll() is None:  # If process is still running
            logger.info(f"Terminating process {proc.pid}")
            proc.terminate()
    sys.exit(0)

# Set up signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def start_web_interface():
    """Start the web interface on port 5001."""
    logger.info("Starting web interface...")
    web_proc = subprocess.Popen([
        sys.executable, 
        "web/web_app.py"
    ])
    processes.append(web_proc)
    logger.info(f"Web interface started with PID {web_proc.pid}")
    return web_proc

if __name__ == "__main__":
    # Start the web interface
    web_proc = start_web_interface()
    
    try:
        # Keep running until interrupted
        while all(proc.poll() is None for proc in processes):
            time.sleep(1)
            
        # Check if any process exited
        for proc in processes:
            if proc.poll() is not None:
                logger.error(f"Process {proc.pid} exited with code {proc.returncode}")
                
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Clean up
        signal_handler(None, None)