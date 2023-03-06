# type: ignore

# MIT License
# 
# Copyright (c) 2023 Daniel Robertson
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
from micropython import const
from rp2 import PIO, StateMachine, asm_pio

class _pio_prog:
    def __init__(self) -> None:
        pass
    def init(self, hx) -> None:
        pass
    def program(self) -> None:
        pass

class _hx711_reader(_pio_prog):

    # see: https://github.com/endail/hx711-pico-c/blob/main/src/hx711_noblock.pio
    PUSH_BITS: int = const(24)
    FREQUENCY: int = const(10000000)

    def __init__(self) -> None:
        super().__init__()

    def init(self, hx: hx711) -> None:
        hx._sm = StateMachine(hx._sm_index)
        hx._sm.init(
            self.program,
            freq=self.FREQUENCY,
            in_base=hx.data_pin,
            out_base=hx.clock_pin,
            set_base=hx.clock_pin,
            jmp_pin=None,
            sideset_base=hx.clock_pin)

    # pylint: disable=E,W,C,R
    @asm_pio(
        out_init=(PIO.OUT_LOW),
        set_init=(PIO.OUT_LOW),
        sideset_init=(PIO.OUT_LOW),
        out_shiftdir=PIO.SHIFT_LEFT,
        autopush=True,
        autopull=False,
        push_thresh=PUSH_BITS,
        fifo_join=PIO.JOIN_NONE
    )
    def program():

        set(x, 0) # default gain of 0
        pull(noblock) # pull in gain
        out(x, 32) # copy osr into x

        label("wrap_target")
        wrap_target()

        set(y, 23) # read bits, 0 based

        wait(0, pin, 0)

        label("bitloop")
        set(pins, 1)
        in_(pins, 1)

        jmp(y_dec, "bitloop").side(0).delay(2 - 1) # T4

        pull(noblock).side(1)

        out(x, 32)

        jmp(not_x, "wrap_target").side(0)

        mov(y, x)

        label("gainloop")
        set(pins, 1).delay(2 - 1) # T3
        jmp(y_dec, "gainloop").side(0).delay(2 - 1) # T4

        wrap()

class _util:

    @classmethod
    def get_sm_from_pio(cls, pio: PIO, sm_index: int) -> StateMachine:
        """Returns the StateMachine object from the given index

        Args:
            pio (PIO): RP2040 PIO instance
            sm_index (int):

        Returns:
            StateMachine:
        """
        return pio.state_machine(sm_index)

    @classmethod
    def get_sm_index(cls, pio_offset: int, sm_offset: int) -> int:
        """Returns the global state machine index from given args

        Args:
            pio_offset (int): 0 or 1
            sm_offset (int):

        Returns:
            int: index between 0 and 7
        """
        return (pio_offset >> 2) + sm_offset

    @classmethod
    def get_pio_from_sm_index(cls, sm_index: int) -> PIO:
        """Returns the correct PIO object from the global state machine index

        Args:
            sm_index (int):

        Returns:
            PIO:
        """
        return PIO(sm_index >> 2)

    @classmethod
    def sm_drain_tx_fifo(cls, sm: StateMachine) -> None:
        """Clears the StateMachine TX FIFO

        Args:
            sm (StateMachine):
        
        Performs:
        pull( ) noblock
        https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_pio/pio.c#L252
        This may not be thread safe
        """
        while sm.tx_fifo() != 0: sm.exec("pull() noblock")

    @classmethod
    def sm_get(cls, sm: StateMachine) -> int|None:
        """Returns a value from the StateMachine's RX FIFO (NON-BLOCKING)

        Args:
            sm (StateMachine):

        Returns:
            int|None: None is returned if RX FIFO is empty
        """
        return sm.get() if sm.rx_fifo() != 0 else None

    @classmethod
    def sm_get_blocking(cls, sm: StateMachine) -> int:
        """Returns a value from the StateMachine's RX FIFO (BLOCKING)

        Args:
            sm (StateMachine):

        Returns:
            int:
        """
        while sm.rx_fifo() == 0: pass
        return sm.get()

