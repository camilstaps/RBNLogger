#!/usr/bin/env python3
"""Reverse Beacon Network (www.reversebeacon.net) logging and filter tool"""
from argparse import ArgumentParser
import re
from telnetlib import Telnet


HOST = 'telnet.reversebeacon.net'
PORT = 7000
TIMEOUT = 5

RGX = r'^DX de (.*?):\s*(\d+\.\d+)\s*(\S+)\s+' +\
        r'(\S+)\s+(\d+) dB\s+(\d+)\s+(\S+)\s+(\S.*\S)\s+(\d+)(\d\d)Z\s*$'

BANDS = [
        (160, 2500),
        (80, 5000),
        (40, 8500),
        (30, 12000),
        (20, 16000),
        (17, 19500),
        (15, 22000),
        (12, 26500),
        (10, 45000),
        (6, 65000),
        (4, 120000),
        (2, 160000)]

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
    - List of values equatable to val (at least one should match)
    - Regex (with regex=True) (True if str(val) matches key)
    - List of regexes (with regex=True) (at least one should match)
    - Function from type(val) to bool
    """
    if key is None:
        return True
    if regex:
        val = str(val)
    if type(key) is list:
        if regex:
            for rgx in key:
                if re.match(key, val):
                    return True
            return False
        else:
            return val in key
    if regex:
        return re.match(key, val)
    if callable(key):
        return key(val)
    return key == val


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
        return str(self.time[0]) + ':' + str(self.time[1]) + 'Z  ' +\
                'DX de ' + (self.station_dx + ':').ljust(12) + '  ' +\
                band_to_str(self.band()).rjust(4) + '  ' +\
                str(self.frequency).rjust(10) + '  ' +\
                self.station_de.ljust(14) + '  ' + self.mode.ljust(8) + '  ' +\
                (str(self.signal_strength) + ' dB').rjust(6) + '  ' +\
                str(self.speed[0]) + ' ' + self.speed[1] + '\t' +\
                self.record_type

def connect(call, host, port, timeout):
    """Connect to an RBN server"""
    conn = Telnet(host, port, timeout)
    conn.read_until('Please enter your call:'.encode('ascii'))
    conn.write((call + '\n').encode('ascii'))
    return conn

def main():
    """Main program"""
    prs = ArgumentParser(description='Reverse Beacon Network logger')

    prs.add_argument('-c', '--call', help='Your identification', required=True)
    prs.add_argument('-H', '--host', help='Telnet host', default=HOST)
    prs.add_argument('-p', '--port', help='Telnet port', default=PORT)
    prs.add_argument('--timeout', help='Connection timeout', default=TIMEOUT)

    prs.add_argument('--de', help='Filter transmitting station (regex)')
    prs.add_argument('--dx', help='Filter skimming station (regex)')
    prs.add_argument('--band', help='Filter band (comma-separated integers)')

    args = prs.parse_args()

    conn = connect(args.call, args.host, args.port, args.timeout)

    filters = dict(de=args.de, dx=args.dx)
    if args.band is not None:
        filters['band'] = list(map(int, args.band.split(',')))

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
