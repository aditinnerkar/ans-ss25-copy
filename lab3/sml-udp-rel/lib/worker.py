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



import os, sys
from datetime import datetime

def ip(iface="eth0"):
    """
    Retrieve the first ip address assigned to an interface
    """
    return os.popen('ip addr show %s' % iface).read().split("inet ")[1].split("/")[0] # yeah, i know... right?

def rank():
    """
    Retrieve the rank of a worker, assumed to be found at sys.argv[1]
    Throws and exception if an integer cannot be parsed from sys.argv[1]
    """
    rank.val = None
    if rank.val == None:
        rank.val = int(sys.argv[1])
    return rank.val

def PrintUsage():
    print("usage: python worker.py <rank>")

def GetRankOrExit():
    """
    Retrieve the rank of a worker or exist gracefully with usage message
    """
    try:
        return rank()
    except:
        PrintUsage()
        sys.exit(1)

def Log(*args):
    """
    Log a timestamped message to stdout
    """
    now = datetime.now()
    ts = ('%02d:%02d:%02d.%06d' %
          (now.hour, now.minute, now.second, now.microsecond))
    print("[W][%s][%s]" % (ip(), ts), *args)