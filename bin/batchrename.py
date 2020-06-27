#!/usr/bin/env python3

import argparse
import contextlib
import glob
import io
import logging
import os
import pathlib
import re
import sys
import unittest
from dataclasses import dataclass
from unittest import mock
from typing import Generator, Iterable, Optional, Tuple, List

############################
# BATCH RENAME APPLICATION #
############################


@dataclass
class BatchRenameArgs:
    dry_run: bool
    walk: str
    glob: Optional[str]
    ignore_case: bool
    zero_pad: int
    renumber_group: Optional[str]
    renumber_from: int
    verbose: bool
    test: bool
    pattern: str
    replacement: str
    files: List[str]

    @classmethod
    def from_parse_args(cls: type, args: argparse.Namespace) -> "BatchRenameArgs":
        return cls(**args.__dict__)


@dataclass
class BatchRenameConfig:
    pattern: str
    replacement: str
    files: Iterable[str]
    renumber_from: int
    renumber_offset: int
    zero_pad: int
    renumber_match_group: Optional[int]
    regex_flags: int
    dry_run: bool
    logger: logging.Logger


def make_argparser() -> argparse.ArgumentParser:
    """Return CLI argument parser instance for batchrename application."""
    parser = argparse.ArgumentParser(
        description=(
            "Batch rename all files in a directory or directory tree. "
            "Unless otherwise specified, walks the directory tree rooted at the current directory."
        )
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        default=False,
        help="Output the rename that would happen instead of performing the rename.",
    )
    parser.add_argument(
        "-w",
        "--walk",
        metavar="DIR_PATH",
        default=".",
        help="Walk the directory tree, rooted at the current directory by default.",
    )
    parser.add_argument(
        "-g",
        "--glob",
        default=None,
        help="Glob to select filenames to examine. Overrides --walk argument if present.",
    )
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        default=False,
        help="Ignore uppercase/lowercase distinctions in filename.",
    )
    parser.add_argument(
        "-z",
        "--zero-pad",
        metavar="Z",
        type=int,
        default=1,
        help=(
            "Number of digits to pad to when renumbering files with {n} "
            "(see help for replacement argument). For example, Z=3 "
            "will transform 1 -> 001."
        ),
    )
    parser.add_argument(
        "-m",
        "--renumber-group",
        metavar="MATCH_GROUP",
        help=(
            "Use a match group to renumber from, instead of processing order. "
            "The group must be an integer value. Offset using + and -. "
            "For example, -g 2-10 will subtract 10 from the integer in match group 2."
        ),
    )
    parser.add_argument(
        "-r",
        "--renumber-from",
        metavar="FIRST",
        type=int,
        default=1,
        help=(
            "What number to start renumbering from, when renumbering files with {n}. "
            "Default is 1."
        ),
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
    parser.add_argument(
        "pattern", type=str, help="Filename regular expression pattern to match."
    )
    parser.add_argument(
        "replacement",
        type=str,
        help=(
            "Replacement string, can reference match groups in pattern with \\d "
            "for match group d. Use {n} for renumbering files based on the "
            "order they are processed. (Use {{}n} for a literal {n}.)"
        ),
    )
    parser.add_argument(
        "files",
        metavar="file",
        nargs="*",
        help=(
            "File(s) to rename. "
            "Use single hyphen ('-') to process filenames from standard input. "
            "If any files are present, overrides --walk, --glob arguments."
        ),
    )
    return parser


def init_from_args(args: BatchRenameArgs) -> BatchRenameConfig:
    logger = init_logger(args.verbose)
    file_generator = gen_files(args.files, args.glob, args.walk)
    match_group, offset = init_renumbering(args.renumber_group)
    return BatchRenameConfig(
        pattern=args.pattern,
        replacement=args.replacement,
        files=file_generator,
        renumber_from=args.renumber_from,
        renumber_offset=offset,
        zero_pad=args.zero_pad,
        renumber_match_group=match_group,
        regex_flags=(re.IGNORECASE if args.ignore_case else 0),
        dry_run=args.dry_run,
        logger=logger,
    )


def init_logger(verbose_level: int = 0) -> logging.Logger:
    log_format = "%(levelname)s: %(message)s"
    logging.basicConfig(format=log_format)
    logger = logging.getLogger(__name__)
    if verbose_level > 1:
        logger.setLevel(logging.DEBUG)
    elif verbose_level:
        logger.setLevel(logging.INFO)
    else:
        # Use parent logger's level
        logger.setLevel(logging.NOTSET)
    return logger


def gen_files(
    files: Iterable[str], glob_expr: Optional[str], walk_root: str
) -> Generator[str, None, None]:
    """Generate files for batchrename.

    If files is non-empty, yield file names from the input one at a time. But
    if any of the filenames are "-" then switch to yielding file names from
    standard input instead, one file name per line.

    If files is empty and glob_expr is non-empty, yield from glob.

    Otherwise yield from walking the tree starting at walk_root.

    """
    if files:
        for f in files:
            if f == "-":
                yield from (s.strip() for s in sys.stdin)
            else:
                yield f
    elif glob_expr:
        yield from glob.glob(glob_expr)
    else:
        yield from walk_tree(walk_root)


def walk_tree(root: str) -> Generator[str, None, None]:
    """Walk the directory tree starting at root.

    Yield each file and directory name under root one at a time.

    """
    for path, dirnames, filenames in os.walk(root):
        yield from (os.path.join(path, d) for d in dirnames)
        yield from (os.path.join(path, f) for f in filenames)


def init_renumbering(renumber_group: Optional[str] = None) -> Tuple[Optional[int], int]:
    """Return renumber match group and renumber offset to use.

    Parse a renumbering format string of the form N(+|-)M and return the match
    group N and positive or negative offset M. For example, 2-10 would return
    match group 2 with offset -10.

    """
    if not renumber_group:
        return None, 0
    m = re.match(r"([0-9]+)(?:(\+|-)([0-9]+))?", renumber_group)
    if not m:
        raise ValueError(f"Invalid renumbering match group format: {renumber_group}")
    g = m.groups()
    renumber_match_group = int(g[0])
    renumber_offset = 0
    if g[1] == "+":
        renumber_offset = int(g[2])
    elif g[1] == "-":
        renumber_offset = 0 - int(g[2])
    return (renumber_match_group, renumber_offset)


def batch_rename(cfg: BatchRenameConfig) -> None:
    """Perform batch file renames from a configuration."""
    log = cfg.logger

    # Initialize the file name pattern matcher.
    matcher = re.compile(cfg.pattern, cfg.regex_flags)

    # Iterate over the files to rename and enumerate them for potential
    # renumbering.
    for idx, old_file in enumerate(cfg.files, cfg.renumber_from):
        log.debug("Processing %s", repr(old_file))
        replacement_n = cfg.replacement

        # Replace {n} with the right file renumbering, either from match group
        # or processing order.
        if cfg.renumber_match_group:
            # Replace {n} with value from match group.
            m = matcher.match(old_file)
            if m:
                old_n = int(m.group(cfg.renumber_match_group))
                n = old_n + cfg.renumber_offset
                replacement_n = replacement_n.replace("{n}", str(n).zfill(cfg.zero_pad))
                log.debug(
                    "Renumber %d -> %d from match group %d",
                    old_n,
                    n,
                    cfg.renumber_match_group,
                )
        else:
            # Replace {n} with number from processing order, starting from a
            # first number (usually 1).
            n = idx
            replacement_n = replacement_n.replace("{n}", str(n).zfill(cfg.zero_pad))
            log.debug("Renumber to %d from file processing order", n)

        # For the rare instance we want a literal {n} in the filename, we have
        # to escape it. This lets us write {{}n} to get a literal {n}.
        replacement_n = replacement_n.replace("{{}", "{")

        new_file = matcher.sub(replacement_n, old_file)

        if old_file == new_file:
            log.debug("Ignoring %s, no change in name", repr(old_file))
            continue

        if cfg.dry_run:
            log.info("Rename (dry run): %s -> %s", repr(old_file), repr(new_file))
            print(f"Rename: {old_file} -> {new_file}")
        else:
            log.info("Rename: %s -> %s", repr(old_file), repr(new_file))
            pathlib.Path(old_file).rename(new_file)


def main() -> None:
    """Run batchrename file renaming application."""
    # Parse command line input arguments.
    parser = make_argparser()
    args = BatchRenameArgs.from_parse_args(parser.parse_args())

    if args.test:
        raise ValueError("When --test is used it must be the only argument.")

    # Initialize the application from arguments.
    cfg = init_from_args(args)

    batch_rename(cfg)


######################
# BATCH RENAME TESTS #
######################


class CliArgumentsTest(unittest.TestCase):
    def test_arg_defaults(self):
        parser = make_argparser()
        args = BatchRenameArgs.from_parse_args(
            parser.parse_args(["PATTERN", "REPLACEMENT"])
        )
        self.assertFalse(args.dry_run)
        self.assertEqual(args.walk, ".")
        self.assertIsNone(args.glob)
        self.assertFalse(args.ignore_case)
        self.assertEqual(args.zero_pad, 1)
        self.assertIsNone(args.renumber_group)
        self.assertEqual(args.renumber_from, 1)
        self.assertEqual(args.verbose, 0)
        self.assertEqual(args.pattern, "PATTERN")
        self.assertEqual(args.replacement, "REPLACEMENT")
        self.assertEqual(len(args.files), 0)


class BatchRenameTest(unittest.TestCase):
    def _capture_output(self, cfg: BatchRenameConfig) -> List[Tuple[str, str]]:
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            batch_rename(cfg)
        renames = []
        for line in f.getvalue().split("\n"):
            if line:
                old_file, new_file = line[8:].strip().split(" -> ")
                renames.append((old_file, new_file))
        return renames

    def setUp(self):
        self.args = BatchRenameArgs(
            dry_run=True,
            walk=".",
            glob=None,
            ignore_case=False,
            zero_pad=1,
            renumber_group=None,
            renumber_from=1,
            verbose=False,
            test=True,
            pattern="PATTERN",
            replacement="REPLACEMENT",
            files=[],
        )

    def test_simple_rename(self):
        self.args.pattern = r"file_(\d+)\.txt"
        self.args.replacement = r"\1-file.txt"
        self.args.files = ["file_200.txt"]
        cfg = init_from_args(self.args)
        renames = self._capture_output(cfg)
        self.assertEqual(renames, [("file_200.txt", "200-file.txt")])

    def test_renumber_reorder(self):
        self.args.renumber_from = 17
        self.args.zero_pad = 3
        self.args.pattern = r"file_(\d+)\.txt"
        self.args.replacement = r"{n}-file.txt"
        self.args.files = ["file_200.txt", "file_300.txt"]
        cfg = init_from_args(self.args)
        renames = self._capture_output(cfg)
        self.assertEqual(
            renames,
            [("file_200.txt", "017-file.txt"), ("file_300.txt", "018-file.txt")],
        )

    def test_squiggly(self):
        self.args.renumber_from = 17
        self.args.zero_pad = 3
        self.args.pattern = r"file_(\d+)\.txt"
        self.args.replacement = r"{n}-{{}}file.txt"
        self.args.files = ["file_200.txt"]
        cfg = init_from_args(self.args)
        renames = self._capture_output(cfg)
        self.assertEqual(renames, [("file_200.txt", "017-{}file.txt")])

    def test_renumber_group(self):
        self.args.pattern = r"file_(\d+)\.txt"
        self.args.replacement = r"{n}-file.txt"
        self.args.renumber_group = "1-150"
        self.args.files = ["file_200.txt"]
        cfg = init_from_args(self.args)
        renames = self._capture_output(cfg)
        self.assertEqual(renames, [("file_200.txt", "50-file.txt")])

    @mock.patch("sys.stdin", ["file_1.txt", "file_2.txt"])
    def test_stdin(self):
        self.args.pattern = r"file_(\d+)\.txt"
        self.args.replacement = r"\1-file.txt"
        self.args.files = ["-"]
        cfg = init_from_args(self.args)
        renames = self._capture_output(cfg)
        self.assertEqual(
            renames, [("file_1.txt", "1-file.txt"), ("file_2.txt", "2-file.txt")]
        )


############################
# RUN APPLICATION OR TESTS #
############################

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        sys.argv.pop()
        unittest.main()
    else:
        main()
