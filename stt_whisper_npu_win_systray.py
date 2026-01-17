#!/usr/bin/env python3
"""
Seamless Voice-to-Text Transcription with VAD - System Tray Application

This script provides continuous, real-time speech-to-text transcription using:
- Voice Activity Detection (VAD) to intelligently segment speech
- Seamless audio capture with no gaps between transcriptions
- Windows System Tray integration with dynamic status icon
- Hotkey controls for toggling recording on/off
- Automatic typing of transcriptions into the active window
- Local Whisper model via OpenAI-compatible API

Key Features:
- Runs in system tray with visual recording indicators
- Configurable via JSON config file
- Microphone selection from tray menu
- Continuous audio buffering prevents loss of speech during processing
- Transcription logging to timestamped files
- Optional WAV file saving for debugging
- Filters common Whisper hallucinations
- PyAutoGUI integration for hands-free text input

Usage:
    python script.py                               # Run with default config
    python script.py --config my_config.json       # Use custom config
    python script.py --list-devices                # List audio devices

Default Hotkeys:
    Ctrl+Shift+F1 - Toggle recording on/off
    Ctrl+Shift+F2 - Stop and clear all pending transcriptions

Requirements:
    - PyAudio, OpenAI, PyAutoGUI, keyboard, pystray, Pillow, pygame, pywin32
    - Local Whisper model server (e.g., FasterWhisper, LocalAI)
"""

import pyaudio
import wave
import io
import array
import threading
import queue
import argparse
import logging
import datetime
import os
import time
import pyautogui
import keyboard
import json
import sys
from pathlib import Path
from openai import OpenAI
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw, ImageEnhance

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
        "chunk_size": 1024,  # Audio buffer size in frames
        "silence_threshold": 500,  # Volume threshold for voice detection (0-32767)
        "silence_duration": 1.0,  # Seconds of silence before ending a segment
        "max_buffer": 10.0  # Maximum seconds to record before forcing a send
    },
    "output": {
        "typing_enabled": True,  # Whether to type transcriptions into active window
        "typing_delay": 0.005,  # Delay between keystrokes in seconds (lower = faster)
        "log_dir": "transcription_logs",  # Directory for transcription text logs
        "save_transcription_logs": True,  # Whether to save transcription text logs
        "save_app_logs": False,  # Whether to save application debug logs
        "save_wav_files": False,  # Whether to save audio segments as WAV files
        "wav_dir": "audio_recordings"  # Directory for saved WAV files (if enabled)
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
        "animation_speed": 0.5  # Duration of start/stop animations in seconds
    }
}

