# WS2812/SK6812-RGBW interface for the Raspberry Pi 5

This is a simple interface for WS2812 (RGB) and SK6812-RGBW LED strips for the Raspberry Pi 5.
Supports both 3-byte RGB and 4-byte RGBW pixel formats via the SPI interface.

This library was created for the Raspberry Pi 5 because the previous go-to library [rpi_ws281x](https://github.com/jgarff/rpi_ws281x) is not (yet?) compatible. It should work on other Raspberry Pi models as well, but this has not been tested.

Thanks to [this repository](https://github.com/mattaw/ws2812_spi_python/) for the research on the SPI communication.

## Features

- ✅ **RGB Support**: WS2812, WS2812B (3 bytes per pixel: GRB)
- ✅ **RGBW Support**: SK6812-RGBW (4 bytes per pixel: GRBW)
- ✅ **Brightness Control**: Software brightness adjustment
- ✅ **SPI Interface**: Fast communication via Raspberry Pi SPI
- ✅ **Simple API**: Easy to use Python interface

## Preparation

Enable SPI on the Raspberry Pi 5:

```bash
sudo raspi-config
```

Navigate to `Interfacing Options` -> `SPI` and enable it.

Optional: add your user to the `spi` group to avoid running the script as root:

```bash
sudo adduser YOUR_USER spidev
```

## Installation

```bash
pip install rpi5-ws2812-rgbw
```

## Wiring

Connect the DIN (Data In) pin of the LED strip to the MOSI (Master Out Slave In) pin of the Raspberry Pi 5. The MOSI pin is pin 19 / GPIO10 on the Raspberry Pi 5.

## Usage

### RGB LEDs (WS2812/WS2812B)

```python
from rpi5_ws2812.ws2812 import Color, WS2812SpiDriver
import time

if __name__ == "__main__":
    # Initialize for RGB LEDs (WS2812/WS2812B)
    driver = WS2812SpiDriver(spi_bus=0, spi_device=0, led_count=100, has_white=False)
    strip = driver.get_strip()
    
    while True:
        strip.set_all_pixels(Color(255, 0, 0))  # Red
        strip.show()
        time.sleep(2)
        strip.set_all_pixels(Color(0, 255, 0))  # Green
        strip.show()
        time.sleep(2)
        strip.set_all_pixels(Color(0, 0, 255))  # Blue
        strip.show()
        time.sleep(2)
```

### RGBW LEDs (SK6812-RGBW)

```python
from rpi5_ws2812.ws2812 import Color, WS2812SpiDriver
import time

if __name__ == "__main__":
    # Initialize for RGBW LEDs (SK6812-RGBW)
    driver = WS2812SpiDriver(spi_bus=0, spi_device=0, led_count=144, has_white=True)
    strip = driver.get_strip()
    
    while True:
        strip.set_all_pixels(Color(255, 0, 0, 0))    # Red
        strip.show()
        time.sleep(2)
        strip.set_all_pixels(Color(0, 255, 0, 0))    # Green
        strip.show()
        time.sleep(2)
        strip.set_all_pixels(Color(0, 0, 255, 0))    # Blue
        strip.show()
        time.sleep(2)
        strip.set_all_pixels(Color(0, 0, 0, 255))    # Pure White
        strip.show()
        time.sleep(2)
        strip.set_all_pixels(Color(255, 255, 255, 0)) # RGB White
        strip.show()
        time.sleep(2)
```

### Brightness Control

```python
from rpi5_ws2812.ws2812 import Color, WS2812SpiDriver

driver = WS2812SpiDriver(spi_bus=0, spi_device=0, led_count=100, has_white=False)
strip = driver.get_strip()

# Set brightness to 50%
strip.set_brightness(0.5)

strip.set_all_pixels(Color(255, 0, 0))
strip.show()  # LEDs will be at 50% brightness
```

## Use this library in a docker container

To use this library in a docker container, you need to add the `--device` flag to the `docker run` command to give the container access to the SPI interface. You also need to run the container in privileged mode.

Example:

```bash
docker run --device /dev/spidev0.0 --privileged YOUR_IMAGE
```

```yaml
services:
  your_service:
    image: YOUR_IMAGE
    privileged: true
    devices:
      - /dev/spidev0.0
```
