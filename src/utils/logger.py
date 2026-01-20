import logging
import sys
import os

def setup_logger(name='wits_automation', log_file=None):
    """Sets up a standardized logger with optional file output."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Simple way to clear existing handlers if log_file is provided (re-initialization)
    if log_file and logger.handlers:
        logger.handlers = []

    # Avoid duplicate handlers if not re-initializing
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        
        # Stream Handler
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        
        # File Handler
        if log_file:
            # Ensure folder exists
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    
    return logger
