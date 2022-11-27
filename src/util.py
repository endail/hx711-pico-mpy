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

from machine import mem32
from rp2 import PIO, StateMachine

class util:

    @classmethod
    def get_sm_from_pio(cls, pio_offset: int, sm_offset: int):
        '''
        Takes the pio offset (either 0 or 1) and the sm offset
        (0 - 3) and returns the correct StateMachine object
        '''
        return StateMachine((pio_offset << 2) + sm_offset)

    @classmethod
    def get_pio_from_sm(cls, sm_offset: int):
        '''
        Takes the sm offset and returns the correct pio
        '''
        return PIO(sm_offset >> 2)

    @classmethod
    def sm_drain_tx_fifo(cls, sm):
        while sm.tx_fifo() != 0:
            sm.exec("pull 0 0")

    @classmethod
    def sm_get(cls, sm):
        if sm.rx_fifo() != 0:
            return sm.get()
        return None

    @classmethod
    def sm_get_blocking(cls, sm):
        while(sm.rx_fifo() == 0):
            pass
        return sm.get()
