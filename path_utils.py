#!/usr/bin/env python3
"""
Path Utilities Module

Provides utility functions for path validation and directory management.
"""

import os
import sys
import logging

def get_script_dir():
    """
    Get the directory where the current script is located.
    This works correctly for both regular Python execution and PyInstaller executables.

    Returns:
        str: Path to the script directory
    """
    # For PyInstaller executables, sys._MEIPASS contains the temp directory
    # For regular execution, use the directory of the current file
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as regular Python script
        return os.path.dirname(os.path.abspath(__file__))

def get_process_dir():
    """
    Get the directory where the current process is running from.
    This is different from script directory when running from .exe.

    Returns:
        str: Path to the process directory
    """
    return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else get_script_dir()

def resolve_relative_path(path, base_dir=None):
    """
    Resolve a path relative to the script directory or a specified base directory.

    Args:
        path (str): The path to resolve
        base_dir (str, optional): Base directory to resolve against. If None, uses script directory.

    Returns:
        str: Resolved absolute path
    """
    if not base_dir:
        base_dir = get_script_dir()

    # If path is already absolute, return it as-is
    if os.path.isabs(path):
        return path

    # Otherwise, resolve relative to base directory
    return os.path.join(base_dir, path)

def resolve_process_relative_path(path):
    """
    Resolve a path relative to the process directory (where the executable is running from).

    Args:
        path (str): The path to resolve

    Returns:
        str: Resolved absolute path
    """
    # If path is already absolute, return it as-is
    if os.path.isabs(path):
        return path

    # Otherwise, resolve relative to process directory
    return os.path.join(get_process_dir(), path)


def validate_and_prepare_path(file_path, logger=None):
    """
    Validate that a file path is writable and prepare the directory structure.
    
    Args:
        file_path: The full path to the file that will be written
        logger: Optional logger instance for logging messages
        
    Returns:
        tuple: (success: bool, message: str)
        
    Example:
        >>> success, message = validate_and_prepare_path("/path/to/config.json")
        >>> if not success:
        ...     print(f"Error: {message}")
    """
    if not file_path:
        message = "File path is empty or None"
        if logger:
            logger.error(message)
        return False, message
    
    # Extract directory from file path
    directory = os.path.dirname(file_path)
    
    if not directory:
        # File is in current directory, which should always be writable
        message = f"File path '{file_path}' is in current directory (should be writable)"
        if logger:
            logger.debug(message)
        return True, message
    
    # Check if directory exists
    if os.path.exists(directory):
        # Check if directory is writable
        if os.access(directory, os.W_OK):
            message = f"Directory '{directory}' exists and is writable"
            if logger:
                logger.debug(message)
            return True, message
        else:
            message = f"Directory '{directory}' exists but is not writable"
            if logger:
                logger.error(message)
            return False, message
    else:
        # Directory doesn't exist, try to create it
        try:
            os.makedirs(directory, exist_ok=True)
            message = f"Created directory '{directory}' for file operations"
            if logger:
                logger.info(message)
            return True, message
        except Exception as e:
            message = f"Failed to create directory '{directory}': {str(e)}"
            if logger:
                logger.error(message)
            return False, message


def validate_directory_path(directory_path, logger=None):
    """
    Validate that a directory path exists and is writable.
    
    Args:
        directory_path: The path to the directory
        logger: Optional logger instance for logging messages
        
    Returns:
        tuple: (success: bool, message: str)
    """
    if not directory_path:
        message = "Directory path is empty or None"
        if logger:
            logger.error(message)
        return False, message
    
    # Check if directory exists
    if os.path.exists(directory_path):
        # Check if directory is writable
        if os.access(directory_path, os.W_OK):
            message = f"Directory '{directory_path}' exists and is writable"
            if logger:
                logger.debug(message)
            return True, message
        else:
            message = f"Directory '{directory_path}' exists but is not writable"
            if logger:
                logger.error(message)
            return False, message
    else:
        # Directory doesn't exist, try to create it
        try:
            os.makedirs(directory_path, exist_ok=True)
            message = f"Created directory '{directory_path}'"
            if logger:
                logger.info(message)
            return True, message
        except Exception as e:
            message = f"Failed to create directory '{directory_path}': {str(e)}"
            if logger:
                logger.error(message)
            return False, message
