#!/usr/bin/env python3
"""
Audio Processing Module

Handles audio streaming, VAD (Voice Activity Detection), and audio processing.
"""

import sounddevice as sd
import wave
import array
import threading
import queue
import datetime
import os
import io
import time
import numpy as np


def list_audio_devices():
    """List all available audio input devices."""
    devices = sd.query_devices()
    print("\nAvailable audio input devices:")
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            print(f"  Device {i}: {dev['name']}")


class AudioProcessor:
    """
    Handles audio streaming and VAD processing.
    """
    
    def __init__(self, config, audio_queue, recording_enabled, logger):
        self.config = config
        self.audio_queue = audio_queue
        self.recording_enabled = recording_enabled
        self.logger = logger

        # SoundDevice setup
        self.stream = None
        self.current_device = config["audio"]["device_index"]

        # Counter for audio chunk numbering
        self.audio_chunk_counter = 0
        self.audio_chunk_lock = threading.Lock()

        # Create temp audio directory
        self.temp_audio_dir = "temp_audio"
        os.makedirs(self.temp_audio_dir, exist_ok=True)

        # Force flush flag
        self.force_flush_flag = False
        
        # Hard stop flag
        self.hard_stop_flag = False

        # Audio buffer for SoundDevice callback
        self.audio_buffer = queue.Queue()
        
        # Lock for thread-safe frame operations
        self.frames_lock = threading.Lock()
    
    def restart_stream(self):
        """Restart the audio stream with new device."""
        if self.stream:
            self.stream.stop()
            self.stream.close()

        def audio_callback(indata, frames, time, status):
            """Callback function for SoundDevice stream."""
            if status:
                self.logger.warning(f"Audio stream status: {status}")
            if self.recording_enabled.is_set() and not self.hard_stop_flag:
                # Convert numpy array to bytes (16-bit PCM)
                audio_bytes = indata.tobytes()
                self.audio_buffer.put(audio_bytes)

        self.stream = sd.InputStream(
            device=self.current_device,
            channels=1,
            samplerate=self.config["audio"]["rate"],
            dtype='int16',
            blocksize=self.config["audio"]["chunk_size"],
            callback=audio_callback
        )
        self.stream.start()
    
    def select_device(self, device_index):
        """Select a new microphone device."""
        self.logger.info(f"Switching to device {device_index}")
        self.current_device = device_index
        self.config["audio"]["device_index"] = device_index
        
        # Restart the recording stream
        if self.stream:
            self.restart_stream()
    
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
    
    def record_vad(self, running, save_audio_only=False):
        """Continuous VAD recording with seamless audio capture."""
        self.restart_stream()

        self.logger.info(f"Listening on device {self.current_device}...")

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

        # Logging thresholds for debugging
        self.logger.info(f"VAD Settings: silence_threshold={self.config['audio']['silence_threshold']}, "
                        f"silence_limit={silence_limit} chunks, buffer_limit={buffer_limit} chunks")

        # Queue monitoring variables
        queue_warning_threshold = 10  # Warn if queue has more than 10 items
        last_queue_log_time = time.time()
        queue_log_interval = 30.0  # Log queue status every 30 seconds

        try:
            while running.is_set():
                try:
                    # Check for hard stop
                    if self.hard_stop_flag:
                        self.logger.info("Hard stop detected - clearing current buffer")
                        with self.frames_lock:
                            frames = []
                            is_speaking = False
                            silent_chunks = 0
                        self.hard_stop_flag = False
                        continue
                    
                    # Get audio data from the callback buffer
                    try:
                        data = self.audio_buffer.get(timeout=0.1)
                    except queue.Empty:
                        # No audio data available, continue loop
                        continue

                    # Only process if recording is enabled
                    if self.recording_enabled.is_set():
                        with self.frames_lock:
                            frames.append(data)

                        # Check volume level - convert bytes back to numpy array for analysis
                        audio_array = np.frombuffer(data, dtype='int16')
                        max_val = np.max(np.abs(audio_array)) if len(audio_array) > 0 else 0

                        # Compare max volume against threshold
                        if max_val > self.config["audio"]["silence_threshold"]:
                            if not is_speaking:
                                is_speaking = True
                                self.logger.debug(f"Speech detected (volume: {max_val})")
                            silent_chunks = 0
                        else:
                            silent_chunks += 1
                            if is_speaking and silent_chunks == 1:
                                self.logger.debug(f"Silence started (volume: {max_val})")

                        # Check if we should send the accumulated audio
                        should_send = False
                        send_reason = ""

                        # Send if force flush is requested
                        if self.force_flush_flag and frames:
                            should_send = True
                            send_reason = "force flush requested"
                        # Or send if we detected speech and then enough silence
                        elif is_speaking and silent_chunks > silence_limit:
                            should_send = True
                            send_reason = f"silence after speech ({silent_chunks} silent chunks)"
                        # Or send if buffer is full
                        elif len(frames) >= buffer_limit:
                            should_send = True
                            send_reason = f"buffer full ({len(frames)} chunks)"

                        if should_send and frames:
                            # Send audio to queue for processing
                            with self.frames_lock:
                                audio_data = b''.join(frames)
                                frames_count = len(frames)
                            
                            self.audio_queue.put(audio_data)

                            # Log queue status periodically
                            current_time = time.time()
                            if current_time - last_queue_log_time > queue_log_interval:
                                queue_size = self.audio_queue.qsize()
                                if queue_size > queue_warning_threshold:
                                    self.logger.warning(f"Queue backlog: {queue_size} items waiting. Processing may be delayed.")
                                else:
                                    self.logger.info(f"Queue status: {queue_size} items waiting")
                                last_queue_log_time = current_time

                            self.logger.info(f"Sending audio: {send_reason}, {frames_count} chunks total")

                            # Reset for next segment
                            with self.frames_lock:
                                frames = []
                            is_speaking = False
                            silent_chunks = 0
                            # Reset force flush flag after handling
                            if self.force_flush_flag:
                                self.force_flush_flag = False
                    else:
                        # If recording is disabled, clear any accumulated frames
                        if frames:
                            with self.frames_lock:
                                frames = []
                            is_speaking = False
                            silent_chunks = 0
                        time.sleep(0.01)

                except Exception as e:
                    # Handle stream read errors gracefully
                    self.logger.warning(f"Stream read error: {e}")
                    time.sleep(0.1)
                    continue

        except Exception as e:
            self.logger.error(f"Recording error: {e}")
        finally:
            # Send any remaining audio (but not if hard stop was triggered)
            if frames and not self.hard_stop_flag:
                with self.frames_lock:
                    self.audio_queue.put(b''.join(frames))
            self.logger.info("Audio recording thread stopped")
    
    def force_flush_audio(self):
        """Force flush any accumulated audio frames to the queue."""
        self.force_flush_flag = True
        self.logger.info("Force flush audio flag set")
    
    def hard_stop(self):
        """Hard stop - immediately discard current buffer and clear audio queue."""
        self.hard_stop_flag = True
        
        # Clear the audio buffer from the callback
        while not self.audio_buffer.empty():
            try:
                self.audio_buffer.get_nowait()
            except queue.Empty:
                break
        
        self.logger.info("Hard stop executed - current buffer discarded")

    def cleanup(self):
        """Clean up audio resources."""
        # Stop stream
        if self.stream:
            self.stream.stop()
            self.stream.close()