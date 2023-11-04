#!/usr/bin/env python3

import argparse
import sys
from secrets import SystemRandom

######################
# CHOOSE APPLICATION #
######################


def make_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Choose a random input.")
    parser.add_argument("choices", nargs="*", help="Inputs to choose from.")
    return parser


def main() -> None:
    parser = make_argparser()
    args = parser.parse_args()
    if not args.choices or args.choices == ["-"]:
        choices = [s.strip() for s in sys.stdin.readlines()]
    else:
        choices = args.choices
    print(SystemRandom().choice(choices))


###################
# RUN APPLICATION #
###################

if __name__ == "__main__":
    main()
