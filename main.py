#!/usr/bin/env python3
"""
Main Application Module

Orchestrates the transcription application and handles main execution flow.
"""

import argparse
import threading
import queue
import time
import os
import sys
from pynput import keyboard as pynput_keyboard
from pystray import Icon
from PIL import ImageDraw

# Import our modules
from config import load_config, save_config
from logging_setup import setup_logging
from ui import load_logo, create_icon_image, VisualIndicators, TrayMenu
from audio import AudioProcessor, list_audio_devices
from transcription import TranscriptionHandler, api_worker


class TranscriptionApp:
    """
    Main application class that orchestrates all components.
    """
    
    def __init__(self, config_path=None, save_audio_only=False):
        self.config_path = config_path or "transcription_config.json"
        self.config = load_config(self.config_path)
        self.logger = setup_logging(self.config)
        
        # State
        self.recording_enabled = threading.Event()
        if self.config["startup"]["start_recording"]:
            self.recording_enabled.set()
        
        self.running = threading.Event()
        self.running.set()
        self.audio_queue = queue.Queue()
        self.current_device = self.config["audio"]["device_index"]
        self.save_audio_only = save_audio_only
        
        # Counter for audio chunk numbering (using list to allow modification in threads)
        self.audio_chunk_counter = [0]
        self.audio_chunk_lock = threading.Lock()
        
        # Icon update throttling
        self.icon_update_lock = threading.Lock()
        self.last_icon_state = None
        self.icon_update_pending = False
        
        # Initialize components
        self.audio_processor = AudioProcessor(
            self.config,
            self.audio_queue,
            self.recording_enabled,
            self.logger
        )
        
        self.transcription_handler = TranscriptionHandler(self.config, self.logger)
        
        # Notebook state
        self.notebook_mode = self.config["notebook"]["enabled"]
        
        # Load UI components
        self.logo, self.gray_logo = load_logo()
        self.visual_indicators = VisualIndicators(self.config)
        self.visual_indicators.set_notebook_mode(self.notebook_mode)
        self.tray_menu = TrayMenu(self)
        
        # Tray icon
        self.icon = None
        self.glow_phase = 0.0
        self.glow_direction = 0.1111  # Step size for 10 shades over fade (1.0 / 9 steps)
        self.glow_timer = None
        self.glow_active = False
        self.glow_pause_counter = 0  # Counter for pause duration
        self.glow_pause_frames = 10  # 10 frames * 25ms = 250ms pause
    
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
            os.startfile(self.audio_processor.temp_audio_dir)
        except Exception as e:
            self.logger.error(f"Error opening temp audio directory: {e}")

    def open_transcription_logs(self, icon=None, item=None):
        """Open transcription logs directory."""
        try:
            os.startfile(self.config["output"]["log_dir"])
        except Exception as e:
            self.logger.error(f"Error opening transcription logs: {e}")

    def open_app_logs(self, icon=None, item=None):
        """Open application logs directory."""
        try:
            # Application logs are stored in the dist directory
            dist_dir = os.path.join(os.path.dirname(__file__), 'dist')
            os.startfile(dist_dir)
        except Exception as e:
            self.logger.error(f"Error opening application logs: {e}")
    
    def set_notebook_mode(self, enabled, icon=None, item=None):
        """Set notebook mode on/off."""
        self.notebook_mode = enabled
        self.transcription_handler.set_notebook_mode(enabled)
        self.visual_indicators.set_notebook_mode(enabled)
        self.logger.info(f"Notebook mode {'enabled' if enabled else 'disabled'}")
    
    def open_notebook(self, icon=None, item=None):
        """Open notebook file in default editor."""
        self.transcription_handler.open_notebook()
    
    def clear_notebook(self, icon=None, item=None):
        """Clear notebook file content."""
        self.transcription_handler.clear_notebook()
    
    def set_notebook_path_dialog(self, icon=None, item=None):
        """Show dialog to set notebook path."""
        # This functionality has been removed from the UI
        # Notebook path should be configured in the config file
        self.logger.warning("Notebook path configuration is now handled through the config file only")

    def show_help(self, icon=None, item=None):
        """Show help and instructions dialog."""
        help_message = """Voice Transcription App - Help & Instructions

HOTKEYS:
- Toggle Recording: {}
- Stop & Clear: {}
- Submit Current: {}

CONFIGURATION:
Edit transcription_config.json to customize settings. For example, Notebook path, Hotkeys, API endpoints, ...

USAGE TIPS:
- When recording is paused, the queue continues processing. The mouse cursor will indicate processing is occuring.
- Use "Stop Recording and Clear Queue" to immediately stop recording, and clear pending items.
- Audio files are saved in temp_audio/ directory
- Logs are stored in transcription_logs/ directory

TROUBLESHOOTING:
- If API endpoint is unavailable, transcriptions will be logged as errors
- Queue items are processed in order and logged appropriately"""

        # Format with actual hotkey values from config
        formatted_help = help_message.format(
            self.config['hotkeys']['toggle'],
            self.config['hotkeys']['stop'],
            self.config['hotkeys'].get('submit', 'ctrl+shift+f3')
        )

        # Show native Windows MsgBox using VBScript temp file (pure Windows, reliable)
        try:
            import tempfile
            import os
            
            # Escape each line for VBS, join with vbCrLf to avoid length limits
            lines = formatted_help.split('\n')
            vbs_lines = ' & vbCrLf & '.join(f'"{line.replace(chr(34), chr(34)*2)}"' for line in lines)
            vbs_content = f'MsgBox {vbs_lines}, vbInformation + vbOKOnly, "Speech-to-Text - Help & Instructions"'
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.vbs', delete=False, encoding='utf-8') as f:
                f.write(vbs_content)
            
            import subprocess
            subprocess.Popen(f'start /B "" wscript.exe "{f.name}"', shell=True)
            self.logger.info("Native VBS MsgBox launched successfully")
        except Exception as e:
            self.logger.error(f"Error showing help dialog: {e}")
            print(formatted_help)

    def start_endpoint_monitor(self):
        """Start a background thread to monitor API endpoint health."""
        def endpoint_monitor_loop():
            import time
            import requests

            # Only monitor if we're not in save-audio-only mode
            if self.save_audio_only:
                return

            while self.running.is_set():
                try:
                    # Simple health check - try to connect to the endpoint
                    test_url = f"{self.config['api']['base_url']}/models"
                    response = requests.get(
                        test_url,
                        headers={"Authorization": f"Bearer {self.config['api']['api_key']}"},
                        timeout=5
                    )

                    if response.status_code == 200:
                        if not hasattr(self, 'endpoint_healthy') or not self.endpoint_healthy:
                            self.endpoint_healthy = True
                            self.logger.info("API endpoint health restored")
                            # Update visual indicator to show healthy state
                            self.visual_indicators.set_endpoint_status(True)
                    else:
                        if not hasattr(self, 'endpoint_healthy') or self.endpoint_healthy:
                            self.endpoint_healthy = False
                            self.logger.warning(f"API endpoint health check failed: HTTP {response.status_code}")
                            self.visual_indicators.set_endpoint_status(False)

                except Exception as e:
                    if not hasattr(self, 'endpoint_healthy') or self.endpoint_healthy:
                        self.endpoint_healthy = False
                        self.logger.warning(f"API endpoint health check failed: {e}")
                        self.visual_indicators.set_endpoint_status(False)

                # Check every 30 seconds
                time.sleep(30)

        # Start the monitor thread
        monitor_thread = threading.Thread(target=endpoint_monitor_loop, daemon=True)
        monitor_thread.start()
    
    def update_icon(self):
        """Update the tray icon to reflect recording state (throttled)."""
        if not self.icon:
            return
            
        current_state = self.recording_enabled.is_set()
        
        # Only update if state actually changed
        with self.icon_update_lock:
            if self.last_icon_state == current_state:
                return
            self.last_icon_state = current_state
        
        # Schedule icon update in a separate thread to avoid blocking
        def delayed_update():
            try:
                self.icon.icon = create_icon_image(
                    self.logo,
                    self.gray_logo,
                    current_state
                )
            except Exception as e:
                # Silently ignore icon update errors - they're not critical
                pass
        
        threading.Thread(target=delayed_update, daemon=True).start()

    def update_glowing_icon(self):
        """Update the tray icon with glowing effect for recording state."""
        if self.icon and self.recording_enabled.is_set():
            # Handle pause at peak and trough
            if self.glow_pause_counter > 0:
                self.glow_pause_counter -= 1
                return  # Skip color update during pause

            # Update glow phase for next frame
            self.glow_phase += self.glow_direction
            if self.glow_phase >= 1.0:
                self.glow_phase = 1.0
                self.glow_direction = -0.1111  # Reverse direction with same step size
                self.glow_pause_counter = self.glow_pause_frames  # Start pause at peak
            elif self.glow_phase <= 0.0:
                self.glow_phase = 0.0
                self.glow_direction = 0.1111  # Forward direction with same step size
                self.glow_pause_counter = self.glow_pause_frames  # Start pause at trough

            # Update icon on every frame for maximum smoothness
            try:
                # Import here to avoid circular imports
                from ui.logo import create_built_in_microphone_icon

                # Create icon with current glow phase
                glow_icon = create_built_in_microphone_icon(recording=True, glow_phase=self.glow_phase)

                # Add recording indicator
                draw = ImageDraw.Draw(glow_icon)
                draw.ellipse([52, 4, 62, 14], fill=(255, 50, 50), outline=(200, 0, 0), width=1)

                self.icon.icon = glow_icon
            except Exception as e:
                # If icon update fails, just continue - don't crash the glow effect
                pass

    def start_glow_effect(self):
        """Start the glowing icon effect."""
        if not self.glow_active and self.recording_enabled.is_set():
            self.glow_active = True
            self.glow_phase = 0.0
            self.glow_direction = 0.05  # Adjusted step size for 10 FPS (1.0 / 20 frames)

            # Start timer to update icon periodically
            def glow_update_loop():
                while self.glow_active and self.recording_enabled.is_set() and self.running.is_set():
                    self.update_glowing_icon()
                    time.sleep(0.15)  # Increased to 150ms for maximum keyboard compatibility

            self.glow_timer = threading.Thread(target=glow_update_loop, daemon=True)
            self.glow_timer.start()

    def stop_glow_effect(self):
        """Stop the glowing icon effect."""
        self.glow_active = False
        if self.glow_timer:
            self.glow_timer.join(timeout=0.5)  # Give it a chance to stop
            self.glow_timer = None
        # Reset to normal recording icon
        if self.recording_enabled.is_set():
            self.update_icon()
    
    def toggle_recording(self, icon=None, item=None):
        """Toggle recording on/off."""
        if self.recording_enabled.is_set():
            # Stopping - force flush any accumulated audio first
            self.audio_processor.force_flush_audio()
            # Then wait for queue to empty, then stop indicator and play animation
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
                self.visual_indicators.stop_recording_indicator()
                self.visual_indicators.stop_animation()
                self.logger.info("Queue emptied - recording fully stopped")
                
                # Update icon after animations complete
                self.update_icon()

            threading.Thread(target=wait_and_stop, daemon=True).start()
        else:
            # Starting - play expand animation then start indicator
            self.recording_enabled.set()
            self.logger.info("Recording RESUMED")
            self.visual_indicators.start_animation()
            self.visual_indicators.start_recording_indicator()
            self.start_glow_effect()
            self.update_icon()

        # Update menu to reflect new recording state
        if self.icon:
            def update_menu():
                try:
                    self.icon.menu = self.tray_menu.create_menu()
                    self.icon.update_menu()
                except Exception as e:
                    # Ignore menu update errors
                    pass
            threading.Thread(target=update_menu, daemon=True).start()
    
    def submit_recording(self, icon=None, item=None):
        """Force immediate processing of current recording buffer."""
        if self.recording_enabled.is_set():
            self.audio_processor.force_flush_audio()
            self.logger.info("Submit hotkey pressed - forcing immediate processing of current recording")
        else:
            self.logger.info("Submit hotkey pressed but recording is not enabled")
    
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
        self.visual_indicators.stop_recording_indicator()
        self.visual_indicators.stop_animation()
        self.stop_glow_effect()

        self.update_icon()
        
        # Update menu to reflect new recording state
        if self.icon:
            def update_menu():
                try:
                    self.icon.menu = self.tray_menu.create_menu()
                    self.icon.update_menu()
                except Exception as e:
                    # Ignore menu update errors
                    pass
            threading.Thread(target=update_menu, daemon=True).start()
    
    def hard_stop(self, icon=None, item=None):
        """Hard stop - cancel everything, delete recordings, send nothing."""
        self.logger.info("HARD STOP - Canceling all operations")
        
        # Immediately stop recording
        self.recording_enabled.clear()
        
        # Signal audio processor to hard stop
        self.audio_processor.hard_stop()
        
        # Clear the queue completely
        cleared_count = 0
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
                cleared_count += 1
            except queue.Empty:
                break
        
        self.logger.info(f"Hard stop: Cleared {cleared_count} pending items from queue")
        
        # Stop all visual indicators immediately
        self.visual_indicators.stop_recording_indicator()
        self.visual_indicators.stop_animation()
        self.stop_glow_effect()
        
        # Update icon
        self.update_icon()
        
        # Update menu
        if self.icon:
            def update_menu():
                try:
                    self.icon.menu = self.tray_menu.create_menu()
                    self.icon.update_menu()
                except Exception as e:
                    pass
            threading.Thread(target=update_menu, daemon=True).start()
    
    def reload_config(self, icon=None, item=None):
        """Reload configuration from file."""
        self.logger.info("Reloading configuration...")
        
        # Stop recording and clear queue
        self.stop_and_clear()
        
        # Reload configuration
        try:
            self.config = load_config(self.config_path)
            self.logger.info("Configuration reloaded successfully")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")
    
    def quit_app(self, icon=None, item=None):
        """Quit the application."""
        self.logger.info("Shutting down...")
        self.running.clear()
        self.recording_enabled.clear()
        
        # Stop recording indicator
        self.visual_indicators.stop_recording_indicator()
        
        # Stop audio processing
        self.audio_processor.cleanup()
        
        # Signal worker to stop
        self.audio_queue.put(None)
        
        # Stop icon
        if self.icon:
            self.icon.stop()
    
    def hotkey_monitor(self):
        """Monitor for hotkey presses using Windows native hotkey API."""
        import ctypes
        from ctypes import wintypes
        
        # Check if submit hotkey exists in config, if not use a default
        submit_hotkey = self.config['hotkeys'].get('submit', 'ctrl+shift+f3')

        self.logger.info(f"Hotkey monitoring started: {self.config['hotkeys']['toggle']} to toggle, "
                        f"{self.config['hotkeys']['stop']} to stop, {submit_hotkey} to submit")

        # Windows API constants
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN = 0x0008
        WM_HOTKEY = 0x0312
        
        # Virtual key codes for function keys
        VK_F1 = 0x70
        VK_F2 = 0x71
        VK_F3 = 0x72
        VK_F4 = 0x73
        VK_F5 = 0x74
        VK_F6 = 0x75
        VK_F7 = 0x76
        VK_F8 = 0x77
        VK_F9 = 0x78
        VK_F10 = 0x79
        VK_F11 = 0x7A
        VK_F12 = 0x7B
        VK_TILDE = 0xC0  # Backtick/tilde key
        
        def parse_hotkey(hotkey_str):
            """Parse hotkey string into Windows modifier and virtual key code."""
            parts = [part.strip().lower() for part in hotkey_str.split('+')]
            modifiers = 0
            vk_code = 0
            
            for part in parts:
                if part == 'ctrl':
                    modifiers |= MOD_CONTROL
                elif part == 'shift':
                    modifiers |= MOD_SHIFT
                elif part == 'alt':
                    modifiers |= MOD_ALT
                elif part == 'win':
                    modifiers |= MOD_WIN
                elif part == 'f1':
                    vk_code = VK_F1
                elif part == 'f2':
                    vk_code = VK_F2
                elif part == 'f3':
                    vk_code = VK_F3
                elif part == 'f4':
                    vk_code = VK_F4
                elif part == 'f5':
                    vk_code = VK_F5
                elif part == 'f6':
                    vk_code = VK_F6
                elif part == 'f7':
                    vk_code = VK_F7
                elif part == 'f8':
                    vk_code = VK_F8
                elif part == 'f9':
                    vk_code = VK_F9
                elif part == 'f10':
                    vk_code = VK_F10
                elif part == 'f11':
                    vk_code = VK_F11
                elif part == 'f12':
                    vk_code = VK_F12
                elif part in ['`', 'backtick', 'tilde']:
                    vk_code = VK_TILDE
                elif len(part) == 1:
                    # Single character - convert to virtual key code
                    vk_code = ord(part.upper())
            
            return modifiers, vk_code
        
        # Parse hotkeys
        toggle_mod, toggle_vk = parse_hotkey(self.config['hotkeys']['toggle'])
        stop_mod, stop_vk = parse_hotkey(self.config['hotkeys']['stop'])
        submit_mod, submit_vk = parse_hotkey(submit_hotkey)
        
        # Hotkey IDs
        HOTKEY_TOGGLE = 1
        HOTKEY_STOP = 2
        HOTKEY_SUBMIT = 3
        
        # Windows API functions
        user32 = ctypes.windll.user32
        
        # Register hotkeys
        try:
            if not user32.RegisterHotKey(None, HOTKEY_TOGGLE, toggle_mod, toggle_vk):
                self.logger.error(f"Failed to register toggle hotkey: {self.config['hotkeys']['toggle']}")
            else:
                self.logger.info(f"Registered toggle hotkey: {self.config['hotkeys']['toggle']}")
            
            if not user32.RegisterHotKey(None, HOTKEY_STOP, stop_mod, stop_vk):
                self.logger.error(f"Failed to register stop hotkey: {self.config['hotkeys']['stop']}")
            else:
                self.logger.info(f"Registered stop hotkey: {self.config['hotkeys']['stop']}")
            
            if not user32.RegisterHotKey(None, HOTKEY_SUBMIT, submit_mod, submit_vk):
                self.logger.error(f"Failed to register submit hotkey: {submit_hotkey}")
            else:
                self.logger.info(f"Registered submit hotkey: {submit_hotkey}")
            
            # Message loop to process hotkey events
            msg = wintypes.MSG()
            while self.running.is_set():
                # Non-blocking peek at message queue
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE = 1
                    if msg.message == WM_HOTKEY:
                        hotkey_id = msg.wParam
                        
                        if hotkey_id == HOTKEY_TOGGLE:
                            self.logger.debug("Toggle hotkey pressed")
                            threading.Thread(target=self.toggle_recording, daemon=True).start()
                        elif hotkey_id == HOTKEY_STOP:
                            self.logger.debug("Stop hotkey pressed")
                            threading.Thread(target=self.hard_stop, daemon=True).start()
                        elif hotkey_id == HOTKEY_SUBMIT:
                            self.logger.debug("Submit hotkey pressed")
                            threading.Thread(target=self.submit_recording, daemon=True).start()
                    
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    # No messages, sleep briefly to avoid CPU spinning
                    time.sleep(0.01)
        
        except Exception as e:
            self.logger.error(f"Hotkey monitor error: {e}")
        
        finally:
            # Unregister hotkeys
            try:
                user32.UnregisterHotKey(None, HOTKEY_TOGGLE)
                user32.UnregisterHotKey(None, HOTKEY_STOP)
                user32.UnregisterHotKey(None, HOTKEY_SUBMIT)
                self.logger.info("Hotkeys unregistered")
            except:
                pass
    
    def run(self):
        """Run the application with system tray icon."""
        # Create and start the icon
        self.icon = Icon(
            "TranscriptionApp",
            create_icon_image(self.logo, self.gray_logo, self.recording_enabled.is_set()),
            "Voice Transcription",
            self.tray_menu.create_menu()
        )

        # Start worker threads
        worker_thread = threading.Thread(
            target=api_worker,
            args=(
                self.audio_queue,
                self.transcription_handler,
                self.running,
                self.save_audio_only,
                self.audio_chunk_counter,
                self.audio_chunk_lock
            ),
            daemon=True
        )
        worker_thread.start()

        # Start hotkey monitor
        hotkey_thread = threading.Thread(target=self.hotkey_monitor, daemon=True)
        hotkey_thread.start()

        # Start endpoint health monitor
        self.start_endpoint_monitor()

        # Start recording in background thread
        recording_thread = threading.Thread(
            target=self.audio_processor.record_vad,
            args=(self.running, self.save_audio_only),
            daemon=True
        )
        recording_thread.start()

        # Run the icon (this blocks until quit)
        self.icon.run()


