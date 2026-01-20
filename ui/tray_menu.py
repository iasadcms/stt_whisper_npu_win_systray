#!/usr/bin/env python3
"""
Tray Menu Module

Handles system tray menu creation and management.
"""

from pystray import Menu, MenuItem


class TrayMenu:
    """
    Handles system tray menu creation and management.
    """
    
    def __init__(self, app):
        self.app = app
    
    def get_audio_devices(self):
        """Get list of available audio input devices."""
        import pyaudio
        devices = []
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev['maxInputChannels'] > 0:
                devices.append((i, dev['name']))
        p.terminate()
        return devices
    
    def create_device_menu(self):
        """Create submenu for microphone selection."""
        devices = self.get_audio_devices()
        items = []
        for idx, name in devices:
            items.append(
                MenuItem(
                    f"{name}",
                    lambda _, i=idx: self.app.select_device(i),
                    checked=lambda item, i=idx: self.app.current_device == i
                )
            )
        return Menu(*items)
    
    def create_config_menu(self):
        """Create submenu for configuration options."""
        return Menu(
            MenuItem("Open Config", self.app.open_config),
            MenuItem("Open Transcription Logs", self.app.open_transcription_logs),
            MenuItem("Open Application Logs", self.app.open_app_logs),
            MenuItem("Open Temp Audio", self.app.open_temp_audio)
        )
    
    def create_output_mode_menu(self):
        """Create submenu for output mode selection."""
        return Menu(
            MenuItem(
                "Type to Active Window",
                lambda: self.app.set_notebook_mode(False),
                checked=lambda item: not self.app.notebook_mode,
                radio=True
            ),
            MenuItem(
                "Append to Notebook",
                lambda: self.app.set_notebook_mode(True),
                checked=lambda item: self.app.notebook_mode,
                radio=True
            )
        )
    
    def create_notebook_menu(self):
        """Create submenu for notebook control."""
        return Menu(
            MenuItem("Open Notebook", self.app.open_notebook),
            MenuItem("Clear Notebook", self.app.clear_notebook)
        )
    
    def create_menu(self):
        """Create system tray menu."""
        # Determine recording label based on current state
        recording_label = "Pause Recording" if self.app.recording_enabled.is_set() else "Recording"

        # Create menu items list
        menu_items = [
            MenuItem(
                recording_label,
                self.app.toggle_recording,
                checked=lambda item: self.app.recording_enabled.is_set()
            )
        ]

        # Show "Stop Recording and Clear Queue" when recording is active
        if self.app.recording_enabled.is_set():
            menu_items.append(MenuItem("Stop Recording and Clear Queue", self.app.stop_and_clear))

        # Add remaining menu items
        menu_items.extend([
            Menu.SEPARATOR,
            MenuItem("Output To...", self.create_output_mode_menu()),
            MenuItem("Notebook", self.create_notebook_menu()),
            Menu.SEPARATOR,
            MenuItem("Select Microphone", self.create_device_menu()),
            MenuItem("Config", self.create_config_menu()),
            MenuItem("Help & Instructions", self.app.show_help),
            Menu.SEPARATOR,
            MenuItem("Quit", self.app.quit_app)
        ])

        return Menu(*menu_items)
