#!/usr/bin/env python3
"""
Transcription Module

Handles transcription processing, API communication, and output handling.
"""

import pyautogui
import datetime
import os
import io
import wave
import threading
from openai import OpenAI
from path_utils import validate_and_prepare_path


class NotebookHandler:
    """
    Handles notebook file operations for transcription storage.
    """
    
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.notebook_path = config["notebook"]["file_path"]
        self.notebook_mode = False
        
        # Validate and prepare notebook path
        path_valid, validation_message = validate_and_prepare_path(self.notebook_path, self.logger)
        if not path_valid:
            self.logger.error(f"Notebook path validation failed: {validation_message}")
            self.logger.error("Notebook functionality will be disabled")
            self.notebook_path = None
        else:
            # Ensure notebook directory exists
            notebook_dir = os.path.dirname(self.notebook_path)
            if notebook_dir:
                os.makedirs(notebook_dir, exist_ok=True)
            else:
                # If no directory specified, ensure file can be created in current dir
                try:
                    open(self.notebook_path, 'a').close()
                except Exception as e:
                    self.logger.error(f"Failed to create notebook file: {e}")
                    self.notebook_path = None
    
    def append_to_notebook(self, text):
        """
        Append transcription text to the notebook file.
         
        Args:
            text: The transcription text to append
        """
        if not self.notebook_mode or not text or not self.notebook_path:
            return
            
        try:
            # Ensure notebook file exists
            if not os.path.exists(self.notebook_path):
                open(self.notebook_path, 'w').close()
            
            # Append text as a new line
            with open(self.notebook_path, 'a', encoding='utf-8') as f:
                f.write(f"{text}\n")
            
            self.logger.info(f"Appended to notebook: {text}")
        except Exception as e:
            self.logger.error(f"Error writing to notebook: {e}")
    
    def get_notebook_content(self):
        """
        Return the full content of the notebook.
        
        Returns:
            String containing notebook content, or empty string if error
        """
        try:
            if os.path.exists(self.notebook_path):
                with open(self.notebook_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        except Exception as e:
            self.logger.error(f"Error reading notebook: {e}")
            return ""
    
    def clear_notebook(self):
        """
        Clear the notebook file content.
        """
        try:
            with open(self.notebook_path, 'w', encoding='utf-8') as f:
                f.write("")
            self.logger.info("Notebook cleared")
        except Exception as e:
            self.logger.error(f"Error clearing notebook: {e}")
    
    def open_notebook(self):
        """
        Open the notebook file in the default text editor.
        """
        try:
            if os.path.exists(self.notebook_path):
                os.startfile(self.notebook_path)
            else:
                # Create empty notebook if it doesn't exist
                with open(self.notebook_path, 'w') as f:
                    f.write("")
                os.startfile(self.notebook_path)
        except Exception as e:
            self.logger.error(f"Error opening notebook: {e}")
    
    def set_notebook_path(self, path):
        """
        Change the notebook file path.
        
        Args:
            path: New path for the notebook file
        """
        try:
            # Ensure directory exists
            notebook_dir = os.path.dirname(path)
            if notebook_dir:
                os.makedirs(notebook_dir, exist_ok=True)
            
            # If old notebook exists and has content, copy to new location
            if os.path.exists(self.notebook_path):
                old_content = self.get_notebook_content()
                if old_content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(old_content)
            
            self.notebook_path = path
            self.config["notebook"]["file_path"] = path
            self.logger.info(f"Notebook path changed to: {path}")
        except Exception as e:
            self.logger.error(f"Error changing notebook path: {e}")
    
    def toggle_notebook_mode(self):
        """
        Toggle notebook mode on/off.
        
        Returns:
            New notebook mode state (True/False)
        """
        self.notebook_mode = not self.notebook_mode
        return self.notebook_mode
    
    def set_notebook_mode(self, enabled):
        """
        Set notebook mode to specific state.
        
        Args:
            enabled: Boolean indicating whether to enable notebook mode
        """
        self.notebook_mode = enabled


class TranscriptionHandler:
    """
    Handles transcription processing and output.
    """
    
    def __init__(self, config, logger, app):
        self.config = config
        self.logger = logger
        self.app = app
        
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
        
        # Log file
        if self.config["output"]["save_transcription_logs"]:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            self.log_file = os.path.join(
                self.config["output"]["log_dir"],
                f"transcription_{timestamp}.log"
            )
        else:
            self.log_file = None
        
        # Notebook handler
        self.notebook_handler = NotebookHandler(config, logger)
        self.notebook_mode = config["notebook"]["enabled"]
        self.notebook_handler.set_notebook_mode(self.notebook_mode)
        
        # Event to signal when transcription output is complete
        self.transcription_complete = threading.Event()
        self.transcription_complete.set()
    
    def type_transcription(self, text):
        """
        Type transcribed text to the active window.
        
        Args:
            text: The transcribed text to type
        """
        if not self.config["output"]["typing_enabled"] or not text:
            # Signal completion even if typing is disabled or text is empty
            self.transcription_complete.set()
            return
        
        try:
            import subprocess
            import ctypes
            import time
            
            self.logger.debug("type_transcription: START - about to type text")
            
            # Get the currently active window handle before any operations
            user32 = ctypes.windll.user32
            active_window = user32.GetForegroundWindow()
            
            # Only flash cursor if recording is still enabled
            # (prevents flashing after user has paused)
            if self.config["visual"]["cursor_flash_enabled"]:
                flash_count = self.config["visual"]["cursor_flash_count"]
                flash_duration = self.config["visual"]["cursor_flash_duration"]
                
                self.logger.debug(f"type_transcription: Flashing cursor {flash_count} times")
                for _ in range(flash_count):
                    # Get current cursor position
                    x, y = pyautogui.position()
                    
                    # Move cursor slightly to create a "flash" effect
                    pyautogui.moveRel(2, 2, duration=flash_duration)
                    pyautogui.moveRel(-2, -2, duration=flash_duration)
            
            # Copy text to clipboard using Windows native command
            text_with_space = text + " "  # Add trailing space so next transcription doesn't stick
            self.logger.debug(f"type_transcription: Copying to clipboard: '{text_with_space}'")
            process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
            process.communicate(text_with_space.encode('utf-8'))
            
            # Restore focus to the original active window
            self.logger.debug("type_transcription: Restoring focus to active window")
            user32.SetForegroundWindow(active_window)
            time.sleep(0.05)  # Brief delay to ensure focus is restored
            
            # Paste from clipboard using Ctrl+V
            self.logger.debug("type_transcription: Pasting with Ctrl+V")
            pyautogui.hotkey('ctrl', 'v')
            self.logger.debug("type_transcription: COMPLETE - text pasted")
            
            # Signal that transcription output is complete
            self.transcription_complete.set()
        except Exception as e:
            self.logger.error(f"Error typing transcription: {e}")
            # Signal completion even on error to prevent hanging
            self.transcription_complete.set()
    
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
    
    def process_audio_chunk(self, data, save_audio_only=False, audio_chunk_counter=None, audio_chunk_lock=None):
        """
        Process an audio chunk for transcription.
        
        Args:
            data: Audio data to process
            save_audio_only: Whether to only save audio without transcription
            audio_chunk_counter: Counter for audio chunk numbering
            audio_chunk_lock: Lock for thread-safe counter access
        """
        self.logger.debug("process_audio_chunk: START - processing audio chunk")
        
        # Clear the completion event at the start of each transcription cycle
        self.transcription_complete.clear()
        
        # Handle save-audio-only mode
        if save_audio_only:
            if audio_chunk_counter and audio_chunk_lock:
                with audio_chunk_lock:
                    audio_chunk_counter[0] += 1
                    self.save_audio_chunk(data, audio_chunk_counter[0], audio_chunk_lock)
            return
        
        # Save WAV if enabled
        self.save_wav(data)
        
        # Start timing measurement
        start_time = datetime.datetime.now()
        
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
            
            # Calculate processing time
            end_time = datetime.datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            if text:
                # Filter hallucinations
                if text.lower() in self.config["filters"]["hallucinations"]:
                    self.logger.info(f"Filtered: {text}")
                    # Signal completion even for filtered text
                    self.transcription_complete.set()
                else:
                    # Log transcription text if enabled
                    if self.config["output"]["log_transcription_text"]:
                        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        log_message = f"[{timestamp}] ({processing_time:.3f}s) | {text}"
                        self.logger.info(log_message)
                    
                    # Log to file if enabled
                    if self.log_file:
                        with open(self.log_file, 'a', encoding='utf-8') as f:
                            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            f.write(f"[{timestamp}] ({processing_time:.3f}s) | {text}\n")
                    
                    # Handle output based on mode
                    if self.notebook_mode:
                        # Append to notebook
                        self.logger.debug(f"process_audio_chunk: Appending to notebook: '{text}'")
                        self.notebook_handler.append_to_notebook(text)
                        self.logger.debug(f"process_audio_chunk: COMPLETE - appended to notebook")
                        # Signal that transcription output is complete
                        self.transcription_complete.set()
                    else:
                        # Type to active window (existing behavior)
                        self.logger.debug(f"process_audio_chunk: About to type transcription: '{text}'")
                        self.type_transcription(text)
                        # Note: transcription_complete is set by type_transcription() after paste completes
            else:
                # No text received - signal completion anyway
                self.logger.debug("process_audio_chunk: No text received from transcription")
                self.transcription_complete.set()

        except Exception as e:
            # Enhanced error reporting for translation endpoint issues
            if self.config["output"]["log_translation_errors"]:
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    self.logger.error(f"Translation endpoint unavailable: {e}")
                elif "404" in str(e) or "not found" in str(e).lower():
                    self.logger.error(f"Translation endpoint not found: {e}")
                elif "authentication" in str(e).lower() or "401" in str(e):
                    self.logger.error(f"Translation endpoint authentication failed: {e}")
                else:
                    self.logger.error(f"Translation endpoint error: {e}")
            else:
                self.logger.error(f"API Error: {e}")
            
            # Signal completion even on error to prevent hanging
            self.transcription_complete.set()
    
    def toggle_notebook_mode(self):
        """
        Toggle between notebook mode and window typing mode.
        
        Returns:
            New notebook mode state (True/False)
        """
        self.notebook_mode = self.notebook_handler.toggle_notebook_mode()
        return self.notebook_mode
        
    def set_notebook_mode(self, enabled):
        """
        Set notebook mode to specific state.
        
        Args:
            enabled: Boolean indicating whether to enable notebook mode
        """
        self.notebook_mode = enabled
        self.notebook_handler.set_notebook_mode(enabled)
        
    def open_notebook(self):
        """Open the notebook file in default editor."""
        self.notebook_handler.open_notebook()
        
    def clear_notebook(self):
        """Clear the notebook file content."""
        self.notebook_handler.clear_notebook()
        
    def set_notebook_path(self, path):
        """
        Change the notebook file path.
        
        Args:
            path: New path for the notebook file
        """
        self.notebook_handler.set_notebook_path(path)
        self.config["notebook"]["file_path"] = path
        
    def get_notebook_content(self):
        """
        Get the current notebook content.
        
        Returns:
            String containing notebook content
        """
        return self.notebook_handler.get_notebook_content()
    
    def save_audio_chunk(self, data, chunk_number, audio_chunk_lock):
        """
        Save audio chunk to disk for later processing.
        
        Args:
            data: Raw audio bytes to save
            chunk_number: Sequential number for ordering
            audio_chunk_lock: Lock for thread-safe operations
        """
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = os.path.join(
            "temp_audio",
            f"chunk_{chunk_number}_{timestamp}.wav"
        )
        
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)  # Mono audio
            wf.setsampwidth(2)  # 16-bit audio (2 bytes)
            wf.setframerate(self.config["audio"]["rate"])
            wf.writeframes(data)
        
        self.logger.info(f"Saved audio chunk: {filename}")


