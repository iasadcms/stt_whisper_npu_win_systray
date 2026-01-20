#!/usr/bin/env python3
"""
Logging Setup Module

Handles configuration and initialization of application logging.
"""

import logging
import os


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
        # Ensure dist directory exists
        dist_dir = os.path.join(os.path.dirname(__file__), 'dist')
        os.makedirs(dist_dir, exist_ok=True)
        log_file = os.path.join(dist_dir, 'transcription_app.log')
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=handlers
    )
    logger = logging.getLogger(__name__)
    
    if config["output"]["save_app_logs"]:
        logger.info(f"Application logging enabled. Log file: {log_file}")
    else:
        logger.info("Application logging to console only (file logging disabled)")
    
    return logger