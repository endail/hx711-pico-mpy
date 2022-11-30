from machine import Pin
from src.hx711 import *

# 1. initalise the hx711
hx = hx711(Pin(4), Pin(5))

# 2. power up
hx.set_power(hx711_power.pwr_up)

# 3. [OPTIONAL] set gain and save it to the hx711
# chip by powering down then back up
hx.set_gain(hx711_gain.gain_128)
hx.set_power(hx711_power.pwr_down)
hx711.wait_power_down()
hx.set_power(hx711_power.pwr_up)

# 4. wait for readings to settle
hx711.wait_settle(hx711_rate.rate_10)

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
