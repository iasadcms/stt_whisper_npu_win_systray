#!/usr/bin/env python3
"""
Logo Module

Handles logo loading and icon creation for the user interface.
"""

from PIL import Image, ImageDraw

# =============================================
# CUSTOMIZABLE GLOW EFFECT SETTINGS
# =============================================

# Recording state colors (fade between these)
RECORDING_BASE_COLOR = (100, 20, 20)    # Much darker red for stronger contrast
RECORDING_GLOW_COLOR = (255, 80, 80)    # Brighter red for more visible glow

# Idle state colors
IDLE_COLOR = (100, 200, 100)            # Green
IDLE_OUTLINE = (60, 150, 60)            # Darker green outline

# Glow effect timing (in seconds)
GLOW_FADE_DURATION = 1.6                 # Duration for fade in each direction
GLOW_PAUSE_DURATION = 0.25               # Pause duration at peak and trough

# Number of distinct color shades during fade
GLOW_SHADES = 10

def create_built_in_microphone_icon(size=64, color=(0, 120, 215), outline=(0, 80, 160), recording=False, glow_phase=0.0, custom_color=None):
    """
    Create a built-in microphone icon using the previously designed
    rounded microphone shape.

    Args:
        size: Icon size in pixels
        color: Fill color (RGB tuple)
        outline: Outline color (RGB tuple)
        recording: Whether recording is active (for color selection)
        glow_phase: Phase for glowing effect (0.0 to 1.0)
        custom_color: Optional custom color tuple (RGB) to override default colors

    Returns:
        PIL Image of microphone icon
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    scale = size / 64

    def s(x):
        return int(x * scale)

    # Microphone head (rounded rectangle)
    # Use brighter, more visible colors
    if recording:
        # If custom color provided, use it with glow effect
        if custom_color:
            base_color = tuple(int(c * 0.7) for c in custom_color)  # Darker base
            glow_color = custom_color  # Brighter glow
        else:
            # Glowing effect between two shades with greater range
            base_color = RECORDING_BASE_COLOR  # Darker base color
            glow_color = RECORDING_GLOW_COLOR  # Much brighter glow color

        # Use a smoother curve for the glow effect (ease-in-out)
        # Apply easing function to make transition smoother
        if glow_phase < 0.5:
            # Ease in (quadratic)
            eased_phase = 2 * glow_phase * glow_phase
        else:
            # Ease out (quadratic)
            eased_phase = 1 - 2 * (1 - glow_phase) * (1 - glow_phase)

        # Interpolate between the two colors based on eased glow phase
        fill_color = (
            int(base_color[0] + (glow_color[0] - base_color[0]) * eased_phase),
            int(base_color[1] + (glow_color[1] - base_color[1]) * eased_phase),
            int(base_color[2] + (glow_color[2] - base_color[2]) * eased_phase)
        )
        outline_color = (
            int(fill_color[0] * 0.6),
            int(fill_color[1] * 0.6),
            int(fill_color[2] * 0.6)
        )
    else:
        fill_color = IDLE_COLOR  # Green for idle state
        outline_color = IDLE_OUTLINE  # Darker green outline

    draw.rounded_rectangle(
        [s(16), s(6), s(48), s(46)],
        radius=s(12),
        fill=fill_color,
        outline=outline_color,
        width=s(2)
    )

    # Grill lines
    for y in range(14, 44, 4):
        draw.line(
            [(s(22), s(y)), (s(42), s(y))],
            fill=outline_color,
            width=s(1)
        )

    # Stem
    draw.rectangle(
        [s(30), s(46), s(34), s(56)],
        fill=fill_color,
        outline=outline_color
    )

    # Base curve
    draw.arc(
        [s(18), s(52), s(46), s(66)],
        start=0,
        end=180,
        fill=outline,
        width=s(2)
    )

    # Base stand
    draw.rectangle(
        [s(24), s(60), s(40), s(62)],
        fill=fill_color,
        outline=outline_color
    )

    return img

def get_windows_microphone_icon(recording=False):
    """
    Get a built-in microphone icon.

    Args:
        recording: Whether recording is active

    Returns:
        PIL Image of microphone icon or None if creation fails
    """
    try:
        return create_built_in_microphone_icon(recording=recording)
    except Exception as e:
        return None

def load_logo():
    """
    Load microphone icons (recording and idle states).

    Returns:
        Tuple of (recording_icon, idle_icon)
    """
    # Load both recording and non-recording versions for microphone icon
    recording_mic = get_windows_microphone_icon(recording=True)
    idle_mic = get_windows_microphone_icon(recording=False)

    if recording_mic and idle_mic:
        return recording_mic, idle_mic
    else:
        return None, None

def create_icon_image(logo, gray_logo, recording=False):
    """
    Create system tray icon image.

    Args:
        logo: Recording state icon image
        gray_logo: Idle state icon image
        recording: Whether recording is active

    Returns:
        PIL Image for tray icon
    """
    if logo is not None:
        img = logo.copy() if recording else gray_logo.copy()
        if recording:
            draw = ImageDraw.Draw(img)
            # Brighter red recording indicator (top-right) for better visibility
            draw.ellipse([52, 4, 62, 14], fill=(255, 50, 50), outline=(200, 0, 0), width=1)
        return img
    else:
        # This should never happen since we always generate icons
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Default fallback microphone shape
        fill = (0, 180, 255) if recording else (100, 100, 255)
        outline = (0, 120, 200) if recording else (60, 60, 180)

        draw.ellipse([16, 6, 48, 46], fill=fill, outline=outline)
        draw.rectangle([30, 46, 34, 56], fill=fill, outline=outline)
        draw.ellipse([26, 52, 38, 62], fill=fill, outline=outline)

        return image.convert('RGB')

__all__ = [
    'load_logo',
    'create_icon_image',
    'get_windows_microphone_icon',
    'RECORDING_BASE_COLOR',
    'RECORDING_GLOW_COLOR',
    'IDLE_COLOR',
    'IDLE_OUTLINE',
    'GLOW_FADE_DURATION',
    'GLOW_PAUSE_DURATION',
    'GLOW_SHADES'
]
