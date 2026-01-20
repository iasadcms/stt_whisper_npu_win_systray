#!/usr/bin/env python3
"""
Audio Processing Module

Handles audio streaming, VAD (Voice Activity Detection), and audio processing.
"""

import pyaudio
import wave
import array
import threading
import queue
import datetime
import os
import io
import time


def list_audio_devices():
    """List all available audio input devices."""
    p = pyaudio.PyAudio()
    print("\nAvailable audio input devices:")
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev['maxInputChannels'] > 0:
            print(f"  Device {i}: {dev['name']}")
    p.terminate()


class AudioProcessor:
    """
    Handles audio streaming and VAD processing.
    """
    
    def __init__(self, config, audio_queue, recording_enabled, logger):
        self.config = config
        self.audio_queue = audio_queue
        self.recording_enabled = recording_enabled
        self.logger = logger
        
        # PyAudio setup
        self.p = pyaudio.PyAudio()
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
                    # Always read audio to prevent gaps
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
                            audio_data = b''.join(frames)
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

                            self.logger.info(f"Sending audio: {send_reason}, {len(frames)} chunks total")

                            # Reset for next segment
                            frames = []
                            is_speaking = False
                            silent_chunks = 0
                            # Reset force flush flag after handling
                            if self.force_flush_flag:
                                self.force_flush_flag = False
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
            self.logger.info("Audio recording thread stopped")
    
    def force_flush_audio(self):
        """Force flush any accumulated audio frames to the queue."""
        # This method will be implemented in the record_vad method
        # by setting a flag that triggers immediate flush
        self.force_flush_flag = True
        self.logger.info("Force flush audio flag set")

    def cleanup(self):
        """Clean up audio resources."""
        # Stop stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.p:
            self.p.terminate()