class hx711:

    READ_BITS: int = const(24)
    POWER_DOWN_TIMEOUT: int = const(60) # microseconds

    MIN_VALUE: int = const(-0x800000) # −8,388,608
    MAX_VALUE: int = const(0x7fffff) # 8,388,607

    PIO_MIN_GAIN: int = const(0)
    PIO_MAX_GAIN: int = const(2)

    SETTLING_TIMES: list[int] = [ # milliseconds
        const(400),
        const(50)
    ]

    SAMPLES_RATES: list[int] = [
        const(10),
        const(80)
    ]

    CLOCK_PULSES: list[int] = [
        const(25),
        const(26),
        const(27)
    ]

    RATES: dict = {
        "rate_10": int const(0),
        "rate_80": int const(1)
    }

    GAINS: dict = {
        "gain_128": int const(0),
        "gain_64": int const(1),
        "gain_32": int const(2)
    }

    def __init__(
        self,
        clk: Pin,
        dat: Pin,
        sm_index: int = 0,
        prog: _pio_prog = _hx711_reader()
    ):
        """Create HX711 object

        Args:
            clk (Pin): GPIO pin connected to HX711's clock pin
            dat (Pin): GPIO pin connected to HX711's data pin
            sm_index (int, optional): Global state machine index to use. Defaults to 0.
            prog (_pio_prog, optional): PIO program. Defaults to built-in hx711_reader().
        """

        self._mut = _thread.allocate_lock()

        with self._mut:

            self.clock_pin: Pin = clk
            self.data_pin: Pin = dat
            self.clock_pin.init(mode=Pin.OUT)
            self.data_pin.init(mode=Pin.IN)

            self._sm: StateMachine
            self._sm_index: int = sm_index
            self._prog: __class__._pio_prog = prog

            prog.init(self)

    def __bool__(self) -> bool:
        return self._sm.active()

    def __repr__(self) -> str:
        return "[HX711 - CLK: {}, DAT: {}, SM_IDX: {}]".format(self.clock_pin, self.data_pin, self._sm_index)

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_val, ex_tb) -> None:
        # handle abrupt exits from locked contexts
        if self._mut.locked(): self._mut.release()
        self.close()

    def close(self) -> None:
        """Stop communication with HX711. Does not alter power state.
        """
        with self._mut:
            self._sm.active(0)
            _util.get_pio_from_sm_index(self._sm_index).remove_program(self._prog.program)

    def set_gain(self, gain: int) -> None:
        """Change HX711 gain

        Args:
            gain (int):
        """
        pioGain = __class__.gain_to_pio_gain(gain)
        with self._mut:
            _util.sm_drain_tx_fifo(self._sm)
            self._sm.put(pioGain)
            self._sm.get()
            _util.sm_get_blocking(self._sm)

    @classmethod
    def get_twos_comp(cls, raw: int) -> int:
        """Returns the one's complement value from the raw HX711 value

        Args:
            raw (int): raw value from HX711

        Returns:
            int:
        """
        return -(raw & +cls.MIN_VALUE) + (raw & cls.MAX_VALUE)

    @classmethod
    def is_min_saturated(cls, val: int) -> bool:
        """Whether value is at its maximum

        Args:
            val (int):

        Returns:
            bool:
        """
        return val == cls.MIN_VALUE

    @classmethod
    def is_max_saturated(cls, val: int) -> bool:
        """Whether value is at its maximum

        Args:
            val (int):

        Returns:
            bool:
        """
        return val == cls.MAX_VALUE

    @classmethod
    def get_settling_time(cls, rate: int) -> int:
        """Returns the appropriate settling time for the given rate

        Args:
            rate (int):

        Returns:
            int: milliseconds
        """
        return cls.SETTLING_TIMES[rate]

    @classmethod
    def get_rate_sps(cls, rate: int) -> int:
        """Returns the numeric value of the given rate

        Args:
            rate (int):

        Returns:
            int:
        """
        return cls.SAMPLES_RATES[rate]

    @classmethod
    def get_clock_pulses(cls, gain: int) -> int:
        return cls.CLOCK_PULSES[gain]

    def get_value(self) -> int:
        """Blocks until a value is returned

        Returns:
            int:
        """
        with self._mut:
            rawVal = _util.sm_get_blocking(self._sm)
        return self.get_twos_comp(rawVal)

    def get_value_timeout(self, timeout: int = 1000000) -> int|None:
        """Attempts to obtain a value within the timeout

        Args:
            timeout (int, optional): timeout in microseconds. Defaults to 1000000.

        Returns:
            int|None: None is returned if no value is obtained within the timeout period
        """

        endTime: int = time.ticks_us() + timeout
        val: int|None = None

        with self._mut:
            while(time.ticks_us() < endTime):
                val = self._try_get_value()
                if val != None: break

        return self.get_twos_comp(val) if val else None

    def get_value_noblock(self) -> int|None:
        """Returns a value if one is available

        Returns:
            int|None: None is returned if no value is available
        """
        with self._mut:
            val = self._try_get_value()
        return self.get_twos_comp(val) if val else None

    @classmethod
    def is_value_valid(cls, val: int) -> bool:
        return val >= cls.MIN_VALUE and val <= cls.MAX_VALUE

    @classmethod
    def is_pio_gain_valid(cls, gain: int) -> bool:
        return gain >= cls.PIO_MIN_GAIN and gain <= cls.PIO_MAX_GAIN

    @classmethod
    def is_rate_valid(cls, rate: int) -> bool:
        return rate >= cls.RATES["rate_10"] and rate <= cls.RATES["rate_80"]

    @classmethod
    def is_gain_valid(cls, gain: int) -> bool:
        return gain >= cls.GAINS["gain_128"] and gain <= cls.GAINS["gain_32"]

    def power_up(self, gain: int) -> None:
        pioGain = __class__.gain_to_pio_gain(gain)
        with self._mut:
            self.clock_pin.low()
            self._sm.restart()
            _util.sm_drain_tx_fifo(self._sm)
            self._sm.put(pioGain)
            self._sm.active(1)

    def power_down(self) -> None:
        with self._mut:
            self._sm.active(0)
            self.clock_pin.high()

    @classmethod
    def wait_settle(cls, rate: int) -> None:
        """Waits for the appropriate amount of time for values to settle according to the given rate

        Args:
            rate (int):
        """
        time.sleep_ms(cls.get_settling_time(rate))

    @classmethod
    def wait_power_down(cls) -> None:
        """Waits for the appropriate amount of time for the HX711 to power down
        """
        time.sleep_us(cls.POWER_DOWN_TIMEOUT)

    @classmethod
    def gain_to_pio_gain(cls, gain: int) -> int:
        return cls.get_clock_pulses(gain) - cls.READ_BITS - 1

    def _try_get_value(self) -> int|None:
        """Attempts to obtain a value if one is available

        Returns:
            int|None: None is returned if no value is available
        """
        words = __class__.READ_BITS / 8
        return self._sm.get() if self._sm.rx_fifo() >= words else None

class hx711_multi:
    def __init__(self) -> None:
        raise NotImplementedError()