class TranscriptionApp:
    def __init__(self, config_path=None, save_audio_only=False):
        self.config_path = config_path or "transcription_config.json"
        self.config = self.load_config()
        self.setup_logging()

        # State
        self.recording_enabled = threading.Event()
        if self.config["startup"]["start_recording"]:
            self.recording_enabled.set()

        self.running = True
        self.audio_queue = queue.Queue()
        self.current_device = self.config["audio"]["device_index"]
        self.indicator_thread = None
        self.stop_indicator = threading.Event()
        self.overlay_window = None
        self.save_audio_only = save_audio_only

        # Counter for audio chunk numbering
        self.audio_chunk_counter = 0
        self.audio_chunk_lock = threading.Lock()

        # Add pygame lock to prevent concurrent window operations
        self.pygame_lock = threading.Lock()        

        # Setup client
        self.client = OpenAI(
            base_url=self.config["api"]["base_url"],
            api_key=self.config["api"]["api_key"]
        )

        # Create directories
        if self.config["output"]["save_transcription_logs"]:
            os.makedirs(self.config["output"]["log_dir"], exist_ok=True)
        if self.config["output"]["save_wav_files"]:
            os.makedirs(self.config["output"]["wav_dir"], exist_ok=True)

        # Create temp audio directory for save-audio-only mode
        self.temp_audio_dir = "temp_audio"
        os.makedirs(self.temp_audio_dir, exist_ok=True)

        # Log file
        if self.config["output"]["save_transcription_logs"]:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            self.log_file = os.path.join(
                self.config["output"]["log_dir"],
                f"transcription_{timestamp}.log"
            )
        else:
            self.log_file = None

        # PyAudio setup
        self.p = pyaudio.PyAudio()
        self.stream = None

        # Tray icon
        self.icon = None

        # Load logo for tray icons
        logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
        try:
            self.logo = Image.open(logo_path).convert('RGBA').resize((64, 64), Image.Resampling.LANCZOS)
            gray_enhancer = ImageEnhance.Color(self.logo)
            self.gray_logo = gray_enhancer.enhance(0)
            self.logger.info("Loaded logo.png for tray icon")
        except Exception as e:
            self.logger.warning(f"Failed to load logo.png: {e}. Falling back to default icons.")
            self.logo = None
            self.gray_logo = None
        
    def load_config(self):
        """Load configuration from JSON file or create default."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
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
                self.logger.error(f"Error loading config: {e}. Using defaults.")
                return DEFAULT_CONFIG.copy()
        else:
            # Create default config file
            with open(self.config_path, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            self.logger.info(f"Created default config: {self.config_path}")
            return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            self.logger.info("Configuration saved")
        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
    
    def setup_logging(self):
        """Setup logging configuration."""
        handlers = []
        
        # Always add console handler
        handlers.append(logging.StreamHandler())
        
        # Only add file handler if app logging is enabled
        if self.config["output"]["save_app_logs"]:
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
        self.logger = logging.getLogger(__name__)
        
        if self.config["output"]["save_app_logs"]:
            self.logger.info(f"Application logging enabled. Log file: {log_file}")
        else:
            self.logger.info("Application logging to console only (file logging disabled)")
    
    def create_icon_image(self, recording=False):
        """Create system tray icon image using logo.png (gray when paused, color+red dot when recording)."""
        if self.logo is not None:
            img = self.logo.copy() if recording else self.gray_logo.copy()
            if recording:
                draw = ImageDraw.Draw(img)
                # Small red recording indicator top-right
                draw.ellipse([52, 4, 62, 14], fill=(255, 20, 20), outline=(139, 0, 0), width=1)
            return img
        else:
            # Fallback: original drawn icons
            image = Image.new('RGB', (64, 64), color=(255, 255, 255))
            draw = ImageDraw.Draw(image)
            
            if recording:
                draw.ellipse([8, 8, 56, 56], fill=(220, 20, 60), outline=(139, 0, 0), width=3)
                draw.ellipse([20, 20, 44, 44], fill=(255, 69, 0))
            else:
                draw.ellipse([8, 8, 56, 56], fill=(128, 128, 128), outline=(64, 64, 64), width=3)
                draw.rectangle([22, 20, 28, 44], fill=(255, 255, 255))
                draw.rectangle([36, 20, 42, 44], fill=(255, 255, 255))
            
            return image
    

    def start_animation(self):
        """Animate the overlay circle expanding from cursor when recording starts."""
        if not self.config["visual"]["animation_enabled"]:
            return
        
        # Prevent concurrent pygame operations
        if not self.pygame_lock.acquire(blocking=False):
            self.logger.warning("Animation already running, skipping")
            return
        
        try:
            import pygame
            import math
            
            # Ensure pygame is initialized
            if not pygame.get_init():
                pygame.init()
            
            size = self.config["visual"]["overlay_size"]
            window = pygame.display.set_mode((size, size), pygame.NOFRAME)
            
            # Make window transparent and topmost
            try:
                import win32gui
                import win32con
                hwnd = pygame.display.get_wm_info()['window']
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                extended_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, 
                                    extended_style | win32con.WS_EX_LAYERED | 
                                    win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW)
                win32gui.SetLayeredWindowAttributes(hwnd, 0, 0, win32con.LWA_COLORKEY)
            except:
                pass
            
            # Get cursor position
            x, y = pyautogui.position()
            offset = size // 2
            
            if hwnd:
                win32gui.SetWindowPos(hwnd, -1, x - offset, y - offset, 0, 0, 1)
            
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            color = self.config["visual"]["overlay_color"]
            alpha = self.config["visual"]["overlay_alpha"]
            animation_duration = self.config["visual"]["animation_speed"]
            
            frames = int(animation_duration * 60)
            clock = pygame.time.Clock()
            
            for frame in range(frames):
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        break
                
                progress = frame / frames
                ease_progress = 1 - math.pow(1 - progress, 3)
                
                surface.fill((0, 0, 0, 0))
                center = (size // 2, size // 2)
                max_radius = size // 2 - 2
                
                for ring in range(3):
                    ring_progress = ease_progress - (ring * 0.1)
                    if ring_progress > 0:
                        radius = int(max_radius * ring_progress)
                        ring_alpha = int(alpha * (1 - ring_progress))
                        color_with_alpha = (*color, ring_alpha)
                        pygame.draw.circle(surface, color_with_alpha, center, radius, 2)
                
                window.fill((0, 0, 0))
                window.blit(surface, (0, 0))
                pygame.display.flip()
                clock.tick(60)
            
        except Exception as e:
            self.logger.error(f"Error in start animation: {e}")
        finally:
            try:
                pygame.display.quit()
            except:
                pass
            self.pygame_lock.release()


    def stop_animation(self):
        """Animate the overlay circle collapsing to cursor when recording stops."""
        if not self.config["visual"]["animation_enabled"]:
            return
        
        # Prevent concurrent pygame operations
        if not self.pygame_lock.acquire(blocking=False):
            self.logger.warning("Animation already running, skipping")
            return
        
        try:
            import pygame
            import math
            
            # Ensure pygame is initialized
            if not pygame.get_init():
                pygame.init()
            
            size = self.config["visual"]["overlay_size"]
            window = pygame.display.set_mode((size, size), pygame.NOFRAME)
            
            # Make window transparent and topmost
            try:
                import win32gui
                import win32con
                hwnd = pygame.display.get_wm_info()['window']
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                extended_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, 
                                    extended_style | win32con.WS_EX_LAYERED | 
                                    win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW)
                win32gui.SetLayeredWindowAttributes(hwnd, 0, 0, win32con.LWA_COLORKEY)
            except:
                pass
            
            # Get cursor position
            x, y = pyautogui.position()
            offset = size // 2
            
            if hwnd:
                win32gui.SetWindowPos(hwnd, -1, x - offset, y - offset, 0, 0, 1)
            
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            color = self.config["visual"]["overlay_color"]
            alpha = self.config["visual"]["overlay_alpha"]
            animation_duration = self.config["visual"]["animation_speed"]
            
            frames = int(animation_duration * 60)
            clock = pygame.time.Clock()
            
            for frame in range(frames):
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        break
                
                progress = frame / frames
                ease_progress = math.pow(progress, 3)
                
                surface.fill((0, 0, 0, 0))
                center = (size // 2, size // 2)
                max_radius = size // 2 - 2
                
                for ring in range(3):
                    ring_progress = 1 - ease_progress + (ring * 0.1)
                    if ring_progress > 0 and ring_progress <= 1:
                        radius = int(max_radius * ring_progress)
                        ring_alpha = int(alpha * ring_progress)
                        color_with_alpha = (*color, ring_alpha)
                        if radius > 0:
                            pygame.draw.circle(surface, color_with_alpha, center, radius, 2)
                
                window.fill((0, 0, 0))
                window.blit(surface, (0, 0))
                pygame.display.flip()
                clock.tick(60)
            
        except Exception as e:
            self.logger.error(f"Error in stop animation: {e}")
        finally:
            try:
                pygame.display.quit()
            except:
                pass
            self.pygame_lock.release()


    def create_overlay_window(self):
        """Create a transparent overlay window using pygame."""
        try:
            import pygame
            
            # Initialize pygame
            pygame.init()
            
            size = self.config["visual"]["overlay_size"]
            
            # Create a window with no frame
            window = pygame.display.set_mode((size, size), pygame.NOFRAME)
            pygame.display.set_caption("Recording Indicator")
            
            # Set window to be always on top and transparent (Windows specific)
            try:
                import win32gui
                import win32con
                hwnd = pygame.display.get_wm_info()['window']
                
                # Make it topmost
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                     win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                
                # Make window layered and click-through
                extended_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, 
                                      extended_style | win32con.WS_EX_LAYERED | 
                                      win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW)
                
                # Set transparency - use colorkey for true transparency
                win32gui.SetLayeredWindowAttributes(hwnd, 0, 0, win32con.LWA_COLORKEY)
                
            except ImportError:
                self.logger.warning("win32gui not available, overlay may not be fully transparent")
            except Exception as e:
                self.logger.warning(f"Could not set window transparency: {e}")
            
            return window
            
        except Exception as e:
            self.logger.error(f"Error creating overlay: {e}")
            return None
    
    def pulse_overlay(self):
        """Animate the overlay with a smooth pulsing effect using pygame."""
        import math
        
        try:
            import pygame
        except ImportError:
            self.logger.error("pygame not installed. Install with: pip install pygame pywin32")
            return
        
        # Acquire lock to prevent conflicts with animations
        if not self.pygame_lock.acquire(blocking=True, timeout=2):
            self.logger.warning("Could not acquire pygame lock for overlay")
            return
        
        try:
            # Ensure pygame is initialized
            if not pygame.get_init():
                pygame.init()
            
            if not self.overlay_window:
                self.overlay_window = self.create_overlay_window()
                
            if not self.overlay_window:
                return
            
            window = self.overlay_window
            pulse_speed = self.config["visual"]["overlay_pulse_speed"]
            color_tuple = self.config["visual"]["overlay_color"]
            base_color = (color_tuple[0], color_tuple[1], color_tuple[2])
            alpha = self.config["visual"].get("overlay_alpha", 200)
            size = self.config["visual"]["overlay_size"]
            
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            
            t = 0
            clock = pygame.time.Clock()
            
            try:
                import win32gui
                hwnd = pygame.display.get_wm_info()['window']
            except:
                hwnd = None
            
            while not self.stop_indicator.is_set():
                # Handle pygame events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.stop_indicator.set()
                
                # Get cursor position and center window on cursor
                x, y = pyautogui.position()
                offset = size // 2
                
                if hwnd:
                    try:
                        win32gui.SetWindowPos(hwnd, -1, x - offset, y - offset, 0, 0, 1)
                    except:
                        pass
                
                pulse = (math.sin(t) + 1) / 2
                surface.fill((0, 0, 0, 0))
                center = (size // 2, size // 2)
                max_radius = size // 2 - 2
                
                for ring in range(3):
                    ring_phase = pulse + (ring * 0.33)
                    if ring_phase > 1:
                        ring_phase -= 1
                    
                    radius = int(max_radius * (0.4 + 0.6 * ring_phase))
                    ring_alpha = int(alpha * (1 - ring_phase * 0.7))
                    color_with_alpha = (*base_color, ring_alpha)
                    
                    thickness = max(1, 3 - ring)
                    pygame.draw.circle(surface, color_with_alpha, center, radius, thickness)
                
                window.fill((0, 0, 0))
                window.blit(surface, (0, 0))
                pygame.display.flip()
                
                t += (2 * math.pi) / (pulse_speed * 60)
                if t > 2 * math.pi:
                    t -= 2 * math.pi
                
                clock.tick(60)
                
        except Exception as e:
            self.logger.error(f"Error in pulse overlay: {e}")
        finally:
            try:
                pygame.display.quit()
            except:
                pass
            self.overlay_window = None
            self.pygame_lock.release()

    def start_recording_indicator(self):
        """Start visual indicator for recording."""
        if not self.config["visual"]["recording_indicator_enabled"]:
            return
        
        indicator_type = self.config["visual"]["recording_indicator_type"]
        
        if indicator_type == "overlay":
            if self.indicator_thread and self.indicator_thread.is_alive():
                return  # Already running
            
            self.stop_indicator.clear()
            self.indicator_thread = threading.Thread(target=self.pulse_overlay, daemon=True)
            self.indicator_thread.start()
    
    def stop_recording_indicator(self):
        """Stop visual indicator for recording."""
        self.stop_indicator.set()
        
        if self.overlay_window:
            try:
                pygame.display.quit()
            except:
                pass
            self.overlay_window = None
        
        if self.indicator_thread:
            # Add timeout to prevent infinite hang
            self.indicator_thread.join(timeout=2.0)
            if self.indicator_thread.is_alive():
                self.logger.warning("Indicator thread did not stop cleanly")
    
    def get_audio_devices(self):
        """Get list of available audio input devices."""
        devices = []
        for i in range(self.p.get_device_count()):
            dev = self.p.get_device_info_by_index(i)
            if dev['maxInputChannels'] > 0:
                devices.append((i, dev['name']))
        return devices
    
    def create_device_menu(self):
        """Create submenu for microphone selection."""
        devices = self.get_audio_devices()
        items = []
        for idx, name in devices:
            items.append(
                MenuItem(
                    f"{name}",
                    lambda _, i=idx: self.select_device(i),
                    checked=lambda item, i=idx: self.current_device == i
                )
            )
        return Menu(*items)
    
    def select_device(self, device_index):
        """Select a new microphone device."""
        self.logger.info(f"Switching to device {device_index}")
        self.current_device = device_index
        self.config["audio"]["device_index"] = device_index
        self.save_config()
        
        # Restart the recording stream
        if self.stream:
            self.restart_stream()
    
    def update_icon(self):
        """Update the tray icon to reflect recording state."""
        if self.icon:
            self.icon.icon = self.create_icon_image(self.recording_enabled.is_set())
    
    def toggle_recording(self, icon=None, item=None):
        """Toggle recording on/off."""
        if self.recording_enabled.is_set():
            # Stopping - wait for queue to empty, then stop indicator and play animation
            self.recording_enabled.clear()
            self.logger.info("Recording PAUSED - waiting for queue to finish...")
            
            # Wait for queue to empty in a separate thread so UI stays responsive
            def wait_and_stop():
                # Wait for all pending transcriptions with timeout to prevent infinite hang
                timeout = 10.0  # Maximum 10 seconds to wait for queue
                start_time = time.time()
                
                while not self.audio_queue.empty() and (time.time() - start_time) < timeout:
                    time.sleep(0.1)
                
                if time.time() - start_time >= timeout:
                    self.logger.warning("Queue wait timeout - forcing stop")
                
                # Now play the stop animation and stop indicator
                self.stop_recording_indicator()
                self.stop_animation()
                self.logger.info("Queue emptied - recording fully stopped")
            
            threading.Thread(target=wait_and_stop, daemon=True).start()
        else:
            # Starting - play expand animation then start indicator
            self.recording_enabled.set()
            self.logger.info("Recording RESUMED")
            self.start_animation()
            self.start_recording_indicator()
        
        self.update_icon()

    def stop_and_clear(self, icon=None, item=None):
        """Stop recording and clear queue."""
        self.recording_enabled.clear()
        self.logger.info("Recording STOPPED and cleared")
        
        # Clear queue immediately (don't wait)
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()  # Mark as done to prevent join() hanging
            except queue.Empty:
                break
        
        # Stop indicator and play collapse animation
        self.stop_recording_indicator()
        self.stop_animation()
        
        self.update_icon()
    
    def open_config(self, icon=None, item=None):
        """Open configuration file in default editor."""
        try:
            os.startfile(self.config_path)
        except Exception as e:
            self.logger.error(f"Error opening config: {e}")
    
    def open_logs(self, icon=None, item=None):
        """Open logs directory."""
        try:
            os.startfile(self.config["output"]["log_dir"])
        except Exception as e:
            self.logger.error(f"Error opening logs: {e}")

    def open_temp_audio(self, icon=None, item=None):
        """Open temp audio directory."""
        try:
            os.startfile(self.temp_audio_dir)
        except Exception as e:
            self.logger.error(f"Error opening temp audio directory: {e}")

    def quit_app(self, icon=None, item=None):
        """Quit the application."""
        self.logger.info("Shutting down...")
        self.running = False
        self.recording_enabled.clear()
        
        # Stop recording indicator
        self.stop_recording_indicator()
        
        # Stop stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.p:
            self.p.terminate()
        
        # Signal worker to stop
        self.audio_queue.put(None)
        
        # Stop icon
        if self.icon:
            self.icon.stop()
    
    def create_menu(self):
        """Create system tray menu."""
        return Menu(
            MenuItem(
                "Recording",
                self.toggle_recording,
                checked=lambda item: self.recording_enabled.is_set()
            ),
            MenuItem("Stop & Clear", self.stop_and_clear),
            Menu.SEPARATOR,
            MenuItem("Select Microphone", self.create_device_menu()),
            Menu.SEPARATOR,
            MenuItem("Open Config", self.open_config),
            MenuItem("Open Logs", self.open_logs),
            MenuItem("Open Temp Audio", self.open_temp_audio),
            Menu.SEPARATOR,
            MenuItem("Quit", self.quit_app)
        )
    
    def type_transcription(self, text):
        """
        Type transcribed text to the active window.
        
        Args:
            text: The transcribed text to type
        """
        if not self.config["output"]["typing_enabled"] or not text:
            return
        
        try:
            # Only flash cursor if recording is still enabled
            # (prevents flashing after user has paused)
            if self.recording_enabled.is_set() and self.config["visual"]["cursor_flash_enabled"]:
                flash_count = self.config["visual"]["cursor_flash_count"]
                flash_duration = self.config["visual"]["cursor_flash_duration"]
                
                for _ in range(flash_count):
                    # Get current cursor position
                    x, y = pyautogui.position()
                    
                    # Move cursor slightly to create a "flash" effect
                    pyautogui.moveRel(2, 2, duration=flash_duration)
                    pyautogui.moveRel(-2, -2, duration=flash_duration)
            
            # Type the actual text with configured delay between keystrokes
            pyautogui.write(text, interval=self.config["output"]["typing_delay"])
            # Add trailing space so next transcription doesn't stick to this one
            pyautogui.press('space')
        except Exception as e:
            self.logger.error(f"Error typing transcription: {e}")
    
    def save_wav(self, data, prefix="chunk"):
        """
        Save audio data to WAV file for debugging purposes.

        Args:
            data: Raw audio bytes to save
            prefix: Filename prefix (default: "chunk")
        """
        if not self.config["output"]["save_wav_files"]:
            return

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = os.path.join(
            self.config["output"]["wav_dir"],
            f"{prefix}_{timestamp}.wav"
        )

        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)  # Mono audio
            wf.setsampwidth(2)  # 16-bit audio (2 bytes)
            wf.setframerate(self.config["audio"]["rate"])
            wf.writeframes(data)

    def save_audio_chunk(self, data, chunk_number):
        """
        Save audio chunk to disk for later processing.

        Args:
            data: Raw audio bytes to save
            chunk_number: Sequential number for ordering
        """
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = os.path.join(
            self.temp_audio_dir,
            f"chunk_{chunk_number}_{timestamp}.wav"
        )

        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)  # Mono audio
            wf.setsampwidth(2)  # 16-bit audio (2 bytes)
            wf.setframerate(self.config["audio"]["rate"])
            wf.writeframes(data)

        self.logger.info(f"Saved audio chunk: {filename}")
    
    def api_worker(self):
        """Worker thread that processes audio chunks from the queue."""
        while self.running:
            data = self.audio_queue.get()
            if data is None:
                break

            # Handle save-audio-only mode
            if self.save_audio_only:
                with self.audio_chunk_lock:
                    self.audio_chunk_counter += 1
                    self.save_audio_chunk(data, self.audio_chunk_counter)
                self.audio_queue.task_done()
                continue

            # Save WAV if enabled
            self.save_wav(data)

            # Create WAV file in memory
            buffer = io.BytesIO()
            buffer.name = "speech.wav"
            with wave.open(buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.config["audio"]["rate"])
                wf.writeframes(data)
            buffer.seek(0)

            try:
                resp = self.client.audio.transcriptions.create(
                    model=self.config["api"]["model"],
                    file=buffer,
                    prompt=self.config["api"]["prompt"] if self.config["api"]["prompt"] else None
                )
                text = resp.text.strip()

                if text:
                    # Filter hallucinations
                    if text.lower() in self.config["filters"]["hallucinations"]:
                        self.logger.info(f"Filtered: {text}")
                    else:
                        self.logger.info(f"Transcription: {text}")

                        # Log to file if enabled
                        if self.log_file:
                            with open(self.log_file, 'a', encoding='utf-8') as f:
                                timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                f.write(f"[{timestamp}] {text}\n")

                        # Type to active window
                        self.type_transcription(text)

            except Exception as e:
                self.logger.error(f"API Error: {e}")

            self.audio_queue.task_done()
    
    def hotkey_monitor(self):
        """Monitor for hotkey presses."""
        self.logger.info(f"Hotkey monitoring started: {self.config['hotkeys']['toggle']} to toggle")
        
        keyboard.add_hotkey(self.config["hotkeys"]["toggle"], self.toggle_recording)
        keyboard.add_hotkey(self.config["hotkeys"]["stop"], self.stop_and_clear)
        
        while self.running:
            time.sleep(0.1)
    
    def restart_stream(self):
        """Restart the audio stream with new device."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.config["audio"]["rate"],
            input=True,
            input_device_index=self.current_device,
            frames_per_buffer=self.config["audio"]["chunk_size"]
        )
    
    def record_vad(self):
        """Continuous VAD recording with seamless audio capture."""
        self.restart_stream()
        
        self.logger.info(f"Listening on device {self.current_device}...")
        
        # Start worker threads
        threading.Thread(target=self.api_worker, daemon=True).start()
        threading.Thread(target=self.hotkey_monitor, daemon=True).start()
        
        frames = []
        silent_chunks = 0
        is_speaking = False
        
        silence_limit = int(
            self.config["audio"]["silence_duration"] * 
            self.config["audio"]["rate"] / 
            self.config["audio"]["chunk_size"]
        )
        buffer_limit = int(
            self.config["audio"]["max_buffer"] * 
            self.config["audio"]["rate"] / 
            self.config["audio"]["chunk_size"]
        )
        
        try:
            while self.running:
                try:
                    # Always read audio to prevent gaps
                    # Add timeout to prevent blocking indefinitely
                    if self.stream and self.stream.is_active():
                        data = self.stream.read(
                            self.config["audio"]["chunk_size"],
                            exception_on_overflow=False
                        )
                    else:
                        # Stream is not active, wait a bit and continue
                        time.sleep(0.01)
                        continue
                    
                    # Only process if recording is enabled
                    if self.recording_enabled.is_set():
                        frames.append(data)
                        
                        # Check volume level
                        as_ints = array.array('h', data)
                        max_val = max(abs(i) for i in as_ints) if as_ints else 0
                        
                        if max_val > self.config["audio"]["silence_threshold"]:
                            if not is_speaking:
                                is_speaking = True
                            silent_chunks = 0
                        else:
                            silent_chunks += 1
                        
                        # Check if we should send the accumulated audio
                        should_send = False
                        
                        if is_speaking and silent_chunks > silence_limit:
                            should_send = True
                        elif len(frames) > buffer_limit:
                            should_send = True
                        
                        if should_send and frames:
                            # Send audio to queue for processing
                            audio_data = b''.join(frames)
                            self.audio_queue.put(audio_data)
                            
                            # Reset for next segment
                            frames = []
                            is_speaking = False
                            silent_chunks = 0
                    else:
                        # If recording is disabled, clear any accumulated frames
                        if frames:
                            frames = []
                            is_speaking = False
                            silent_chunks = 0
                        time.sleep(0.01)
                
                except IOError as e:
                    # Handle stream read errors gracefully
                    self.logger.warning(f"Stream read error: {e}")
                    time.sleep(0.1)
                    continue
                        
        except Exception as e:
            self.logger.error(f"Recording error: {e}")
        finally:
            # Send any remaining audio
            if frames:
                self.audio_queue.put(b''.join(frames))

    def run(self):
        """Run the application with system tray icon."""
        # Create and start the icon
        self.icon = Icon(
            "TranscriptionApp",
            self.create_icon_image(self.recording_enabled.is_set()),
            "Voice Transcription",
            self.create_menu()
        )
        
        # Start recording in background thread
        recording_thread = threading.Thread(target=self.record_vad, daemon=True)
        recording_thread.start()
        
        # Run the icon (this blocks until quit)
        self.icon.run()

def list_audio_devices():
    """List all available audio input devices."""
    p = pyaudio.PyAudio()
    print("\nAvailable audio input devices:")
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev['maxInputChannels'] > 0:
            print(f"  Device {i}: {dev['name']}")
    p.terminate()

def main():
    parser = argparse.ArgumentParser(description="Voice Transcription System Tray App")
    parser.add_argument('--config', default='transcription_config.json',
                        help='Path to configuration file')
    parser.add_argument('--list-devices', action='store_true',
                        help='List available audio input devices')
    parser.add_argument('--save-audio-only', action='store_true',
                        help='Save audio chunks without processing with AI (for bulk processing later)')
    args = parser.parse_args()

    if args.list_devices:
        list_audio_devices()
        return

    # Create and run app
    app = TranscriptionApp(config_path=args.config, save_audio_only=args.save_audio_only)
    app.run()

if __name__ == "__main__":
    main()