def api_worker(audio_queue, transcription_handler, running, save_audio_only, audio_chunk_counter, audio_chunk_lock):
    """
    Worker thread that processes audio chunks from the queue.

    Args:
        audio_queue: Queue containing audio chunks to process
        transcription_handler: TranscriptionHandler instance
        running: Event indicating if worker should continue
        save_audio_only: Whether to only save audio without transcription
        audio_chunk_counter: Counter for audio chunk numbering
        audio_chunk_lock: Lock for thread-safe counter access
    """
    import time
    import random

    # Track API endpoint health
    endpoint_healthy = True
    consecutive_failures = 0
    max_retries = 3
    retry_delay = 1.0  # Start with 1 second delay

    while running.is_set():
        data = audio_queue.get()
        if data is None:
            break

        try:
            transcription_handler.process_audio_chunk(
                data,
                save_audio_only=save_audio_only,
                audio_chunk_counter=audio_chunk_counter,
                audio_chunk_lock=audio_chunk_lock
            )

            # Reset failure counter on success
            consecutive_failures = 0
            endpoint_healthy = True
            retry_delay = 1.0  # Reset to base delay

        except Exception as e:
            error_msg = str(e)
            transcription_handler.logger.error(f"Transcription failed: {error_msg}")

            # Check if this is an endpoint-related error
            if ("connection" in error_msg.lower() or
                "timeout" in error_msg.lower() or
                "404" in error_msg or
                "not found" in error_msg.lower() or
                "authentication" in error_msg.lower() or
                "401" in error_msg):

                consecutive_failures += 1
                endpoint_healthy = False

                # Implement exponential backoff with jitter
                if consecutive_failures <= max_retries:
                    # Calculate exponential backoff with jitter
                    current_delay = min(retry_delay * (2 ** (consecutive_failures - 1)), 30.0)
                    jitter = random.uniform(0.5, 1.5)  # Add 50-150% jitter
                    actual_delay = current_delay * jitter

                    transcription_handler.logger.warning(
                        f"API endpoint unavailable (attempt {consecutive_failures}/{max_retries}). "
                        f"Retrying in {actual_delay:.1f} seconds..."
                    )

                    # Save audio chunk for retry
                    if audio_chunk_counter and audio_chunk_lock:
                        with audio_chunk_lock:
                            audio_chunk_counter[0] += 1
                            transcription_handler.save_audio_chunk(data, audio_chunk_counter[0], audio_chunk_lock)

                    # Wait before retrying
                    time.sleep(actual_delay)

                    # Put the data back in the queue for retry
                    audio_queue.put(data)
                    continue

                else:
                    transcription_handler.logger.error(
                        f"API endpoint unavailable after {max_retries} attempts. "
                        "Audio chunk saved for later processing."
                    )

                    # Save audio chunk for later processing
                    if audio_chunk_counter and audio_chunk_lock:
                        with audio_chunk_lock:
                            audio_chunk_counter[0] += 1
                            transcription_handler.save_audio_chunk(data, audio_chunk_counter[0], audio_chunk_lock)

                    # Don't retry further, move to next item
                    consecutive_failures = 0
                    endpoint_healthy = False

            else:
                # Non-endpoint error, log and continue
                transcription_handler.logger.error(f"Processing error (non-retryable): {error_msg}")
                consecutive_failures = 0

        finally:
            audio_queue.task_done()
