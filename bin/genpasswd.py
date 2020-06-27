#!/usr/bin/env python3

import argparse
import logging
import math
import string
import sys
import unittest
from contextlib import closing
from dataclasses import dataclass
from random import Random
from secrets import SystemRandom
from typing import List, Optional, TextIO

#################################
# GENERATE PASSWORD APPLICATION #
#################################

# Some helpful constants

DEFAULT_DICT_FILE = "/usr/share/dict/words"
DEFAULT_WORD_COUNT = 4
DEFAULT_SYMBOL_COUNT = 12
DEFAULT_WORD_SEPARATOR = "-"
SYMBOLS = string.ascii_letters + string.digits + string.punctuation
MIN_WORD_LENGTH = 2


@dataclass
class GenPasswordArgs:
    symbols: bool
    num_words: Optional[int]
    dict_file: Optional[TextIO]
    verbose: bool
    test: bool

    @classmethod
    def from_parse_args(cls, args) -> "GenPasswordArgs":
        return cls(**args.__dict__)


@dataclass
class GenPasswordConfig:
    use_symbols: bool
    num_choices: int
    dict_file: Optional[TextIO]
    separator: str
    symbols: str
    prng: Random
    logger: logging.Logger


def make_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a random password according to https://xkcd.com/936/."
    )
    parser.add_argument(
        "-s",
        "--symbols",
        action="store_true",
        default=False,
        help="Generate random symbols instead of words.",
    )
    parser.add_argument(
        "-n",
        "--num-words",
        metavar="N",
        default=None,
        type=int,
        help=(
            "Number of words or symbols to generate. "
            "Default is {} words or {} symbols if using -s option."
        ).format(DEFAULT_WORD_COUNT, DEFAULT_SYMBOL_COUNT),
    )
    parser.add_argument(
        "-f",
        "--dict-file",
        metavar="FILE",
        type=argparse.FileType("r"),
        default=None,
        help="Use the specified file as input dictionary.",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Verbose mode."
    )
    parser.add_argument(
        "--test",
        default=False,
        action="store_true",
        help="Run tests. Must be the only argument.",
    )
    return parser


def init_from_args(args: GenPasswordArgs) -> GenPasswordConfig:
    logger = init_logger(args.verbose)

    num_choices = args.num_words

    if not num_choices:
        if args.symbols:
            num_choices = DEFAULT_SYMBOL_COUNT
        else:
            num_choices = DEFAULT_WORD_COUNT

    dict_file = args.dict_file
    if not args.test and not args.symbols and not dict_file:
        dict_file = open(DEFAULT_DICT_FILE, "r")

    return GenPasswordConfig(
        use_symbols=args.symbols,
        num_choices=num_choices,
        dict_file=dict_file,
        separator=("" if args.symbols else DEFAULT_WORD_SEPARATOR),
        symbols=SYMBOLS,
        prng=SystemRandom(),
        logger=logger,
    )


def init_logger(verbose_level: int) -> logging.Logger:
    log_format = "%(levelname)s: %(message)s"
    logging.basicConfig(format=log_format)
    logger = logging.getLogger(__name__)
    if verbose_level:
        logger.setLevel(logging.INFO)
    else:
        # Use parent logger's level
        logger.setLevel(logging.NOTSET)
    return logger


def get_elements(cfg: GenPasswordConfig) -> List[str]:
    log = cfg.logger
    if cfg.use_symbols:
        log.info("Using %d symbols from: %s", cfg.num_choices, cfg.symbols)
        elements = [s for s in cfg.symbols]
    elif cfg.dict_file:
        log.info("Using %d words from: %s", cfg.num_choices, cfg.dict_file.name)
        elements = [
            w.strip()
            for w in cfg.dict_file.readlines()
            if len(w.strip()) >= MIN_WORD_LENGTH
        ]
    else:
        err = "use_symbols is False and dict_file is empty in {}".format(cfg)
        raise ValueError(err)
    return elements


def entropy(population_n: int, num_choices: int) -> float:
    return math.log2(population_n ** num_choices)


def choose(prng: Random, num_choices: int, elements: List[str]) -> List[str]:
    return [prng.choice(elements) for _ in range(num_choices)]


def main() -> None:
    parser = make_argparser()
    args = GenPasswordArgs.from_parse_args(parser.parse_args())

    if args.test:
        raise ValueError("When --test is used it must be the only argument.")

    cfg = init_from_args(args)

    log = cfg.logger

    elements = get_elements(cfg)
    choices = choose(cfg.prng, cfg.num_choices, elements)
    password_entropy = entropy(len(elements), cfg.num_choices)

    log.info("Entropy: %.2f bits", password_entropy)
    print(cfg.separator.join(choices))


