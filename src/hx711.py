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

import _thread
import time
import rp2
from machine import Pin
from src.util import util

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
    def __init__(self) -> None:
        pass

class hx711_noblock(hx711_pio_prog):

    PUSH_BITS: int = 24
    FREQUENCY: int = 10000000 # 10MHz, 0.1us

    def __init__(self) -> None:
        super().__init__()

    def init(self, hx) -> None:
        hx._sm = rp2.StateMachine(
            hx._sm_index,
            self.program,
            freq=self.FREQUENCY,
            in_base=hx.data_pin,
            out_base=hx.clock_pin,
            set_base=hx.clock_pin,
            jmp_pin=None,
            sideset_base=hx.clock_pin
        )

    @rp2.asm_pio(
        out_init=rp2.PIO.IN_HIGH,
        set_init=(rp2.PIO.IN_HIGH),
        sideset_init=(rp2.PIO.IN_HIGH),
        out_shiftdir=rp2.PIO.SHIFT_LEFT,
        autopush=True,
        autopull=False,
        push_thresh=PUSH_BITS,
        fifo_join=rp2.PIO.JOIN_NONE
    )
    def program():

        set(x, 0) # default gain of 0

        label("wrap_target")
        wrap_target()

        set(y, 23) # read bits, 0 based

        wait(0, pin, 0)

        label("bitloop")
        set(pins, 0)
        in_(pins, 1)

        jmp(y_dec, "bitloop").side(0) [2 - 1] # T4

        pull(noblock).side(1)

        out(x, 2)

        jmp(not_x, "wrap_target").side(0)

        mov(y, x)

        label("gainloop")
        set(pins, 1) [2 - 1] # T3
        jmp(y_dec, "gainloop").side(0) [2 - 1] # T4

        wrap()

class hx711:

    READ_BITS: int = 24
    MIN_VALUE: int = -0x800000
    MAX_VALUE: int = 0x7fffff
    POWER_DOWN_TIMEOUT: int = 60 # us
    SETTLING_TIMES: list[int] = [ # ms
        400,
        50
    ]
    SAMPLES_RATES: list[int] = [
        10,
        80
    ]

    def __init__(
        self,
        clk: Pin,
        dat: Pin,
        sm_index: int = 0,
        prog: hx711_pio_prog = hx711_noblock()
    ):
        '''
        clk: clock pin
        dat: data pin
        sm_index: state machine index
        prog: PIO program
        '''

        self._mut = _thread.allocate_lock()
        self._mut.acquire()

        self.clock_pin = clk
        self.data_pin = dat
        self.clock_pin.init(mode=Pin.OUT)
        self.data_pin.init(mode=Pin.IN)

        self._sm: rp2.StateMachine|None = None
        self._sm_index: int = sm_index
        self._prog: hx711_pio_prog = prog

        prog.init(self)

        self._mut.release()

    def close(self) -> None:
        self._mut.acquire()
        self._sm.active(0)
        util.get_pio_from_sm_index(hx._sm_index).remove_program(self._prog.program)
        self._mut.release()

    def set_gain(self, gain: int) -> None:
        self._mut.acquire()
        util.sm_drain_tx_fifo(self._sm)
        self._sm.put(gain)
        self._sm.get()
        util.sm_get_blocking(self._sm)
        self._mut.release()

    @classmethod
    def get_twos_comp(cls, raw: int) -> int:
        return -(raw & 0x800000) + (raw & 0x7fffff)

    @classmethod
    def is_min_saturated(cls, val: int) -> bool:
        return val == cls.MIN_VALUE

    @classmethod
    def is_max_saturated(cls, val: int) -> bool:
        return val == cls.MAX_VALUE

    @classmethod
    def get_settling_time(cls, rate: int) -> int:
        return cls.SETTLING_TIMES[rate]

    @classmethod
    def get_rate_sps(cls, rate: int) -> int:
        return cls.SAMPLES_RATES[rate]

    def get_value(self) -> int|None:
        self._mut.acquire()
        rawVal = util.sm_get_blocking(self._sm)
        self._mut.release()
        return self.get_twos_comp(rawVal)

    def get_value_timeout(self, timeout: int = 1000000) -> int|None:

        '''
        timeout: microseconds, 1 second by default
        '''

        endTime = time.ticks_us() + timeout
        val = None

        self._mut.acquire()

        while(time.ticks_us() < endTime):
            val = self.__try_get_value()
            if val != None: break

        self._mut.release()

        return self.get_twos_comp(val) if val else None

    def get_value_noblock(self) -> int|None:
        self._mut.acquire()
        val = self.__try_get_value()
        self._mut.release()
        return self.get_twos_comp(val) if val else None

    def set_power(self, pwr: int) -> None:

        self._mut.acquire()

        if pwr == hx711_power.pwr_up:
            self.clock_pin.value(0)
            self._sm.restart()
            self._sm.active(1)

        elif pwr == hx711_power.pwr_down:
            self._sm.active(0)
            self.clock_pin.value(1)

        self._mut.release()

    @classmethod
    def wait_settle(cls, rate: int) -> None:
        time.sleep_ms(cls.get_settling_time(rate))

    @classmethod
    def wait_power_down(cls) -> None:
        time.sleep_us(cls.POWER_DOWN_TIMEOUT)

    def __try_get_value(self) -> int|None:
        words = self.READ_BITS / 8
        return self._sm.get() if self._sm.rx_fifo() >= words else None
