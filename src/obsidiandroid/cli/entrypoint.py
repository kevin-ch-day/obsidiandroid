"""Dispatch the installed command and the source-checkout launcher."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib import import_module
import sys

_COMMAND_MODULES = {
    "analysis": ".analysis",
    "pi-v2": ".permission_v2",
}


def parse_menu_args(argv: Sequence[str], *, show_commands: bool = False) -> None:
    """Handle operator menu help and reject unexpected arguments."""
    epilog = None
    if show_commands:
        commands = ", ".join(_COMMAND_MODULES)
        epilog = f"Commands: {commands}. Run obsidiandroid COMMAND --help for command options."
    parser = argparse.ArgumentParser(
        prog="obsidiandroid",
        description="Launch the interactive ObsidianDroid operator console.",
        epilog=epilog,
    )
    parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a subcommand or launch the default operator menu."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and (target := _COMMAND_MODULES.get(arguments[0])):
        command = import_module(target, __package__)
        return command.main(arguments[1:], prog=f"obsidiandroid {arguments[0]}")
    if arguments:
        parse_menu_args(arguments, show_commands=True)

    from .startup_menu import main as launch_menu

    return launch_menu([])
