# type: ignore

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
from machine import Pin, I2C
from micropython import const
from rp2 import PIO, StateMachine, asm_pio

class _util:

    @classmethod
    def set_bits8(cls, value: int, startbit: int, len: int, bits: int) -> int:
        mask: int = ((1 << len) - 1) << startbit
        value &= ~mask
        value |= (bits << startbit)
        return value

    @classmethod
    def get_bits8(cls, value: int, startbit: int, len: int):
        mask: int = ((1 << len) - 1) << startbit
        extracted: int = (value & mask) >> startbit
        return extracted

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

    class rate:
        rate_10: int = const(0)
        rate_80: int = const(1)

    class gain:
        gain_128: int = const(25)
        gain_32: int = const(26)
        gain_64: int = const(27)

    class power:
        pwr_up: int = const(0)
        pwr_down: int = const(1)

    class _pio_prog:
        def __init__(self) -> None:
            pass
        def init(self, hx) -> None:
            pass
        def program(self) -> None:
            pass

    class pio_noblock(_pio_prog):

        # see: https://github.com/endail/hx711-pico-c/blob/main/src/hx711_noblock.pio
        PUSH_BITS: int = const(24)
        FREQUENCY: int = const(10000000)

        def __init__(self) -> None:
            super().__init__()

        def init(self, hx: hx711) -> None:
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

            label("wrap_target")
            wrap_target()

            set(y, 23) # read bits, 0 based

            wait(0, pin, 0)

            label("bitloop")
            set(pins, 1)
            in_(pins, 1)

            jmp(y_dec, "bitloop").side(0).delay(2 - 1) # T4

            pull(noblock).side(1)

            out(x, 2)

            jmp(not_x, "wrap_target").side(0)

            mov(y, x)

            label("gainloop")
            set(pins, 1).delay(2 - 1) # T3
            jmp(y_dec, "gainloop").side(0).delay(2 - 1) # T4

            wrap()

    READ_BITS: int = const(24)
    MIN_VALUE: int = const(-0x800000)
    MAX_VALUE: int = const(0x7fffff)
    POWER_DOWN_TIMEOUT: int = const(60) # us
    SETTLING_TIMES: list[int] = [ # ms
        const(400),
        const(50)
    ]
    SAMPLES_RATES: list[int] = [
        const(10),
        const(80)
    ]

    def __init__(
        self,
        clk: Pin,
        dat: Pin,
        sm_index: int = 0,
        prog: _pio_prog = pio_noblock()
    ):
        """Create HX711 object

        Args:
            clk (Pin): GPIO pin connected to HX711's clock pin
            dat (Pin): GPIO pin connected to HX711's data pin
            sm_index (int, optional): Global state machine index to use. Defaults to 0.
            prog (_pio_prog, optional): PIO program. Defaults to built-in pio_noblock().
        """

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
        self._mut.acquire()
        self._sm.active(0)
        _util.get_pio_from_sm_index(self._sm_index).remove_program(self._prog.program)
        self._mut.release()

    def set_gain(self, gain: int) -> None:
        """Change HX711 gain

        Args:
            gain (int):
        """
        self._mut.acquire()
        _util.sm_drain_tx_fifo(self._sm)
        self._sm.put(gain)
        self._sm.get()
        _util.sm_get_blocking(self._sm)
        self._mut.release()

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

    def get_value(self) -> int:
        """Blocks until a value is returned

        Returns:
            int:
        """
        self._mut.acquire()
        rawVal = _util.sm_get_blocking(self._sm)
        self._mut.release()
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

        self._mut.acquire()

        while(time.ticks_us() < endTime):
            val = self._try_get_value()
            if val != None: break

        self._mut.release()

        return self.get_twos_comp(val) if val else None

    def get_value_noblock(self) -> int|None:
        """Returns a value if one is available

        Returns:
            int|None: None is returned if no value is available
        """
        self._mut.acquire()
        val = self._try_get_value()
        self._mut.release()
        return self.get_twos_comp(val) if val else None

    def set_power(self, pwr: int) -> None:
        """Changes the power state of the HX711 and starts/stops the PIO program

        Args:
            pwr (int):
        """

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

    def _try_get_value(self) -> int|None:
        """Attempts to obtain a value if one is available

        Returns:
            int|None: None is returned if no value is available
        """
        words = __class__.READ_BITS / 8
        return self._sm.get() if self._sm.rx_fifo() >= words else None

