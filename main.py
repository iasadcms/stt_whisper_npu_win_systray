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
from path_utils import resolve_relative_path, get_script_dir, resolve_process_relative_path
from ui import load_logo, create_icon_image, VisualIndicators, TrayMenu
from ui.icon_effects import IconEffects
from ui.hotkey_monitor import HotkeyMonitor
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
        
        # Endpoint health state
        self.endpoint_healthy = True
        self.last_successful_send_time = 0.0
        self.poll_lock = threading.Lock()
        
        # Buffer draining state
        self.buffer_draining = threading.Event()
        self.buffer_monitor_thread = None
        
        # Counter for audio chunk numbering (using list to allow modification in threads)
        self.audio_chunk_counter = [0]
        self.audio_chunk_lock = threading.Lock()
        
        # Icon update throttling
        self.icon_update_lock = threading.Lock()
        self.last_icon_state = None
        self.last_icon_color = None
        self.icon_update_pending = False
        
        # Initialize components
        self.audio_processor = AudioProcessor(
            self.config,
            self.audio_queue,
            self.recording_enabled,
            self.logger
        )

        self.transcription_handler = TranscriptionHandler(self.config, self.logger, self)

        # Notebook state
        self.notebook_mode = self.config["notebook"]["enabled"]

        # Load UI components
        self.logo, self.gray_logo = load_logo()
        self.visual_indicators = VisualIndicators(self.config)
        self.visual_indicators.set_notebook_mode(self.notebook_mode)
        self.visual_indicators.set_buffer_draining(False)  # Ensure buffer draining is initially false
        self.visual_indicators.set_endpoint_checking(False)  # Ensure endpoint checking is initially false
        self.tray_menu = TrayMenu(self)

        # Initialize icon effects
        self.icon_effects = IconEffects(self)

        # Initialize hotkey monitor
        self.hotkey_monitor = HotkeyMonitor(self.config, self, self.logger)

        # Tray icon
        self.icon = None
    
    def start_buffer_monitor(self):
        """Start monitoring buffer draining state."""
        def buffer_monitor_loop():
            # Give the app a moment to fully initialize
            time.sleep(1)

            while self.running.is_set():
                # Check if recording is paused (draining state)
                recording_paused = not self.recording_enabled.is_set()
                # Check if there are items in queue OR if transcription is still processing
                has_buffer_items = not self.audio_queue.empty()
                transcription_in_progress = not self.transcription_handler.transcription_complete.is_set()

                # Buffer is draining if: recording is paused AND (queue has items OR transcription is in progress)
                should_be_draining = recording_paused and (has_buffer_items or transcription_in_progress)

                if should_be_draining:
                    if not self.buffer_draining.is_set():
                        self.buffer_draining.set()
                        self.visual_indicators.set_buffer_draining(True)
                        # Only start glow effect if we're actually recording or have items to process
                        if self.recording_enabled.is_set() or has_buffer_items or transcription_in_progress:
                            self.icon_effects.start_glow_effect()
                        self.logger.info("[BUFFER] Buffer draining STARTED")
                        self.icon_effects.update_icon()  # Update icon when buffer draining starts
                else:
                    if self.buffer_draining.is_set():
                        self.buffer_draining.clear()
                        self.visual_indicators.set_buffer_draining(False)
                        self.icon_effects.stop_glow_effect()
                        self.logger.info("[BUFFER] Buffer draining STOPPED")
                        self.icon_effects.update_icon()  # Update icon when buffer draining stops

                        # If recording is still paused and buffer is empty, clear all visualizations
                        if recording_paused and not has_buffer_items and not transcription_in_progress:
                            if hasattr(self, 'visual_indicators') and self.visual_indicators.indicator_thread and self.visual_indicators.indicator_thread.is_alive():
                                self.logger.info("[BUFFER] Clearing visualizations - buffer empty and recording paused")
                                self.visual_indicators.stop_recording_indicator()
                                self.visual_indicators.stop_animation()

                # Update buffer items state for visual indicators
                self.visual_indicators.set_has_buffer_items(has_buffer_items)

                time.sleep(0.1)

        if not self.buffer_monitor_thread or not self.buffer_monitor_thread.is_alive():
            self.buffer_monitor_thread = threading.Thread(target=buffer_monitor_loop, daemon=True)
            self.buffer_monitor_thread.start()
    
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
            # Application logs are stored in the process directory (same as executable)
            log_dir = resolve_process_relative_path('')
            os.startfile(log_dir)
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

