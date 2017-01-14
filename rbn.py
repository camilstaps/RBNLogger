#!/usr/bin/env python3
"""Reverse Beacon Network (www.reversebeacon.net) logging and filter tool"""
import argparse
import re
import telnetlib
import textwrap


HOST = 'telnet.reversebeacon.net'
PORT = 7000
TIMEOUT = 5

RGX = r'^DX de (.*?):\s*(\d+\.\d+)\s*(\S+)\s+' +\
        r'(\S+)\s+(\d+) dB\s+(\d+)\s+(\S+)\s+(\S.*\S)\s+(\d+)(\d\d)Z\s*$'

BANDS = [
        (160, 2500),
        (80, 5000),
        (60, 6000),
        (40, 8500),
        (30, 12000),
        (20, 16000),
        (17, 19500),
        (15, 22500),
        (12, 26500),
        (10, 40000),
        (6, 65000),
        (4, 120000),
        (2, 160000),
        (1.25, 300000),
        (0.7, 600000),
        (0.33, 1000000),
        (0.23, 1400000)]

def band_to_str(band):
    if band < 0:
        return str(band * 100) + 'cm'
    else:
        return str(band) + 'm'


def matches(key, val, regex=False):
    """Check if a value matches a filter

    The filter can be one of the following:

    - None (always True)
    - Value, equatable to val (True on equality)
    - Regex (with regex=True) (True if str(val) matches key)
    - Function from type(val) to bool
    - A tuple of a key and a boolean, true iff the match should be inverted
    - A list of the above (at least one should match)
    """
    if key is None:
        return True
    if regex:
        val = str(val)
    if type(key) is list:
        for subkey in key:
            if matches(subkey, val, regex=regex):
                return True
        return False
    if type(key) is tuple:
        match = matches(key[0], val, regex=regex)
        return not match if key[1] else match
    if regex:
        return re.match(key, val)
    if callable(key):
        return key(val)
    return key == val

def parse_range_filter(arg):
    if arg[0:2] == '<=':
        return lambda x : x <= float(arg[2:].strip())
    if arg[0:2] == '>=':
        return lambda x : x >= float(arg[2:].strip())
    if arg[0:2] == '/=':
        return lambda x : x != float(arg[2:].strip())
    if arg[0:1] == '=':
        return lambda x : x == float(arg[1:].strip())
    if arg[0:1] == '<':
        return lambda x : x < float(arg[1:].strip())
    if arg[0:1] == '>':
        return lambda x : x > float(arg[1:].strip())
    match = re.match(r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+))', arg)
    if match is not None:
        return lambda x : float(match.group(1)) <= x <= float(match.group(2))
    raise ValueError('Could not parse "' + arg + '" as a range')

class Record:
    """A record fetched from RBN"""
    def __init__(self, line):
        self.parse(line)

    def parse(self, line):
        """Parse a line from the telnet server"""
        match = re.match(RGX, line)
        if match is None:
            raise ValueError('Could not parse: "' + line + '"')
        self.station_dx = match.group(1)
        self.frequency = float(match.group(2))
        self.station_de = match.group(3)
        self.mode = match.group(4)
        self.signal_strength = int(match.group(5))
        self.speed = (int(match.group(6)), match.group(7))
        self.record_type = match.group(8)
        self.time = (int(match.group(9)), int(match.group(10)))

    def band(self):
        for (band, freq) in BANDS:
            if self.frequency < freq:
                return band
        return None

    def match(self,
            dx=None, de=None, band=None, frequency=None, mode=None,
            signal_strength=None, speed=None, record_type=None):
        """Does this record match filters?
        
        For filter documentation see matches().

        dx, de: string (regex search)
        mode, record_type: string
        band, signal_strength: int
        frequency: float
        speed: (int, string)
        """
        filters = [
                (dx, self.station_dx, True),
                (de, self.station_de, True),
                (band, self.band(), False),
                (frequency, self.frequency, False),
                (mode, self.mode, False),
                (signal_strength, self.signal_strength, False),
                (speed, self.speed, False),
                (record_type, self.record_type, False)]
        for key, val, rgx in filters:
            if key is not None and not matches(key, val, regex=rgx):
                return False
        return True

    def __str__(self):
        return ('%02d'%self.time[0]) + ':' + ('%02d'%self.time[1]) + 'Z  ' +\
                'DX de ' + (self.station_dx + ':').ljust(12) + '  ' +\
                band_to_str(self.band()).rjust(4) + '  ' +\
                str(self.frequency).rjust(10) + '  ' +\
                self.station_de.ljust(14) + '  ' + self.mode.ljust(8) + '  ' +\
                (str(self.signal_strength) + ' dB').rjust(6) + '  ' +\
                str(self.speed[0]) + ' ' + self.speed[1] + '\t' +\
                self.record_type

