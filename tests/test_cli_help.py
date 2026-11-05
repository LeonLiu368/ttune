"""Every command and subcommand prints its help: a stray % in a help string crashes argparse only when asked."""

import argparse
import contextlib
import importlib
import io

import pytest

MODULES = ["scraper", "envgen", "docgen", "evals", "harbortask", "viewer"]


def parser_of(module: str) -> argparse.ArgumentParser:
    """Capture the ArgumentParser a module's main() builds, without running the command."""
    main = importlib.import_module(f"{module}.__main__")
    captured = {}
    original = argparse.ArgumentParser.parse_args

    def grab(self, *args, **kwargs):
        captured.setdefault("parser", self)
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = grab
    try:
        with contextlib.suppress(SystemExit):
            main.main([])
    finally:
        argparse.ArgumentParser.parse_args = original
    return captured["parser"]


def walk(parser: argparse.ArgumentParser):
    yield parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                yield from walk(sub)


@pytest.mark.parametrize("module", MODULES)
def test_every_help_renders(module):
    for parser in walk(parser_of(module)):
        with contextlib.redirect_stdout(io.StringIO()):
            parser.format_help()