VISUAL INDICATORS:
- Red cursor indicator: Recording to active window
- Blue cursor indicator: Recording to notebook
- Yellow cursor indicator: Buffer is draining (processing queue)
- Orange cursor indicator: API endpoint is unavailable (recording continues, audio is saved)
- Bright Red cursor indicator: API endpoint is being checked (background monitoring)
- Tray icon color matches the cursor indicator color

USAGE TIPS:
- When recording is paused, the queue continues processing. The mouse cursor will indicate processing is occuring.
- Use "Stop Recording and Clear Queue" to immediately stop recording, and clear pending items.
- Audio files are saved in temp_audio/ directory
- Logs are stored in transcription_logs/ directory
- If the cursor turns orange, the API endpoint is unavailable but recording continues
- If the cursor turns bright red, the application is checking API endpoint health

TROUBLESHOOTING:
- If API endpoint is unavailable (orange indicator), transcriptions will be saved for later processing
- Queue items are processed in order and logged appropriately
- Check your API endpoint configuration if orange indicator persists
- The application automatically checks endpoint health periodically and adjusts recording behavior accordingly"""

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

            # Track consecutive failures for aggressive polling
            consecutive_failures = 0
            max_consecutive_failures = 3

            # Initial endpoint check
            time.sleep(2)  # Give the app a moment to fully initialize

            while self.running.is_set():
                # Show red indicator while checking endpoint
                self.visual_indicators.set_endpoint_checking(True)
                self.icon_effects.update_icon()

                try:
                    # Simple health check - try to connect to the endpoint
                    test_url = f"{self.config['api']['base_url']}/models"
                    response = requests.get(
                        test_url,
                        headers={"Authorization": f"Bearer {self.config['api']['api_key']}"},
                        timeout=5
                    )

                    if response.status_code == 200:
                        if not self.endpoint_healthy:
                            self.endpoint_healthy = True
                            self.logger.info("API endpoint health restored")
                            # Update visual indicator to show healthy state
                            self.visual_indicators.set_endpoint_status(True)
                            consecutive_failures = 0
                        else:
                            # Endpoint is still healthy, just update to clear checking state
                            self.visual_indicators.set_endpoint_checking(False)
                    else:
                        if self.endpoint_healthy:
                            self.endpoint_healthy = False
                            self.logger.warning(f"API endpoint health check failed: HTTP {response.status_code}")
                            self.visual_indicators.set_endpoint_status(False)
                            consecutive_failures += 1
                        else:
                            consecutive_failures += 1

                except Exception as e:
                    if self.endpoint_healthy:
                        self.endpoint_healthy = False
                        self.logger.warning(f"API endpoint health check failed: {e}")
                        self.visual_indicators.set_endpoint_status(False)
                        consecutive_failures += 1
                    else:
                        consecutive_failures += 1

                # Clear checking state
                self.visual_indicators.set_endpoint_checking(False)
                self.logger.debug(f"API endpoint checking: Complete - {test_url}")
                self.icon_effects.update_icon()

                # Adjust polling frequency based on endpoint health
                if self.endpoint_healthy:
                    # Normal polling when healthy - every 30 seconds
                    time.sleep(30)
                else:
                    # Aggressive polling when endpoint is down
                    # Start with 5 seconds, increase up to 30 seconds
                    poll_interval = min(5 * (consecutive_failures + 1), 30)
                    time.sleep(poll_interval)

                # If endpoint is down and we're recording, handle it
                if not self.endpoint_healthy and self.recording_enabled.is_set():
                    self.handle_endpoint_failure_during_recording()

        # Start the monitor thread
        monitor_thread = threading.Thread(target=endpoint_monitor_loop, daemon=True)
        monitor_thread.start()

    def handle_endpoint_failure_during_recording(self):
        """Handle endpoint failure when recording is active."""
        if not self.endpoint_healthy and self.recording_enabled.is_set():
            self.logger.warning("Endpoint failure detected during recording - stopping recording")

            # Stop recording gracefully
            self.recording_enabled.clear()

            # Force flush any accumulated audio
            self.audio_processor.force_flush_audio()

            # Stop visual indicators
            if hasattr(self, 'visual_indicators') and self.visual_indicators.indicator_thread and self.visual_indicators.indicator_thread.is_alive():
                self.visual_indicators.stop_recording_indicator()
                self.visual_indicators.stop_animation()

            # Stop glow effect
            self.icon_effects.stop_glow_effect()

            # Update icon to show endpoint unavailable state
            self.icon_effects.update_icon()

            self.logger.info("Recording stopped due to endpoint failure - audio saved for later processing")
    
    def get_current_indicator_color(self):
        """Get the current visual indicator color based on state."""
        return self.visual_indicators.get_current_color()
    
    
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

                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    self.logger.warning(f"Queue wait timeout ({elapsed:.1f}s) - forcing stop")
                
                # Wait for transcription output to complete (typing/notebook write)
                # This ensures visual indicators stay visible until the very last output is done
                transcription_timeout = 5.0  # Maximum 5 seconds to wait for transcription output
                transcription_start = time.time()
                
                while not self.transcription_handler.transcription_complete.is_set() and (time.time() - transcription_start) < transcription_timeout:
                    time.sleep(0.05)
                
                transcription_elapsed = time.time() - transcription_start
                if transcription_elapsed >= transcription_timeout:
                    self.logger.warning(f"Transcription output timeout ({transcription_elapsed:.1f}s) - forcing stop")
                
                # Only stop visual indicators if they were actually running AND buffer is not draining
                if hasattr(self, 'visual_indicators') and self.visual_indicators.indicator_thread and self.visual_indicators.indicator_thread.is_alive():
                    # Check if buffer is still draining
                    if not self.buffer_draining.is_set():
                        self.logger.info("wait_and_stop: Stopping visual indicators")
                        self.visual_indicators.stop_recording_indicator()
                        self.visual_indicators.stop_animation()
                        self.icon_effects.stop_glow_effect()
                        self.logger.info("Queue emptied and transcription complete - recording fully stopped")
                        # Ensure recording is stopped when buffer draining completes
                        self.recording_enabled.clear()
                    else:
                        self.logger.info("Buffer still draining - keeping visual indicators and glow active")
                else:
                    self.logger.info("Queue emptied - no active visual indicators to stop")
                
                # Update icon after animations complete
                self.icon_effects.update_icon()

            threading.Thread(target=wait_and_stop, daemon=True).start()
        else:
            # Starting - clear buffer draining, play expand animation then start indicator
            self.buffer_draining.clear()
            self.visual_indicators.set_buffer_draining(False)
            self.recording_enabled.set()
            self.logger.info("Recording RESUMED")
            self.visual_indicators.start_animation()
            self.visual_indicators.start_recording_indicator()
            self.icon_effects.start_glow_effect()
            self.icon_effects.update_icon()

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
        self.buffer_draining.clear()
        self.visual_indicators.set_buffer_draining(False)
        self.icon_effects.stop_glow_effect()
        self.logger.info("Recording STOPPED and cleared")

        # Clear queue immediately (don't wait)
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()  # Mark as done to prevent join() hanging
            except queue.Empty:
                break

        # Stop indicator and play collapse animation only if they are running
        if hasattr(self, 'visual_indicators') and self.visual_indicators.indicator_thread and self.visual_indicators.indicator_thread.is_alive():
            self.visual_indicators.stop_recording_indicator()
            self.visual_indicators.stop_animation()

        self.icon_effects.update_icon()
        
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
        self.buffer_draining.clear()
        self.visual_indicators.set_buffer_draining(False)
        self.icon_effects.stop_glow_effect()
         
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
         
        # Stop all visual indicators immediately only if they are running
        if hasattr(self, 'visual_indicators') and self.visual_indicators.indicator_thread and self.visual_indicators.indicator_thread.is_alive():
            self.visual_indicators.stop_recording_indicator()
            self.visual_indicators.stop_animation()
        
        # Update icon
        self.icon_effects.update_icon()
        
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
        
        # Stop hotkey monitor
        self.hotkey_monitor.stop()
        
        # Stop icon
        if self.icon:
            self.icon.stop()
    
    
    def run(self):
        """Run the application with system tray icon."""
        # Create and start the icon
        self.icon = Icon(
            "TranscriptionApp",
            create_icon_image(self.logo, self.gray_logo, self.recording_enabled.is_set()),
            "Voice Transcription",
            self.tray_menu.create_menu()
        )

        # Set initial icon color based on current state
        self.icon_effects.update_icon()

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
        self.hotkey_monitor.start()

        # Start endpoint health monitor
        self.start_endpoint_monitor()

        # Start buffer monitor
        self.start_buffer_monitor()

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
