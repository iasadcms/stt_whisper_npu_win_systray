#!/usr/bin/env python3
"""
Configuration Management Module

Handles loading, saving, and managing application configuration.
"""

import os
import json
from path_utils import validate_and_prepare_path, resolve_relative_path

# Default configuration
DEFAULT_CONFIG = {
    "api": {
        "base_url": "http://127.0.0.1:52625/v1",  # OpenAI-compatible API endpoint
        "api_key": "flm",  # API key for authentication
        "model": "whisper-v3",  # Whisper model to use for transcription
        "prompt": ""  # Optional prompt to guide transcription style/vocabulary
    },
    "audio": {
        "device_index": 0,  # Audio input device ID (use --list-devices to see options)
        "rate": 16000,  # Sample rate in Hz (16000 is optimal for Whisper)
        "chunk_size": 2048,  # Audio buffer size in frames
        "silence_threshold": 700,  # Volume threshold for voice detection (0-32767)
        "silence_duration": 1.5,  # Seconds of silence before ending a segment
        "max_buffer": 40.0  # Maximum seconds to record before forcing a send
    },
    "output": {
        "typing_enabled": True,  # Whether to type transcriptions into active window
        "typing_delay": 0.005,  # Delay between keystrokes in seconds (lower = faster)
        "log_dir": "transcription_logs",  # Directory for transcription text logs
        "save_transcription_logs": True,  # Whether to save transcription text logs
        "save_app_logs": False,  # Whether to save application debug logs
        "save_wav_files": False,  # Whether to save audio segments as WAV files
        "wav_dir": "audio_recordings",  # Directory for saved WAV files (if enabled)
        "log_transcription_text": True,  # Whether to include transcription text in logs
        "log_processing_time": True,  # Whether to log processing time for each sample
        "log_translation_errors": True  # Whether to log detailed translation endpoint errors
    },
    "hotkeys": {
        "toggle": "ctrl+shift+f1",  # Hotkey to toggle recording on/off
        "stop": "ctrl+shift+f2",  # Hotkey to stop recording and clear queue
        "submit": "ctrl+shift+`"
    },
    "filters": {
        # Common Whisper hallucinations to filter out (won't be typed or logged)
        "hallucinations": ["thank you.", "thank you", "stop", "bye.", "thanks for watching."]
    },
    "startup": {
        "start_recording": False,  # Whether recording is enabled on app startup
        "minimize_to_tray": True  # Whether to minimize to system tray on startup
    },
    "notebook": {
        "enabled": False,                    # Whether notebook mode is active
        "file_path": "notebook.txt",        # Path to notebook file
        "view_on_startup": False            # Whether to open notebook when starting
    },
    "visual": {
        "cursor_flash_enabled": True,  # Flash cursor before typing transcription
        "cursor_flash_count": 3,  # Number of flashes
        "cursor_flash_duration": 0.1,  # Duration of each flash in seconds
        "recording_indicator_enabled": True,  # Show visual indicator when recording
        "recording_indicator_type": "overlay",  # "overlay" or "none"
        "overlay_pulse_speed": 2.0,  # Seconds per complete pulse cycle (lower = faster)
        "overlay_size": 60,  # Diameter of overlay circle in pixels
        "overlay_color": (255, 60, 60),  # RGB color for overlay (red by default)
        "overlay_alpha": 200,  # Transparency level 0-255 (255 = opaque, 0 = invisible)
        "animation_enabled": True,  # Enable start/stop animations
        "animation_speed": 0.5,  # Duration of start/stop animations in seconds
        "notebook_indicator_color": (100, 200, 255),  # RGB color for notebook mode (bright cyan-blue)
        "notebook_indicator_shape": "square",  # Shape for notebook mode indicator
        "notebook_pulse_pattern": "double",  # Different animation pattern for notebook
        "buffer_draining_color": (255, 255, 0),  # RGB color for buffer draining state (yellow)
        "endpoint_unavailable_color": (255, 165, 0),  # RGB color for endpoint unavailable state (orange)
        "idle_icon_color": (0, 255, 0),  # RGB color for idle tray icon (green)
        "cursor_indicator_type": "speaking",  # "speaking" for radiating sound waves
        "notebook_indicator_type": "radiating_lines"  # "radiating_lines" for inward lines
    },
    "logging": {
        "debug": False  # Debug logging enabled/disabled
    }
}


def load_config(config_path="transcription_config.json"):
    """
    Load configuration from JSON file or create default.

    Args:
        config_path: Path to configuration file

    Returns:
        Dictionary containing merged configuration
    """
    # Resolve config path relative to script directory
    resolved_config_path = resolve_relative_path(config_path)

    if os.path.exists(resolved_config_path):
        try:
            with open(resolved_config_path, 'r') as f:
                user_config = json.load(f)
            # Merge with defaults (user config overrides defaults)
            config = DEFAULT_CONFIG.copy()
            for section in user_config:
                if section in config:
                    config[section].update(user_config[section])
                else:
                    config[section] = user_config[section]
            return config
        except Exception as e:
            print(f"Error loading config: {e}. Using defaults.")
            return DEFAULT_CONFIG.copy()
    else:
        # Only create default config file if using the default path
        if config_path == "transcription_config.json":
            with open(resolved_config_path, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            print(f"Created default config: {resolved_config_path}")
            return DEFAULT_CONFIG.copy()
        else:
            # If a custom config path is provided and it doesn't exist, fail
            raise FileNotFoundError(f"Configuration file not found: {resolved_config_path}")


def save_config(config, config_path="transcription_config.json", logger=None):
    """
    Save current configuration to file.
    
    Args:
        config: Configuration dictionary to save
        config_path: Path to configuration file
        logger: Optional logger instance for logging messages
    """
    # Validate path before attempting to write
    path_valid, validation_message = validate_and_prepare_path(config_path, logger)
    
    if not path_valid:
        error_msg = f"Cannot save configuration: {validation_message}"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        return False
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        success_msg = "Configuration saved successfully"
        if logger:
            logger.info(success_msg)
        else:
            print(success_msg)
        return True
    except Exception as e:
        error_msg = f"Error saving config: {e}"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        return False
