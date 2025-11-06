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

    def set_pixel_color(self, i: int, color: Color) -> None:
        """
        Set the color of a single pixel in the buffer. It is not written to the LED strip until show() is called.
        :param i: The index of the pixel
        :param color: The color to set the pixel to
        """
        self._pixels[i] = color

    def show(self) -> None:
        """
        Write the current pixel colors to the LED strip.
        Note: Brightness is NOT applied here - it should be pre-applied in the color values
        to avoid double-scaling when used with led-control's render functions.
        """
        if self._has_white:
            # RGBW: 4 bytes per pixel (G, R, B, W order for SK6812)
            buffer = np.array(
                [
                    np.array([pixel.g, pixel.r, pixel.b, pixel.w])
                    for pixel in self._pixels
                ],
                dtype=np.uint8,
            )
        else:
            # RGB: 3 bytes per pixel (G, R, B order for WS2812)
            buffer = np.array(
                [
                    np.array([pixel.g, pixel.r, pixel.b])
                    for pixel in self._pixels
                ],
                dtype=np.uint8,
            )
        self._backend.write(buffer)

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

    def __init__(self, spi_bus: int, spi_device: int, led_count: int, has_white: bool = False):
        """
        Initialize the SPI driver.
        :param spi_bus: SPI bus number (usually 0)
        :param spi_device: SPI device number (usually 0)
        :param led_count: Number of LEDs in the strip
        :param has_white: True for SK6812-RGBW (4 bytes per pixel), False for WS2812 (3 bytes per pixel)
        """
        super().__init__(has_white)
        
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

    def _encode_byte_to_spi(self, byte_val: int) -> bytes:
        """
        Encode one data byte (8 bits) to SPI format.
        Each data bit becomes 3 SPI bits:
        - 1 -> 110 (high for ~0.8us, low for ~0.4us at 2.4MHz)
        - 0 -> 100 (high for ~0.4us, low for ~0.8us at 2.4MHz)
        
        Returns 3 bytes (24 SPI bits for 8 data bits)
        """
        # Build bit string: each data bit -> 3 SPI bits
        bit_string = ''
        for i in range(7, -1, -1):  # MSB first
            bit = (byte_val >> i) & 1
            if bit:
                bit_string += '110'  # LED_ONE
            else:
                bit_string += '100'  # LED_ZERO
        
        # Convert 24-bit string to 3 bytes
        packed = bytearray(3)
        for i in range(3):
            packed[i] = int(bit_string[i*8:(i+1)*8], 2)
        
        return bytes(packed)

    def write(self, buffer: np.ndarray) -> None:
        """
        Write colors to the LED strip.
        
        Note: SK6812/WS2812 require >50µs reset time between frames, but this is
        automatically satisfied by normal animation frame rates (typically 30-60 FPS).
        No artificial delay needed.
        
        :param buffer: A 2D numpy array of shape (num_leds, 3) for RGB or (num_leds, 4) for RGBW
                       where the last dimension is the GRB or GRBW values
        """
        # Build SPI buffer: preamble + encoded color data
        spi_data = bytearray(WS2812SpiDriver.PREAMBLE)
        
        # Encode each byte of color data
        flattened_colors = buffer.ravel()
        for byte_val in flattened_colors:
            spi_data.extend(self._encode_byte_to_spi(byte_val))
        
        self._device.writebytes2(spi_data)

    def clear(self) -> None:
        """Reset all LEDs to off"""
        self._device.writebytes2(self._clear_buffer)

    def get_led_count(self) -> int:
        return self._led_count