class hx711_i2c:

    @classmethod
    def gain_to_i2c_gain(cls, g: int) -> int|None:
        if g == hx711.gain.gain_128: return 0
        elif g == hx711.gain.gain_32: return 1
        elif g == hx711.gain.gain_64: return 2
        return None
    
    @classmethod
    def i2c_gain_to_gain(cls, ig: int) -> int|None:
        if ig == 0: return hx711.gain.gain_128
        elif ig == 1: return hx711.gain.gain_32
        elif ig == 2: return hx711.gain.gain_64
        return None

    class control:
        _METADATA_OFFSET_BYTES: int =    const(0)
        _READY_STATE_OFFSET: int =       const(0)
        _NEW_VALUE_STATE_OFFSET: int =   const(1)
        _POWER_STATE_OFFSET: int =       const(2)
        _GAIN_OFFSET: int =              const(3)
        _RATE_OFFSET: int =              const(5)
        _DATA_OFFSET: int =              const(8)
        _DATA_OFFSET_BYTES: int =        const(1)

        _READY_STATE_SIZE: int =         const(1)
        _NEW_VALUE_STATE_SIZE: int =     const(1)
        _POWER_STATE_SIZE: int =         const(1)
        _GAIN_SIZE: int =                const(2)
        _RATE_SIZE: int =                const(1)

        _DATA_SIZE_BITS: int =           const(hx711.READ_BITS)
        _DATA_SIZE_BYTES: int =          const(3)
        _METADATA_SIZE_BITS: int =       const(6)
        _METADATA_SIZE_BYTES: int =      const(1)
        _TOTAL_BYTES: int =              const(4)

        def __init__(self, metadata: int = 0) -> None:
            self._bits = metadata

        def __int__(self) -> int:
            return self._bits
        
        def __bool__(self) -> bool:
            return self.new_value_state and self.ready_state and self.power_state

        @property
        def ready_state(self) -> bool:
            return bool(_util.get_bits8(
                self._bits,
                __class__._READY_STATE_OFFSET,
                __class__._READY_STATE_SIZE))

        @ready_state.setter
        def ready_state(self, state: bool) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._READY_STATE_OFFSET,
                __class__._READY_STATE_SIZE,
                int(state))

        @property
        def new_value_state(self) -> bool:
            return bool(_util.get_bits8(
                self._bits,
                __class__._NEW_VALUE_STATE_OFFSET,
                __class__._NEW_VALUE_STATE_SIZE))

        @new_value_state.setter
        def new_value_state(self, state: bool) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._NEW_VALUE_STATE_OFFSET,
                __class__._NEW_VALUE_STATE_SIZE,
                int(state))

        @property
        def power_state(self) -> bool:
            return bool(_util.get_bits8(
                self._bits,
                __class__._POWER_STATE_OFFSET,
                __class__._POWER_STATE_SIZE))

        @power_state.setter
        def power_state(self, state: bool) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._POWER_STATE_OFFSET,
                __class__._POWER_STATE_SIZE,
                int(state))

        @property
        def gain(self) -> int:
            i2c_gain: int = _util.get_bits8(
                self._bits,
                __class__._GAIN_OFFSET,
                __class__._GAIN_SIZE)
            return i2c_gain_to_gain(i2c_gain)

        @gain.setter
        def gain(self, g: int) -> None:
            i2c_gain: int = gain_to_i2c_gain(g)
            self._bits = _util.set_bits8(
                self._bits,
                __class__._GAIN_OFFSET,
                __class__._GAIN_SIZE,
                i2c_gain)

        @property
        def rate(self) -> int:
            return _util.get_bits8(
                self._bits,
                __class__._RATE_OFFSET,
                __class__._RATE_SIZE)

        @rate.setter
        def rate(self, r: int) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._RATE_OFFSET,
                __class__._RATE_SIZE,
                r)

    class command:
        _COMMAND_OFFSET: int =           const(0)
        _POWER_STATE_OFFSET: int =       const(2)
        _GAIN_OFFSET: int =              const(3)
        _RATE_OFFSET: int =              const(5)

        _COMMAND_SIZE: int =             const(2)
        _POWER_STATE_SIZE: int =         const(1)
        _GAIN_SIZE: int =                const(2)
        _RATE_SIZE: int =                const(1)

        none: int =                     const(0)
        change_power_state: int =       const(1)
        change_gain: int =              const(2)
        get_value: int =                const(3)

        def __init__(self, metadata: int = 0) -> None:
            self._bits = metadata

        def __int__(self) -> int:
            return self._bits

        @property
        def cmd(self) -> command:
            return _util.get_bits8(
                self._bits,
                __class__._COMMAND_OFFSET,
                __class__._COMMAND_SIZE)

        @cmd.setter
        def cmd(self, c: int) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._COMMAND_OFFSET,
                __class__._COMMAND_SIZE,
                c)

        @property
        def power_state(self) -> bool:
            return bool(_util.get_bits8(
                self._bits,
                __class__._POWER_STATE_OFFSET,
                __class__._POWER_STATE_SIZE))

        @power_state.setter
        def power_state(self, state: bool) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._POWER_STATE_OFFSET,
                __class__._POWER_STATE_SIZE,
                int(state))

        @property
        def gain(self) -> int:
            i2c_gain: int = _util.get_bits8(
                self._bits,
                __class__._GAIN_OFFSET,
                __class__._GAIN_SIZE)
            return hx711_i2c.i2c_gain_to_gain(i2c_gain)

        @gain.setter
        def gain(self, g: int) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._GAIN_OFFSET,
                __class__._GAIN_SIZE,
                hx711_i2c.gain_to_i2c_gain(g))

        @property
        def rate(self) -> int:
            return _util.get_bits8(
                self._bits,
                __class__._RATE_OFFSET,
                __class__._RATE_SIZE)

        @rate.setter
        def rate(self, r: int) -> None:
            self._bits = _util.set_bits8(
                self._bits,
                __class__._RATE_OFFSET,
                __class__._RATE_SIZE,
                r)

    DEFAULT_SCL_PIN: Pin = Pin(5, mode=Pin.OUT, pull=Pin.PULL_UP, alt=Pin.ALT_I2C)
    DEFAULT_SDA_PIN: Pin = Pin(4, mode=Pin.IN, pull=Pin.PULL_UP, alt=Pin.ALT_I2C)
    DEFAULT_BAUD_RATE: int = const(100000)
    DEFAULT_I2C_ADDR: int = const(0x64)
    DEFAULT_I2C_INST: int = const(0)
    DEFAULT_I2C_TIMEOUT: int = const(50000)

    @classmethod
    def _value_to_array(cls, val: int) -> bytearray:
        arr: bytearray = bytearray(hx711.READ_BITS / 8)
        arr[0] = ((val >> 0) & 0xff)
        arr[1] = ((val >> 8) & 0xff)
        arr[2] = ((val >> 16) & 0xff)
        return arr

    @classmethod
    def _array_to_value(cls, arr: bytes) -> int:
        assert(len(arr) == hx711.READ_BITS / 8)
        val = int.from_bytes(arr, "little", False)
        return hx711.get_twos_comp(val)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __init__(
        self,
        scl_pin: Pin = DEFAULT_SCL_PIN,
        sda_pin: Pin = DEFAULT_SDA_PIN,
        baud_rate: int = DEFAULT_BAUD_RATE,
        addr: int = DEFAULT_I2C_ADDR,
        inst: int = DEFAULT_I2C_INST,
        i2c_timeout: int = DEFAULT_I2C_TIMEOUT
    ) -> None:

        self._scl_pin = scl_pin
        self._sda_pin = sda_pin
        self._baud_rate = baud_rate
        self._addr = addr
        self._i2c = inst
        self._i2c_timeout = i2c_timeout

        self._i2c = I2C(
            id=self._i2c,
            scl=self._scl_pin,
            sda=self._sda_pin,
            freq=self._baud_rate,
            timeout=self._i2c_timeout)

    def __repr__(self) -> str:
        return f"{__class__.__name__}(scl:{self._scl_pin}, sda:{self._sda_pin}, baud:{self._baud_rate}, addr:{self._addr})"

    def close(self) -> None:
        self._i2c.deinit()

    def set_gain(self, gain: int, rate: int) -> None:
        cmd: __class__.command = __class__.command()
        cmd.cmd = __class__.command.change_gain
        cmd.gain = gain
        cmd.rate = rate
        self._i2c.writeto(
            self._addr,
            bytes(int(command)),
            True)

    def get_value(self) -> tuple[int, int, control]:

        # 0: byte length (or error?)
        # 1: value
        # 2: control
        ret: list[int, int, __class__.control] = [None, None, None]

        inbuff: bytes = self._i2c.readfrom(
            self._addr,
            __class__.control._TOTAL_BYTES,
            True)

        ret[0] = len(inbuff)

        if ret[0] != __class__.control._TOTAL_BYTES:
            return tuple(ret)

        ret[1] = __class__._array_to_value(inbuff[1:])
        ret[2] = __class__.control(inbuff[0])

        return tuple(ret)

    def power_up(self, gain: int, rate: int) -> None:
        cmd: __class__.command = __class__.command()
        cmd.cmd = __class__.command.change_power_state
        cmd.power_state = True
        cmd.gain = gain
        cmd.rate = rate
        self._i2c.writeto(
            self._addr,
            bytes(int(cmd)),
            True)

    def power_down(self):
        cmd: __class__.command = __class__.command()
        cmd.cmd = __class__.command.change_power_state
        cmd.power_state = False
        self._i2c.writeto(
            self._addr,
            bytes(int(command)),
            True)
