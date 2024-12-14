from src.hx711 import *

'''
By default, hx711_i2c uses:
 - pin 5 as the clock
 - pin 4 for data
 - 100000 as the baud rate/frequency
 - 0x64 as the slave address
 - I2C instance 0
'''

hx = hx711_i2c()
hx.power_up(hx711.gain.gain_128, hx711.rate.rate_80)
hx711.wait_settle(hx711.rate.rate_80)

for _ in range(1000):
    print(hx.get_value_blocking())

hx.power_down()
hx.close()
hx711.wait_power_down()

# or use with:

with hx711_i2c() as hx:
    hx.power_up(hx711.gain.gain_128, hx711.rate.rate_80)
    hx711.wait_settle(hx711.rate.rate_80)
    for _ in range(1000):
        print(hx.get_value_blocking())
