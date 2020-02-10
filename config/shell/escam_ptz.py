#!/usr/local/bin/python3
"""
Simple script to move ESCAM QF001 ip camera between preset points

Usage: `./escam_ptz.py r 1. -v`

# Go to preset point
./escam_ptz.py door  -v
./escam_ptz.py window

# Reset into right corner
./escam_ptz.py r 6.  -v

"""
from datetime import datetime
from time import time, sleep
import requests
from threading import Thread
from argparse import ArgumentParser
import sys

HOST = "192.168.1.7"

URL = f"http://{HOST}/dvrcmd"
HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8,pt;q=0.7",
    "Content-Type": "text/plain; charset=utf-8",
}
PAYLOAD_MASK = "command=ptz_req&req={}&param={}&channel=1&stream=1"
DIRECTIONS = {
    "r": "directionright",
    "l": "directionleft",
    "d": "directiondown",
    "u": "directionup",
    "ru": "directionrightup",
    "rd": "directionrightdown",
    "lu": "directionleftup",
    "ld": "directionleftdown",
}

PRESET_POINTS = {
    "corner": [("r", 6.)],
    "window": [("r", 6.), ("l", 1.5)],
    "door": [("r", 6.), ("l", 3.)],
}
AVAILABLE_DIRECTIONS = list(PRESET_POINTS.keys())
AVAILABLE_DIRECTIONS += list(DIRECTIONS.keys())


def _make_req(command, parameter, verbose=True):
    if verbose:
        print(f"{datetime.now().time()} - {command.upper()} - {parameter}")
    tic_i = time()
    payload = PAYLOAD_MASK.format(command, parameter)
    _r = requests.post(URL, data=payload, headers=HEADERS)
    if verbose:
        print(
            f"{datetime.now().time()} - {command.upper()} - {parameter} "
            f"in {time() - tic_i:.3f} s"
        )


def ptz(direction="l", extra_wait=0., verbose=True):
    waiting_time = 2.5 + extra_wait
    d = DIRECTIONS[direction]
    tic = time()

    t1 = Thread(target=_make_req, args=("start", d, verbose,))
    t2 = Thread(target=_make_req, args=("stop", d, verbose,))

    t1.start()
    sleep(waiting_time)
    t2.start()

    if verbose:
        print(f"\n{datetime.now().time()} - Now waiting ... ")
    t1.join()
    toc_1 = time()
    if verbose:
        print(f"{datetime.now().time()} - R1 finished ... ")
    t2.join()
    if verbose:
        print(f"{datetime.now().time()} - R2 finished ... ")
    toc_2 = time()

    if verbose:
        print(
            f"=> TOOK {toc_2 - tic:.3f} s; "
            f"({toc_1 - tic:.3f} + {toc_2 - toc_1:.3f})"
        )


def _arg_parser():
    p = ArgumentParser()
    p.add_argument(
        "dir", help=f"Direction or preset point, as in {AVAILABLE_DIRECTIONS}"
    )
    p.add_argument(
        "duration", nargs="?", type=float, default=0.,
        help="Extra movement, in step fractions. (1 step ~ 2.5 sec)",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print information about the process."
    )
    return p.parse_args()


def _main():
    args = _arg_parser()
    # print(args)

    if args.dir in PRESET_POINTS:
        for operation in PRESET_POINTS[args.dir]:
            ptz(*operation, verbose=args.verbose)
        sys.exit(0)

    elif args.dir not in DIRECTIONS:
        print(f"BAD DIRECTION: {args.dir} not in {AVAILABLE_DIRECTIONS}")
        sys.exit(-1)

    ptz(args.dir, args.duration, args.verbose)


if __name__ == '__main__':
    _main()
