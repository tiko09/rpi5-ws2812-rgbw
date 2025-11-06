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
        """
        if self._has_white:
            # RGBW: 4 bytes per pixel (G, R, B, W order for SK6812)
            buffer = np.array(
                [
                    np.array([
                        pixel.g * self._brightness,
                        pixel.r * self._brightness,
                        pixel.b * self._brightness,
                        pixel.w * self._brightness
                    ])
                    for pixel in self._pixels
                ],
                dtype=np.uint8,
            )
        else:
            # RGB: 3 bytes per pixel (G, R, B order for WS2812)
            buffer = np.array(
                [
                    np.array([
                        pixel.g * self._brightness,
                        pixel.r * self._brightness,
                        pixel.b * self._brightness
                    ])
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
    """

    # WS2812 timings. Thanks to https://github.com/mattaw/ws2812_spi_python
    LED_ZERO: int = 0b1100_0000
    LED_ONE: int = 0b1111_1100
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

        self._device.max_speed_hz = 6_500_000
        self._device.mode = 0b00
        self._device.lsbfirst = False

        self._led_count = led_count
        
        # Calculate bits per pixel: RGB = 3 bytes * 8 bits = 24, RGBW = 4 bytes * 8 bits = 32
        self._bits_per_pixel = 32 if has_white else 24
        
        # Initialize clear buffer with correct size
        self._clear_buffer = np.zeros(
            WS2812SpiDriver.PREAMBLE + led_count * self._bits_per_pixel, 
            dtype=np.uint8
        )
        self._clear_buffer[WS2812SpiDriver.PREAMBLE:] = np.full(
            led_count * self._bits_per_pixel, 
            WS2812SpiDriver.LED_ZERO, 
            dtype=np.uint8
        )

        # Initialize main buffer
        self._buffer = np.zeros(
            WS2812SpiDriver.PREAMBLE + led_count * self._bits_per_pixel, 
            dtype=np.uint8
        )

    def write(self, buffer: np.ndarray) -> None:
        """
        Write colors to the LED strip
        :param buffer: A 2D numpy array of shape (num_leds, 3) for RGB or (num_leds, 4) for RGBW
                       where the last dimension is the GRB or GRBW values
        """
        flattened_colors = buffer.ravel()
        color_bits = np.unpackbits(flattened_colors)
        self._buffer[WS2812SpiDriver.PREAMBLE:] = np.where(
            color_bits == 1, WS2812SpiDriver.LED_ONE, WS2812SpiDriver.LED_ZERO
        )
        self._device.writebytes2(self._buffer)

    def clear(self) -> None:
        """
        Reset all LEDs to off"""
        self._device.writebytes2(self._clear_buffer)

    def get_led_count(self) -> int:
        return self._led_count
