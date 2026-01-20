#!/usr/bin/env python3
"""
Configuration Management Module

Handles loading, saving, and managing application configuration.
"""

import os
import json

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
        "stop": "ctrl+shift+f2"  # Hotkey to stop recording and clear queue
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
        "notebook_indicator_color": (60, 60, 255),  # RGB color for notebook mode (blue)
        "notebook_indicator_shape": "square",  # Shape for notebook mode indicator
        "notebook_pulse_pattern": "double"  # Different animation pattern for notebook
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
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
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
            with open(config_path, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            print(f"Created default config: {config_path}")
            return DEFAULT_CONFIG.copy()
        else:
            # If a custom config path is provided and it doesn't exist, fail
            raise FileNotFoundError(f"Configuration file not found: {config_path}")


def save_config(config, config_path="transcription_config.json"):
    """
    Save current configuration to file.
    
    Args:
        config: Configuration dictionary to save
        config_path: Path to configuration file
    """
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        print("Configuration saved")
    except Exception as e:
        print(f"Error saving config: {e}")