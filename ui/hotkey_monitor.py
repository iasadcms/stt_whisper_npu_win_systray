#!/usr/bin/env python3
"""
Hotkey Monitoring Module

Handles global hotkey registration and monitoring for the transcription application.
This module provides a dedicated class for managing hotkey functionality,
separating UI concerns from the main application logic.
"""

import threading
import time
import ctypes
from ctypes import wintypes


class HotkeyMonitor:
    """
    Class for monitoring and handling global hotkeys.
    
    This class encapsulates all hotkey-related functionality including:
    - Parsing hotkey configurations
    - Registering hotkeys with Windows API
    - Monitoring for hotkey presses
    - Triggering appropriate actions
    - Cleanup and unregistering hotkeys
    """
    
    def __init__(self, config, app_instance, logger):
        """
        Initialize the HotkeyMonitor.
        
        Args:
            config: Application configuration containing hotkey settings
            app_instance: Reference to the main application instance
            logger: Logger instance for logging messages
        """
        self.config = config
        self.app = app_instance
        self.logger = logger
        self.running = threading.Event()
        # Don't set running flag here - let start() method handle it
        
        # Windows API constants
        self.MOD_ALT = 0x0001
        self.MOD_CONTROL = 0x0002
        self.MOD_SHIFT = 0x0004
        self.MOD_WIN = 0x0008
        self.WM_HOTKEY = 0x0312
        
        # Virtual key codes for function keys
        self.VK_F1 = 0x70
        self.VK_F2 = 0x71
        self.VK_F3 = 0x72
        self.VK_F4 = 0x73
        self.VK_F5 = 0x74
        self.VK_F6 = 0x75
        self.VK_F7 = 0x76
        self.VK_F8 = 0x77
        self.VK_F9 = 0x78
        self.VK_F10 = 0x79
        self.VK_F11 = 0x7A
        self.VK_F12 = 0x7B
        self.VK_TILDE = 0xC0  # Backtick/tilde key
        
        # Hotkey IDs
        self.HOTKEY_TOGGLE = 1
        self.HOTKEY_STOP = 2
        self.HOTKEY_SUBMIT = 3

    def parse_hotkey(self, hotkey_str):
        """
        Parse hotkey string into Windows modifier and virtual key code.
        
        Args:
            hotkey_str: String representation of hotkey (e.g., "ctrl+shift+f1")
            
        Returns:
            tuple: (modifiers, vk_code) where modifiers is a bitmask and vk_code is the virtual key code
        """
        parts = [part.strip().lower() for part in hotkey_str.split('+')]
        modifiers = 0
        vk_code = 0
        
        for part in parts:
            if part == 'ctrl':
                modifiers |= self.MOD_CONTROL
            elif part == 'shift':
                modifiers |= self.MOD_SHIFT
            elif part == 'alt':
                modifiers |= self.MOD_ALT
            elif part == 'win':
                modifiers |= self.MOD_WIN
            elif part == 'f1':
                vk_code = self.VK_F1
            elif part == 'f2':
                vk_code = self.VK_F2
            elif part == 'f3':
                vk_code = self.VK_F3
            elif part == 'f4':
                vk_code = self.VK_F4
            elif part == 'f5':
                vk_code = self.VK_F5
            elif part == 'f6':
                vk_code = self.VK_F6
            elif part == 'f7':
                vk_code = self.VK_F7
            elif part == 'f8':
                vk_code = self.VK_F8
            elif part == 'f9':
                vk_code = self.VK_F9
            elif part == 'f10':
                vk_code = self.VK_F10
            elif part == 'f11':
                vk_code = self.VK_F11
            elif part == 'f12':
                vk_code = self.VK_F12
            elif part in ['`', 'backtick', 'tilde']:
                vk_code = self.VK_TILDE
            elif len(part) == 1:
                # Single character - convert to virtual key code
                vk_code = ord(part.upper())
        
        return modifiers, vk_code

    def monitor_loop(self):
        """
        Main monitoring loop for hotkey events.
        
        This method runs in a separate thread and handles:
        - Registering hotkeys with Windows API
        - Processing hotkey messages
        - Triggering appropriate actions
        - Cleanup on exit
        """
        # Check if submit hotkey exists in config, if not use a default
        submit_hotkey = self.config['hotkeys'].get('submit', 'ctrl+shift+f3')

        self.logger.info(f"Hotkey monitoring started: {self.config['hotkeys']['toggle']} to toggle, "
                        f"{self.config['hotkeys']['stop']} to stop, {submit_hotkey} to submit")

        # Parse hotkeys
        toggle_mod, toggle_vk = self.parse_hotkey(self.config['hotkeys']['toggle'])
        stop_mod, stop_vk = self.parse_hotkey(self.config['hotkeys']['stop'])
        submit_mod, submit_vk = self.parse_hotkey(submit_hotkey)

        # Windows API functions
        user32 = ctypes.windll.user32

        # Register hotkeys
        try:
            if not user32.RegisterHotKey(None, self.HOTKEY_TOGGLE, toggle_mod, toggle_vk):
                self.logger.error(f"Failed to register toggle hotkey: {self.config['hotkeys']['toggle']}")
            else:
                self.logger.info(f"Registered toggle hotkey: {self.config['hotkeys']['toggle']}")
            
            if not user32.RegisterHotKey(None, self.HOTKEY_STOP, stop_mod, stop_vk):
                self.logger.error(f"Failed to register stop hotkey: {self.config['hotkeys']['stop']}")
            else:
                self.logger.info(f"Registered stop hotkey: {self.config['hotkeys']['stop']}")
            
            if not user32.RegisterHotKey(None, self.HOTKEY_SUBMIT, submit_mod, submit_vk):
                self.logger.error(f"Failed to register submit hotkey: {submit_hotkey}")
            else:
                self.logger.info(f"Registered submit hotkey: {submit_hotkey}")
            
            # Message loop to process hotkey events
            msg = wintypes.MSG()
            while self.running.is_set():
                # Non-blocking peek at message queue
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE = 1
                    if msg.message == self.WM_HOTKEY:
                        hotkey_id = msg.wParam
                        
                        if hotkey_id == self.HOTKEY_TOGGLE:
                            self.logger.debug("Toggle hotkey pressed")
                            threading.Thread(target=self.app.toggle_recording, daemon=True).start()
                        elif hotkey_id == self.HOTKEY_STOP:
                            self.logger.debug("Stop hotkey pressed")
                            threading.Thread(target=self.app.hard_stop, daemon=True).start()
                        elif hotkey_id == self.HOTKEY_SUBMIT:
                            self.logger.debug("Submit hotkey pressed")
                            threading.Thread(target=self.app.submit_recording, daemon=True).start()
                        
                        # Don't dispatch hotkey messages - we've already handled them
                        # Dispatching them can cause focus to be stolen from the active window
                    else:
                        # For non-hotkey messages, translate and dispatch normally
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
                user32.UnregisterHotKey(None, self.HOTKEY_TOGGLE)
                user32.UnregisterHotKey(None, self.HOTKEY_STOP)
                user32.UnregisterHotKey(None, self.HOTKEY_SUBMIT)
                self.logger.info("Hotkeys unregistered")
            except:
                pass

    def start(self):
        """
        Start the hotkey monitoring thread.
        """
        if not self.running.is_set():
            self.running.set()
            monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            monitor_thread.start()
            self.logger.info("Hotkey monitor thread started")

    def stop(self):
        """
        Stop the hotkey monitoring.
        """
        self.running.clear()
        self.logger.info("Hotkey monitor stopped")