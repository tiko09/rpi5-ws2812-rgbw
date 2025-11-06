from abc import ABC, abstractmethod

import numpy as np
from spidev import SpiDev


class Color:
    """
    A class to represent an RGB or RGBW color.
    For RGB LEDs, the white channel is ignored.
    For RGBW LEDs, all four channels are used.
    """
    __slots__ = ('r', 'g', 'b', 'w')
    
    def __init__(self, r: int, g: int, b: int, w: int = 0):
        """
        Initialize a color.
        :param r: Red channel (0-255)
        :param g: Green channel (0-255)
        :param b: Blue channel (0-255)
        :param w: White channel (0-255), default 0 for RGB compatibility
        """
        self.r = r
        self.g = g
        self.b = b
        self.w = w
    
    def __repr__(self):
        if self.w > 0:
            return f"Color(r={self.r}, g={self.g}, b={self.b}, w={self.w})"
        return f"Color(r={self.r}, g={self.g}, b={self.b})"
    
    def __eq__(self, other):
        if isinstance(other, Color):
            return self.r == other.r and self.g == other.g and self.b == other.b and self.w == other.w
        return False
    
    def __iter__(self):
        """Allow unpacking: r, g, b, w = color"""
        return iter((self.r, self.g, self.b, self.w))


class Strip:
    """
    A class to control a WS2812 LED strip (RGB or RGBW).
    """

    def __init__(self, backend: "WS2812StripDriver", has_white: bool = False):
        """
        Initialize the LED strip.
        :param backend: The driver backend to use
        :param has_white: True for RGBW LEDs (SK6812-RGBW), False for RGB LEDs (WS2812/WS2812B)
        """
        self._led_count = backend.get_led_count()
        self._brightness = 1.0
        self._has_white = has_white
        self._pixels: list[Color] = [Color(0, 0, 0, 0)] * self._led_count
        self._backend = backend
        
        # Pre-allocate NumPy buffer for fast pixel-to-array conversion
        if has_white:
            self._pixel_buffer = np.zeros((self._led_count, 4), dtype=np.uint8)
        else:
            self._pixel_buffer = np.zeros((self._led_count, 3), dtype=np.uint8)

    def set_pixel_color(self, i: int, color: Color) -> None:
        """
        Set the color of a single pixel in the buffer. It is not written to the LED strip until show() is called.
        :param i: The index of the pixel
        :param color: The color to set the pixel to
        """
        self._pixels[i] = color
    
    def set_pixels_batch(self, start: int, colors: list) -> None:
        """
        Set multiple pixels at once (batch operation for performance).
        :param start: Starting index
        :param colors: List of Color objects or tuples (r, g, b, w) or (r, g, b)
        """
        for i, color in enumerate(colors):
            idx = start + i
            if idx >= self._led_count:
                break
            if isinstance(color, Color):
                self._pixels[idx] = color
            elif isinstance(color, (tuple, list)):
                # Support both (r,g,b) and (r,g,b,w) tuples
                if len(color) >= 4:
                    self._pixels[idx] = Color(color[0], color[1], color[2], color[3])
                else:
                    self._pixels[idx] = Color(color[0], color[1], color[2], 0)
            else:
                raise ValueError(f"Invalid color type: {type(color)}")
    
    def set_pixels_array(self, start: int, rgbw_array: np.ndarray) -> None:
        """
        Set multiple pixels from a NumPy array (fastest batch operation).
        :param start: Starting index
        :param rgbw_array: NumPy array of shape (n, 3) for RGB or (n, 4) for RGBW, dtype uint8
        """
        n_pixels = len(rgbw_array)
        end = min(start + n_pixels, self._led_count)
        n_actual = end - start
        
        if rgbw_array.shape[1] == 4:
            # RGBW array
            for i in range(n_actual):
                self._pixels[start + i] = Color(
                    int(rgbw_array[i, 0]),
                    int(rgbw_array[i, 1]),
                    int(rgbw_array[i, 2]),
                    int(rgbw_array[i, 3])
                )
        elif rgbw_array.shape[1] == 3:
            # RGB array
            for i in range(n_actual):
                self._pixels[start + i] = Color(
                    int(rgbw_array[i, 0]),
                    int(rgbw_array[i, 1]),
                    int(rgbw_array[i, 2]),
                    0
                )
        else:
            raise ValueError(f"Invalid array shape: {rgbw_array.shape}. Expected (n, 3) or (n, 4)")


    def show(self) -> None:
        """
        Write the current pixel colors to the LED strip.
        Note: Brightness is NOT applied here - it should be pre-applied in the color values
        to avoid double-scaling when used with led-control's render functions.
        
        OPTIMIZED: Uses pre-allocated buffer and vectorized operations.
        """
        # Fast path: Copy pixel data to pre-allocated buffer
        # This is MUCH faster than list comprehension
        for i in range(self._led_count):
            pixel = self._pixels[i]
            if self._has_white:
                # GRBW order for SK6812
                self._pixel_buffer[i, 0] = pixel.g
                self._pixel_buffer[i, 1] = pixel.r
                self._pixel_buffer[i, 2] = pixel.b
                self._pixel_buffer[i, 3] = pixel.w
            else:
                # GRB order for WS2812
                self._pixel_buffer[i, 0] = pixel.g
                self._pixel_buffer[i, 1] = pixel.r
                self._pixel_buffer[i, 2] = pixel.b
        
        self._backend.write(self._pixel_buffer)

    def clear(self) -> None:
        """
        Clear the LED strip and the buffer by setting all pixels to off.
        """
        self._pixels = [Color(0, 0, 0, 0)] * self._led_count
        self._backend.clear()

    def set_brightness(self, brightness: float) -> None:
        """
        Set the brightness of the LED strip. The brightness is a float between 0.0 and 1.0.
        """
        self._brightness = max(min(brightness, 1.0), 0.0)

    def num_pixels(self) -> int:
        """
        Get the number of pixels in the LED strip.
        :return: The number of pixels.
        """
        return self._led_count

    def get_brightness(self) -> float:
        """
        Get the current brightness of the LED strip.
        :return: The brightness as a float between 0.0 and 1.0."""
        return self._brightness

    def set_all_pixels(self, color: Color) -> None:
        """
        Set all pixels to the same color. The colors are not written to the LED strip until show() is called.
        :param color: The color to set all pixels to.
        """
        self._pixels = [color] * self._led_count
    
    def has_white_channel(self) -> bool:
        """
        Check if the strip supports white channel (RGBW).
        :return: True if RGBW, False if RGB
        """
        return self._has_white


