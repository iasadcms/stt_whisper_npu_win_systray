#!/usr/bin/env python3
"""
Logging Setup Module

Handles configuration and initialization of application logging.
"""

import logging
import os
import sys
from path_utils import validate_directory_path, get_script_dir, resolve_relative_path, resolve_process_relative_path


def setup_logging(config):
    """
    Setup logging configuration based on application settings.
    
    Args:
        config: Application configuration dictionary
        
    Returns:
        Configured logger instance
    """
    handlers = []
    
    # Always add console handler
    handlers.append(logging.StreamHandler())
    
    # Only add file handler if app logging is enabled
    if config["output"]["save_app_logs"]:
        # Use process directory for application logs (same folder as executable)
        log_dir = resolve_process_relative_path('')

        # Create the log directory if it doesn't exist
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create log directory: {e}")
            print("Application logging to console only (file logging disabled due to path issues)")
        else:
            log_file = os.path.join(log_dir, 'transcription_app.log')
            handlers.append(logging.FileHandler(log_file))
    
    debug_enabled = config.get("logging", {}).get("debug", False)
    level = logging.DEBUG if debug_enabled else logging.INFO
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=level,
        handlers=handlers
    )
    
    # Suppress PIL plugin import DEBUG logs
    pil_logger = logging.getLogger('PIL')
    pil_logger.setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    
    if config["output"]["save_app_logs"]:
        if 'log_file' in locals():
            logger.info(f"Application logging enabled. Log file: {log_file}")
        else:
            logger.info("Application logging to console only (file logging disabled due to path issues)")
    else:
        logger.info("Application logging to console only (file logging disabled)")
    
    return logger
