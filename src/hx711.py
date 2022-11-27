# MIT License
# 
# Copyright (c) 2022 Daniel Robertson
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import time
import rp2
import _thread
from machine import Pin
from util import util

class hx711_rate:
    rate_10 = 0
    rate_80 = 1

class hx711_gain:
    gain_128 = 25
    gain_32 = 26
    gain_64 = 27

class hx711_power:
    pwr_up = 0
    pwr_down = 1

class hx711_pio_prog:
    def init():
        pass
    def program():
        pass

class hx711:

    READ_BITS: int = 24
    MIN_VALUE: int = -0x800000
    MAX_VALUE: int = 0x7fffff
    POWER_DOWN_TIMEOUT: int = 60 #us
    SETTLING_TIMES: int = [
        400,
        50
    ]
    SAMPLES_RATES: int = [
        10,
        80
    ]

    def __init__(
        self,
        clk: Pin,
        dat: Pin,
        pio_offset: int, # either 0 or 1
        sm_offset: int, # 0 - 3
        prog: hx711_pio_prog
    ):

        self._mut = _thread.allocate_lock()
        self._mut.acquire()

        self.clock_pin = clk
        self.data_pin = dat
        self.clock_pin.init(mode=Pin.OUT)
        self.data_pin.init(mode=Pin.IN)

        self._pio_offset = pio_offset
        self._sm_offset = sm_offset
        self._state_mach = None

        prog.init(self)

        self._mut.release()

    def close(self):
        self._mut.acquire()
        self._state_mach.active(0)
        rp2.PIO(self._pio_offset).remove_program(self._prog.program)
        self._mut.release()

    def set_gain(self, gain: hx711_gain):
        self._mut.acquire()
        util.sm_drain_tx_fifo(self._state_mach)
        self._state_mach.put(gain)
        self._state_mach.get()
        util.sm_get_blocking(self._state_mach)
        self._mut.release()

    @classmethod
    def get_twos_comp(cls, raw: int):
        return -(raw & 0x800000) + (raw & 0x7fffff)

    @classmethod
    def is_min_saturated(cls, val: int):
        return val == cls.MIN_VALUE

    @classmethod
    def is_max_saturated(cls, val: int):
        return val == cls.MAX_VALUE

    @classmethod
    def get_settling_time(cls, rate: hx711_rate):
        return cls.SETTLING_TIMES[rate]

    @classmethod
    def get_rate_sps(cls, rate: hx711_rate):
        return cls.SAMPLE_RATES[rate]

    def get_value(self):
        self._mut.acquire()
        rawVal = util.sm_get_blocking(self._state_mach)
        self._mut.release()
        return self.get_twos_comp(rawVal)

    def get_value_timeout(self, timeout: int):

        endTime = time.ticks_us() + timeout
        val = None

        self._mut.acquire()

        while(time.ticks_us() < endTime):
            val = self.__try_get_value()
            if val != None:
                break

        self._mut.release()

        if val != None:
            return self.get_twos_comp(val)

        return None

    def get_value_noblock(self):

        self._mut.acquire()
        val = self.__try_get_value()
        self._mut.release()
        
        if val != None:
            return self.get_twos_comp(val)

        return None

    def set_power(self, pwr: hx711_power):

        self._mut.acquire()

        if pwr == hx711_power.pwr_up:
            self.clock_pin.value(0)
            self._state_mach.restart()
            self._state_mach.active(1)

        elif pwr == hx711_power.pwr_down:
            self._state_mach.active(0)
            self.clock_pin.value(1)

        self._mut.release()

    @classmethod
    def wait_settle(cls, rate: hx711_rate):
        time.sleep_ms(cls.get_settling_time(rate))

    @classmethod
    def wait_power_down(cls):
        time.sleep_us(cls.POWER_DOWN_TIMEOUT)

    def __try_get_value(self):
        if self._state_mach.rx_fifo() >= self.READ_BITS / 8:
            return self._state_mach.get()
        return None