def ensure_console():
    """
    Attach to parent console if launched from cmd/PowerShell.
    Do NOT create a new console unless explicitly desired.
    """
    if os.name != "nt":
        return

    import ctypes
    kernel32 = ctypes.windll.kernel32

    ATTACH_PARENT_PROCESS = -1

    # If stdout already works, we already have a console
    try:
        sys.stdout.write("")
        sys.stdout.flush()
        return
    except Exception:
        pass

    # Try attaching to parent console
    if kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        sys.stdin = open("CONIN$", "r")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8")
        sys.stderr = open("CONOUT$", "w", encoding="utf-8")

def has_console():
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False
    

def main():
    """Main entry point for the application."""
    # Only care about console if CLI args are used
    if len(sys.argv) > 1:
        ensure_console()

    parser = argparse.ArgumentParser(description="Voice Transcription System Tray App")
    parser.add_argument('--config', default='transcription_config.json',
                        help='Path to configuration file')
    parser.add_argument('--list-devices', action='store_true', 
                        help='List available audio input devices')
    parser.add_argument('--save-audio-only', action='store_true',
                        help='Save audio chunks without processing with AI (for bulk processing later)')
    
    try:
        args = parser.parse_args()
    except SystemExit:
        if has_console():
            try:
                input("\nPress Enter to exit...")
            except Exception:
                pass
        sys.exit(1)
    
    if args.list_devices:
        list_audio_devices()
        if has_console():
            try:
                input("\nPress Enter to exit...")
            except Exception:
                pass
        return
        
    # Create and run app
    app = TranscriptionApp(config_path=args.config, save_audio_only=args.save_audio_only)
    app.run()


if __name__ == "__main__":
    main()