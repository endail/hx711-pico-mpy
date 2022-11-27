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

from hx711 import hx711_pio_prog
from util import util
from rp2 import asm_pio, PIO, StateMachine

class hx711_noblock(hx711_pio_prog):

    READ_BITS: int = 23
    DEFAULT_GAIN: int = 0
    T3: int = 2
    T4: int = 2
    FREQUENCY: int = 10000000 #10MHz, 0.1us

    def init(self, hx):

        hx._state_mach = util.get_sm_from_pio(hx._pio_offset, hx._sm_offset)

        hx._state_mach = StateMachine.init(
            self.program,
            freq=self.FREQUENCY,
            in_base=hx.data_pin,
            out_base=hx.clock_pin,
            set_base=hx.clock_pin,
            jmp_pin=None,
            sideset_base=hx.clock_pin
        )

    @asm_pio(
        out_init=(PIO.IN_HIGH),
        set_init=(PIO.IN_HIGH),
        sideset_init=(PIO.IN_HIGH),
        out_shiftdir=PIO.SHIFT_LEFT,
        autopush=True,
        autopull=False,
        push_thresh=READ_BITS + 1,
        push_thresh=32,
        fifo_join=PIO.JOIN_NONE
    )
    def program(self):

        set(dest=x, self.DEFAULT_GAIN)

        label("wrap_target")
        wrap_target()

        set(dest=y, self.READ_BITS)

        wait(polarity=0, src=pin, index=0)

        label("bitloop")
        set(dest=pins, data=0)
        in_(src=pins, bit_count=1)

        jmp(cond=y_dec, "bitloop").side(0) [self.T4 - 1]

        pull(noblock).side(1)

        out(dest=x, bit_count=2)

        jmp(cond=not_x, "wrap_target").side(0)

        mov(dest=y, src=x)

        label("gainloop")
        set(dest=pins, data=1) [self.T3 - 1]
        jmp(cond=y_dec, "gainloop").side(0) [self.T4 - 1]

        wrap()