###########################
# GENERATE PASSWORD TESTS #
###########################

# Some helpful testing constants

# 1000 is arbitrary. Just want to have some choices in our word dictionary.
DEFAULT_DICT_FLOOR = 1000

# We want to have at least this many bits of entropy in our passwords by
# default.
DEFAULT_ENTROPY_FLOOR = 64


class TestingMixin(unittest.TestCase):
    def setUp(self):
        self.parser = make_argparser()
        self.args = GenPasswordArgs.from_parse_args(self.parser.parse_args([]))
        # Prevent init_from_args from opening the dict file handle.
        self.args.test = True

    def assertIsCallable(self, v):
        self.assertTrue(callable(v))

    def assertIsEmpty(self, v):
        self.assertFalse(bool(v))

    def assertIsNotEmpty(self, v):
        self.assertTrue(bool(v))


class CliArgumentsTest(TestingMixin, unittest.TestCase):
    def test_arg_defaults(self):
        self.assertFalse(self.args.symbols)
        self.assertIsNone(self.args.num_words)
        self.assertIsNone(self.args.dict_file)
        self.assertEqual(self.args.verbose, 0)


class InitLoggingTest(TestingMixin, unittest.TestCase):
    def test_init_logger(self):
        logger = init_logger(0)
        self.assertIsCallable(logger.info)

    def test_verbose_0(self):
        logger = init_logger(0)
        self.assertEqual(logger.level, logging.NOTSET)
        self.assertEqual(logger.root.level, logging.WARN)

    def test_verbose_1(self):
        logger = init_logger(1)
        self.assertEqual(logger.level, logging.INFO)


class InitFromArgsTest(TestingMixin, unittest.TestCase):
    def test_init_from_args_defaults(self):
        cfg = init_from_args(self.args)
        self.assertFalse(cfg.use_symbols)
        self.assertEqual(cfg.num_choices, DEFAULT_WORD_COUNT)
        self.assertIsNone(cfg.dict_file)  # None because we're in test mode.
        self.assertEqual(cfg.separator, DEFAULT_WORD_SEPARATOR)
        self.assertIsCallable(cfg.prng.choice)
        self.assertIsCallable(cfg.logger.info)

    def test_init_from_args_with_symbols(self):
        self.args.symbols = True
        cfg = init_from_args(self.args)
        self.assertTrue(cfg.use_symbols)
        self.assertEqual(cfg.num_choices, DEFAULT_SYMBOL_COUNT)
        self.assertIsNone(cfg.dict_file)  # None because we're in symbols mode.
        self.assertEqual(cfg.separator, "")
        self.assertEqual(cfg.symbols, SYMBOLS)
        self.assertIsCallable(cfg.prng.choice)
        self.assertIsCallable(cfg.logger.info)


class GetElementsSymbolsTest(TestingMixin, unittest.TestCase):
    def test_get_elements_symbols(self):
        self.args.symbols = True
        cfg = init_from_args(self.args)
        elements = get_elements(cfg)
        self.assertEqual("".join(elements), SYMBOLS)


class GetElementsDictTest(TestingMixin, unittest.TestCase):
    def test_get_elements_dict(self):
        # Override to allow init_from_args top open the dict file handle.
        self.args.test = False
        cfg = init_from_args(self.args)
        with closing(cfg.dict_file):
            elements = get_elements(cfg)
        self.assertGreater(len(elements), DEFAULT_DICT_FLOOR)


class EntropyTest(unittest.TestCase):
    def test_entropy_calc(self):
        self.assertAlmostEqual(entropy(2, 16), 16)

    def test_default_symbol_entropy(self):
        self.assertGreaterEqual(
            entropy(len(SYMBOLS), DEFAULT_SYMBOL_COUNT), DEFAULT_ENTROPY_FLOOR
        )


class DictEntropyTest(TestingMixin, unittest.TestCase):
    def test_default_dict_entropy(self):
        # Override to allow init_from_args top open the dict file handle.
        self.args.test = False
        cfg = init_from_args(self.args)
        with closing(cfg.dict_file):
            elements = get_elements(cfg)
        self.assertGreaterEqual(
            entropy(len(elements), cfg.num_choices), DEFAULT_ENTROPY_FLOOR
        )


class ChooseTest(unittest.TestCase):
    def test_choose_symbols(self):
        prng = SystemRandom()
        choice = choose(prng, DEFAULT_SYMBOL_COUNT, SYMBOLS)
        self.assertEqual(len(choice), DEFAULT_SYMBOL_COUNT)


############################
# RUN APPLICATION OR TESTS #
############################

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        sys.argv.pop()
        unittest.main()
    else:
        main()
