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
from machine import Pin
from rp2 import PIO, StateMachine

class hx711:

    # ------- BEGIN INNER CLASSES ---------

    class _util:

        @classmethod
        def get_sm_from_pio(cls, pio: PIO, sm_index: int) -> StateMachine:
            return pio.state_machine(sm_index)

        @classmethod
        def get_sm_index(cls, pio_offset: int, sm_offset: int) -> int:
            return (pio_offset >> 2) + sm_offset

        @classmethod
        def get_pio_from_sm_index(cls, sm_index: int) -> PIO:
            return PIO(sm_index >> 2)

        @classmethod
        def sm_drain_tx_fifo(cls, sm: StateMachine) -> None:
            '''
            to clear the fifo...
            pull( ) noblock
            https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_pio/pio.c#L252
            '''
            while sm.tx_fifo() != 0: sm.exec("pull() noblock") # nts

        @classmethod
        def sm_get(cls, sm: StateMachine):
            return sm.get() if sm.rx_fifo() != 0 else None

        @classmethod
        def sm_get_blocking(cls, sm: StateMachine):
            while sm.rx_fifo() == 0: pass
            return sm.get()

    class rate:
        rate_10 = 0
        rate_80 = 1

    class gain:
        gain_128 = 25
        gain_32 = 26
        gain_64 = 27

    class power:
        pwr_up = 0
        pwr_down = 1

    class _pio_prog:
        def __init__(self) -> None:
            pass
        def init(self, hx) -> None:
            pass
        def program(self) -> None:
            pass

    class pio_noblock(_pio_prog):

        PUSH_BITS: int = 24
        FREQUENCY: int = 10000000 # 10MHz, 0.1us

        def __init__(self) -> None:
            super().__init__()

        def init(self, hx) -> None:
            hx._sm = StateMachine(
                hx._sm_index,
                self.program,
                freq=self.FREQUENCY,
                in_base=hx.data_pin,
                out_base=hx.clock_pin,
                set_base=hx.clock_pin,
                jmp_pin=None,
                sideset_base=hx.clock_pin
            )

        @asm_pio(
            out_init=PIO.IN_HIGH,
            set_init=(PIO.IN_HIGH),
            sideset_init=(PIO.IN_HIGH),
            out_shiftdir=PIO.SHIFT_LEFT,
            autopush=True,
            autopull=False,
            push_thresh=PUSH_BITS,
            fifo_join=PIO.JOIN_NONE
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

    # ------- END INNER CLASSES ---------

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
        prog: _pio_prog = pio_noblock()
    ):
        '''
        clk: clock pin
        dat: data pin
        sm_index: state machine index
        prog: PIO program
        '''

        self._mut = _thread.allocate_lock()
        self._mut.acquire()

        self.clock_pin: Pin = clk
        self.data_pin: Pin = dat
        self.clock_pin.init(mode=Pin.OUT)
        self.data_pin.init(mode=Pin.IN)

        self._sm: StateMachine
        self._sm_index: int = sm_index
        self._prog: __class__._pio_prog = prog

        prog.init(self)

        self._mut.release()

    def __enter__(self):
        return self
        
    def __exit__(self, ex_type, ex_val, ex_tb):
        self.close()

    def close(self) -> None:
        self._mut.acquire()
        self._sm.active(0)
        __class__._util.get_pio_from_sm_index(self._sm_index).remove_program(self._prog.program)
        self._mut.release()

    def set_gain(self, gain: int) -> None:
        self._mut.acquire()
        __class__._util.sm_drain_tx_fifo(self._sm)
        self._sm.put(gain)
        self._sm.get()
        __class__._util.sm_get_blocking(self._sm)
        self._mut.release()

    @classmethod
    def get_twos_comp(cls, raw: int) -> int:
        return -(raw & +cls.MIN_VALUE) + (raw & cls.MAX_VALUE)

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
        rawVal = __class__._util.sm_get_blocking(self._sm)
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
            val = self._try_get_value()
            if val != None: break

        self._mut.release()

        return self.get_twos_comp(val) if val else None

    def get_value_noblock(self) -> int|None:
        self._mut.acquire()
        val = self._try_get_value()
        self._mut.release()
        return self.get_twos_comp(val) if val else None

    def set_power(self, pwr: int) -> None:

        self._mut.acquire()

        if pwr == __class__.power.pwr_up:
            self.clock_pin.low()
            self._sm.restart()
            self._sm.active(1)

        elif pwr == __class__.power.pwr_down:
            self._sm.active(0)
            self.clock_pin.high()

        self._mut.release()

    @classmethod
    def wait_settle(cls, rate: int) -> None:
        time.sleep_ms(cls.get_settling_time(rate))

    @classmethod
    def wait_power_down(cls) -> None:
        time.sleep_us(cls.POWER_DOWN_TIMEOUT)

    def _try_get_value(self) -> int|None:
        words = self.READ_BITS / 8
        return self._sm.get() if self._sm.rx_fifo() >= words else None
