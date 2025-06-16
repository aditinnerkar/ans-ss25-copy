"""
Copyright (c) 2025 Computer Networks Group @ UPB

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

"""
    Utilities to generate input data
"""

import random

MAX_INT_VAL = 0xffff
MAX_FLOAT_VAL = 1

def GenMultipleOfInRange(lo=2, hi=2048, multiple=1, seed=42):
    """
    Generate a random integer in range [lo, hi] that is a multiple of 'multiple'
    If the range is not correct, it will be 'fixed' to make sure that:
        multiple <= lo <= hi
    By default the function passes `seed` to the RNG and then resets it. Which is useful
    for generating the same random number across workers etc.
    """
    if lo < multiple:
        lo = multiple
    if hi <= lo:
        hi = lo
    random.seed(seed)
    n = random.randint(lo, hi)
    random.seed(None)
    res = multiple * round(n / multiple)
    return res + multiple if res < lo or res > hi else res

def GenInts(n=1, unique=None):
    """
    Generate n random integers in range [0, MAX_INT_VAL]
    if unique is not None, all elements have the value unique
    """
    return [unique] * n if unique is not None else random.sample(range(0, MAX_INT_VAL), n)

def GenFloats(n=1, unique=None):
    """
    Generate n random floats in range [0, MAX_FLOAT_VAL]
    if unique is not None, all elements have the value unique
    """
    return [float(unique)] * n if unique is not None else [random.uniform(0, MAX_FLOAT_VAL) for i in range(n)]