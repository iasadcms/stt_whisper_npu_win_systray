#!/usr/bin/env python3
"""
Icon Effects Module

Handles tray icon visual effects including glow effects and state updates.
"""

import threading
import time
from PIL import ImageDraw


class IconEffects:
    """
    Handles visual effects for the tray icon.
    """
    
    def __init__(self, app):
        """
        Initialize the IconEffects with the main application instance.
        
        Args:
            app: The main TranscriptionApp instance
        """
        self.app = app
        self.glow_phase = 0.0
        self.glow_direction = 0.1111  # Step size for 10 shades over fade (1.0 / 9 steps)
        self.glow_timer = None
        self.glow_active = False
        self.glow_pause_counter = 0  # Counter for pause duration
        self.glow_pause_frames = 10  # 10 frames * 25ms = 250ms pause
    
    def update_icon(self):
        """
        Update the tray icon to reflect recording state (throttled).
        """
        if not self.app.icon:
            return
         
        current_state = self.app.recording_enabled.is_set()
        current_color = self.app.get_current_indicator_color()
         
        # Only update if state or color actually changed
        with self.app.icon_update_lock:
            if self.app.last_icon_state == current_state and self.app.last_icon_color == current_color:
                return
            self.app.last_icon_state = current_state
            self.app.last_icon_color = current_color
         
        # Schedule icon update in a separate thread to avoid blocking
        def delayed_update():
            try:
                # Import here to avoid circular imports
                from ui.logo import create_built_in_microphone_icon
                 
                if current_state:
                    # Recording - use custom color
                    icon = create_built_in_microphone_icon(recording=True, custom_color=current_color)
                    draw = ImageDraw.Draw(icon)
                    indicator_color = tuple(current_color) if isinstance(current_color, list) else current_color
                    darker = tuple(int(c * 0.8) for c in indicator_color)
                    draw.ellipse([52, 4, 62, 14], fill=indicator_color, outline=darker, width=1)
                else:
                    # Idle - use default green
                    icon = create_built_in_microphone_icon(recording=False)
                    if not self.app.endpoint_healthy or self.app.visual_indicators.endpoint_checking:
                        draw = ImageDraw.Draw(icon)
                        indicator_color = tuple(current_color) if isinstance(current_color, list) else current_color
                        darker = tuple(int(c * 0.8) for c in indicator_color)
                        draw.ellipse([52, 4, 62, 14], fill=indicator_color, outline=darker, width=1)
                 
                self.app.icon.icon = icon
            except Exception as e:
                # Silently ignore icon update errors - they're not critical
                pass
         
        threading.Thread(target=delayed_update, daemon=True).start()
    
    def update_glowing_icon(self):
        """
        Update the tray icon with glowing effect for recording state.
        """
        if not self.app.icon:
            return
            
        if not (self.app.recording_enabled.is_set() or self.app.buffer_draining.is_set()):
            return
            
        # Update glow phase for next frame
        self.glow_phase += self.glow_direction
        if self.glow_phase >= 1.0:
            self.glow_phase = 1.0
            self.glow_direction = -0.12  # Reverse direction
        elif self.glow_phase <= 0.0:
            self.glow_phase = 0.0
            self.glow_direction = 0.12  # Forward direction
  
        # Update icon on every frame for maximum smoothness
        try:
            # Import here to avoid circular imports
            from ui.logo import create_built_in_microphone_icon
  
            # Get current indicator color (includes endpoint status)
            current_color = self.app.get_current_indicator_color()
              
            # Create icon with current glow phase and color
            glow_icon = create_built_in_microphone_icon(recording=True, glow_phase=self.glow_phase, custom_color=current_color)
  
            # Add recording indicator (use endpoint color if available)
            draw = ImageDraw.Draw(glow_icon)
            # Ensure indicator_color is a tuple, not a list (config returns lists)
            if current_color:
                indicator_color = tuple(current_color) if isinstance(current_color, list) else current_color
            else:
                indicator_color = (255, 50, 50)
            draw.ellipse([52, 4, 62, 14], fill=indicator_color, outline=(200, 0, 0), width=1)
  
            self.app.icon.icon = glow_icon
        except Exception as e:
            # If icon update fails, just continue - don't crash the glow effect
            pass
    
    def start_glow_effect(self):
        """
        Start the glowing icon effect.
        """
        if not self.glow_active and (self.app.recording_enabled.is_set() or self.app.buffer_draining.is_set()):
            self.glow_active = True
            self.glow_phase = 0.0
            self.glow_direction = 0.12  # Step size for 2.5 second glow cycle (0.15s sleep * ~8.33 frames per half-cycle)
            
            # Start timer to update icon periodically
            def glow_update_loop():
                while self.glow_active and self.app.running.is_set():
                    # Continue glowing if either recording or buffer draining is active
                    if not (self.app.recording_enabled.is_set() or self.app.buffer_draining.is_set()):
                        break
                    
                    self.update_glowing_icon()
                    time.sleep(0.15)  # Increased to 150ms for maximum keyboard compatibility
            
            self.glow_timer = threading.Thread(target=glow_update_loop, daemon=True)
            self.glow_timer.start()
    
    def stop_glow_effect(self):
        """
        Stop the glowing icon effect.
        """
        self.glow_active = False
        if self.glow_timer:
            self.glow_timer.join(timeout=0.5)  # Give it a chance to stop
            self.glow_timer = None
        # Reset to normal recording icon
        if self.app.recording_enabled.is_set():
            self.update_icon()