def connect(call, host, port, timeout):
    """Connect to an RBN server"""
    conn = telnetlib.Telnet(host, port, timeout)
    conn.read_until('Please enter your call:'.encode('ascii'))
    conn.write((call + '\n').encode('ascii'))
    return conn

def main():
    """Main program"""
    prs = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description='''Reverse Beacon Network logger''',
            epilog=textwrap.dedent('''\
                All non-range filter arguments can be prepended with ~ to invert them.

                Range filters:
                 - =x    Value should be equal to x
                 - /=x   Value should not be equal to x
                 - <x    Value should be smaller than x
                 - >x    Value should be greater than x
                 - <=x   Value should be smaller than or equal to x
                 - >=x   Value should be greater than or equal to x
                 - x-y   Value should be between x and y (inclusive)
                 - A comma-separated list of range filters
            '''))

    prs.add_argument('-c', '--call', help='Your identification', required=True)
    prs.add_argument('-H', '--host', help='Telnet host', default=HOST)
    prs.add_argument('-p', '--port', help='Telnet port', default=PORT)
    prs.add_argument('--timeout', help='Connection timeout', default=TIMEOUT)

    prs.add_argument('--de', help='Filter transmitting station (regex)')
    prs.add_argument('--dx', help='Filter skimming station (regex)')
    prs.add_argument('-b', '--band',
            help='Filter band (comma-separated integers)')
    prs.add_argument('-m', '--mode',
            help='Filter mode (comma-separated strings)')
    prs.add_argument('-f', '--frequency',
            help='Filter frequency in MHz (range filter, see below)')
    prs.add_argument('-s', '--speed',
            help='Filter transmission speed (range filter, see below)')
    prs.add_argument('-S', '--signal',
            help='Filter signal strength in dB (range filter, see below)')
    prs.add_argument('-t', '--type', dest='record_type',
            help='Filter record type (comma-separated; e.g. CQ or BEACON)')

    args = prs.parse_args()

    conn = connect(args.call, args.host, args.port, args.timeout)

    filters = dict(de=args.de, dx=args.dx)
    if args.band is not None:
        invert = args.band[0] == '~'
        if invert:
            args.band = args.band[1:]
        filters['band'] = (list(map(int, args.band.split(','))), invert)
    if args.mode is not None:
        invert = args.mode[0] == '~'
        if invert:
            args.mode = args.mode[1:]
        filters['mode'] = (args.mode.split(','), invert)
    if args.record_type is not None:
        invert = args.record_type[0] == '~'
        if invert:
            args.record_type = args.record_type[1:]
        filters['record_type'] = (args.record_type.split(','), invert)
    if args.frequency is not None:
        filters['frequency'] = list(map(
            parse_range_filter, args.frequency.split(',')))
    if args.speed is not None:
        speed_filters = list(map(parse_range_filter, args.speed.split(',')))
        filters['speed'] = lambda x : matches(speed_filters, x[0])
    if args.signal is not None:
        filters['signal'] = list(map(
            parse_range_filter, args.signal.split(',')))

    line = None
    while line is None or line != '':
        line = conn.read_until('\r\n'.encode('ascii'))
        try:
            rec = Record(line.decode('ascii').strip())
            if rec.match(**filters):
                print(rec)
        except ValueError:
            pass

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
    except EOFError as exc:
        print(exc)