class WS2812StripDriver(ABC):
    """
    Abstract base class for drivers
    """

    def __init__(self, has_white: bool = False):
        """
        Initialize the driver.
        :param has_white: True for RGBW LEDs, False for RGB LEDs
        """
        self._has_white = has_white

    @abstractmethod
    def write(self, colors: np.ndarray) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    @abstractmethod
    def get_led_count(self) -> int:
        pass

    def get_strip(self) -> Strip:
        return Strip(self, self._has_white)


class WS2812SpiDriver(WS2812StripDriver):
    """
    Driver for WS2812/WS2812B (RGB) and SK6812-RGBW LED strips using the SPI interface on the Raspberry Pi.
    Supports both 3-byte (RGB) and 4-byte (RGBW) pixel formats.
    
    Uses 3-bit SPI encoding per data bit at 2.4MHz SPI clock:
    - Data bit 1: SPI pattern 110 (~0.8us high, ~0.4us low)
    - Data bit 0: SPI pattern 100 (~0.4us high, ~0.8us low)
    This matches WS2812/SK6812 timing requirements.
    """

    # Bit patterns for SPI encoding (3 SPI bits per data bit)
    # At 2.4MHz SPI: each SPI bit is ~0.42us
    LED_ZERO: int = 0b100  # 0.42us high, 0.83us low
    LED_ONE: int = 0b110   # 0.83us high, 0.42us low
    PREAMBLE: int = 42
    
    # Pre-compute lookup table for SPI encoding (256 entries)
    # This avoids bit manipulation in the hot path
    _SPI_LOOKUP = None

    @classmethod
    def _init_spi_lookup(cls):
        """Initialize SPI encoding lookup table (called once)."""
        if cls._SPI_LOOKUP is not None:
            return
        
        cls._SPI_LOOKUP = []
        for byte_val in range(256):
            # Encode each bit position
            bits = []
            for i in range(7, -1, -1):  # MSB first
                bit = (byte_val >> i) & 1
                bits.append('110' if bit else '100')
            
            # Convert 24-bit string to 3 bytes
            bit_string = ''.join(bits)
            packed = bytes([
                int(bit_string[0:8], 2),
                int(bit_string[8:16], 2),
                int(bit_string[16:24], 2)
            ])
            cls._SPI_LOOKUP.append(packed)

    def __init__(self, spi_bus: int, spi_device: int, led_count: int, has_white: bool = False):
        """
        Initialize the SPI driver.
        :param spi_bus: SPI bus number (usually 0)
        :param spi_device: SPI device number (usually 0)
        :param led_count: Number of LEDs in the strip
        :param has_white: True for SK6812-RGBW (4 bytes per pixel), False for WS2812 (3 bytes per pixel)
        """
        super().__init__(has_white)
        
        # Initialize lookup table once
        WS2812SpiDriver._init_spi_lookup()
        
        self._device = SpiDev()
        self._device.open(spi_bus, spi_device)

        # 2.4MHz for 3-bit encoding (each bit ~0.42us)
        self._device.max_speed_hz = 2_400_000
        self._device.mode = 0b00
        self._device.lsbfirst = False

        self._led_count = led_count
        
        # Bytes per pixel: RGB = 3 bytes, RGBW = 4 bytes
        self._bytes_per_pixel = 4 if has_white else 3
        
        # Each data byte becomes 3 bytes in SPI (8 bits * 3 SPI bits per bit = 24 SPI bits = 3 bytes)
        # Total SPI bytes = led_count * bytes_per_pixel * 3
        spi_bytes = led_count * self._bytes_per_pixel * 3
        
        # Initialize clear buffer
        self._clear_buffer = bytearray(WS2812SpiDriver.PREAMBLE + spi_bytes)
        
        # Pre-allocate SPI buffer for performance
        self._spi_buffer = bytearray(WS2812SpiDriver.PREAMBLE + spi_bytes)

    def write(self, buffer: np.ndarray) -> None:
        """
        Write colors to the LED strip.
        
        OPTIMIZED: Uses pre-computed lookup table and pre-allocated buffer.
        
        Note: SK6812/WS2812 require >50µs reset time between frames, but this is
        automatically satisfied by normal animation frame rates (typically 30-60 FPS).
        No artificial delay needed.
        
        :param buffer: A 2D numpy array of shape (num_leds, 3) for RGB or (num_leds, 4) for RGBW
                       where the last dimension is the GRB or GRBW values
        """
        # Use pre-allocated buffer and lookup table for maximum speed
        offset = WS2812SpiDriver.PREAMBLE
        flattened_colors = buffer.ravel()
        
        # Fast lookup-based encoding (no bit manipulation in hot path)
        for byte_val in flattened_colors:
            encoded = WS2812SpiDriver._SPI_LOOKUP[byte_val]
            self._spi_buffer[offset:offset+3] = encoded
            offset += 3
        
        self._device.writebytes2(self._spi_buffer)

    def clear(self) -> None:
        """Reset all LEDs to off"""
        self._device.writebytes2(self._clear_buffer)

    def get_led_count(self) -> int:
        return self._led_count
