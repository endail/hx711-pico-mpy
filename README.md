# hx711-pico-mpy

MicroPython port of [hx711-pico-c](https://github.com/endail/hx711-pico-c).

Implemented as a [single Python file](https://raw.githubusercontent.com/endail/hx711-pico-mpy/main/src/hx711.py) which you can drop into your project.

```python
from machine import Pin
from src.hx711 import *

# 1. initalise the hx711 with pin 14 as clock pin, pin
# 15 as data pin
hx = hx711(Pin(14), Pin(15))

# 2. power up
hx.set_power(hx711.power.pwr_up)

# 3. [OPTIONAL] set gain and save it to the hx711
# chip by powering down then back up
hx.set_gain(hx711.gain.gain_128)
hx.set_power(hx711.power.pwr_down)
hx711.wait_power_down()
hx.set_power(hx711.power.pwr_up)

# 4. wait for readings to settle
hx711.wait_settle(hx711.rate.rate_10)

# 5. read values

# wait (block) until a value is read
val = hx.get_value()

# or use a timeout
if val := hx.get_value_timeout(250000):
    # value was obtained within the timeout period
    # in this case, within 250 milliseconds
    print(val)

# or see if there's a value, but don't block if not
if val := hx.get_value_noblock():
    print(val)

# 6. stop communication with HX711
hx.close()

```

## Alternatively, Use `with`

```python
with hx711(Pin(14), Pin(15)) as hx:
    hx.set_power(hx711.power.pwr_up)
    hx.set_gain(hx711.gain.gain_128)
    hx711.wait_settle(hx711.rate.rate_10)
    print(hx.get_value())
```
