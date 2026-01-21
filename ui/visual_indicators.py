#!/usr/bin/env python3
"""
Visual Indicators Module

Handles visual indicators for recording state including animations and overlays.
"""

import threading
import time
import sys
import pyautogui


class VisualIndicators:
    """
    Handles visual indicators for recording state.
    """
    
    def __init__(self, config):
        self.config = config
        self.pygame_lock = threading.Lock()
        self.overlay_window = None
        self.stop_indicator = threading.Event()
        self.indicator_thread = None
        self.notebook_mode = False
    
    def start_animation(self):
        """Animate the overlay circle expanding from cursor when recording starts."""
        if not self.config["visual"]["animation_enabled"]:
            return

        # Prevent concurrent pygame operations
        if not self.pygame_lock.acquire(blocking=False):
            print("Animation already running, skipping")
            return

        try:
            import pygame
            import math

            # Ensure pygame is initialized with proper error handling for executable environment
            try:
                if not pygame.get_init():
                    # Set environment variable to help pygame find SDL in executable
                    import os
                    if hasattr(sys, '_MEIPASS'):
                        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
                        os.environ['SDL_VIDEODRIVER'] = 'windib'
                    pygame.init()
            except Exception as init_error:
                print(f"Pygame initialization failed: {init_error}")
                print("Animations will be disabled. Try running as administrator.")
                return

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
                # Make window closable by adding close button
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE,
                                    win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE) | win32con.WS_SYSMENU)
            except Exception as win_error:
                print(f"Window transparency setup failed: {win_error}")
                print("Animation will continue without transparency effects")

            # Get cursor position
            x, y = pyautogui.position()
            offset = size // 2

            if 'hwnd' in locals():
                try:
                    win32gui.SetWindowPos(hwnd, -1, x - offset, y - offset, 0, 0, 1)
                except:
                    pass

            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            color = self.config["visual"]["overlay_color"]
            alpha = self.config["visual"]["overlay_alpha"]
            animation_duration = self.config["visual"]["animation_speed"]

            frames = int(animation_duration * 30)
            clock = pygame.time.Clock()

            for frame in range(frames):
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        break
                    # Handle window close events
                    if event.type == pygame.WINDOWCLOSE:
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
                clock.tick(20)

        except Exception as e:
            print(f"Error in start animation: {e}")
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
            print("Animation already running, skipping")
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
                # Make window closable by adding close button
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE,
                                    win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE) | win32con.WS_SYSMENU)
            except:
                pass
            
            # Get cursor position
            x, y = pyautogui.position()
            offset = size // 2
            
            if 'hwnd' in locals():
                win32gui.SetWindowPos(hwnd, -1, x - offset, y - offset, 0, 0, 1)
            
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            color = self.config["visual"]["overlay_color"]
            alpha = self.config["visual"]["overlay_alpha"]
            animation_duration = self.config["visual"]["animation_speed"]
            
            frames = int(animation_duration * 30)
            clock = pygame.time.Clock()

            for frame in range(frames):
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        break
                    # Handle window close events
                    if event.type == pygame.WINDOWCLOSE:
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
                clock.tick(15)
            
        except Exception as e:
            print(f"Error in stop animation: {e}")
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

                # Make window closable by adding close button
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE,
                                    win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE) | win32con.WS_SYSMENU)

            except ImportError:
                print("win32gui not available, overlay may not be fully transparent")
            except Exception as e:
                print(f"Could not set window transparency: {e}")
            
            return window
            
        except Exception as e:
            print(f"Error creating overlay: {e}")
            return None
    
    def pulse_overlay(self):
        """Animate the overlay with a smooth pulsing effect using pygame."""
        import math
        
        try:
            import pygame
        except ImportError:
            print("pygame not installed. Install with: pip install pygame pywin32")
            return
        
        # Acquire lock to prevent conflicts with animations
        if not self.pygame_lock.acquire(blocking=True, timeout=2):
            print("Could not acquire pygame lock for overlay")
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
            
            # Choose color and shape based on notebook mode
            if self.notebook_mode:
                color_tuple = self.config["visual"]["notebook_indicator_color"]
                shape_type = self.config["visual"]["notebook_indicator_shape"]
            else:
                color_tuple = self.config["visual"]["overlay_color"]
                shape_type = "circle"
            
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
                    # Handle window close events
                    if event.type == pygame.WINDOWCLOSE:
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

                    # Draw different shapes based on mode
                    if shape_type == "square":
                        # Draw square/diamond shape for notebook mode
                        half_size = radius
                        rect = pygame.Rect(center[0] - half_size, center[1] - half_size, half_size * 2, half_size * 2)
                        pygame.draw.rect(surface, color_with_alpha, rect, thickness)
                    else:
                        # Draw circle for normal mode
                        pygame.draw.circle(surface, color_with_alpha, center, radius, thickness)

                window.fill((0, 0, 0))
                window.blit(surface, (0, 0))
                pygame.display.flip()

                t += (2 * math.pi) / (pulse_speed * 30)
                if t > 2 * math.pi:
                    t -= 2 * math.pi

                clock.tick(30)
            
        except Exception as e:
            print(f"Error in pulse overlay: {e}")
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
    
    def set_notebook_mode(self, enabled):
        """Set notebook mode for visual indicators."""
        self.notebook_mode = enabled
    
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
                print("Indicator thread did not stop cleanly")

    def set_endpoint_status(self, healthy):
        """Set API endpoint status indicator."""
        # This method can be extended to provide visual feedback about endpoint health
        # For now, we'll just log it, but it could trigger visual changes in the future
        if healthy:
            print("API endpoint status: Healthy")
        else:
            print("API endpoint status: Unhealthy - transcriptions may be delayed")
