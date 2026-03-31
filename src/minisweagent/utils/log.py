from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

# Console instance shared across all minisweagent loggers.
_logging_console: Console | None = None

# The RichHandler attached to the root logger, kept so we can swap its console.
_rich_handler: RichHandler | None = None


def _ensure_setup() -> Console:
    """Lazily set up the root logger with a default Console if not yet done."""
    global _logging_console, _rich_handler

    if _logging_console is not None:
        return _logging_console

    return setup_logging()


def setup_logging(console: Console | None = None) -> Console:
    """Initialise (or re-initialise) the root ``minisweagent`` logger.

    Args:
        console: Rich Console to use for log output.  If *None* a new
                 stderr Console is created (suitable for non-batch / interactive
                 use).

    Returns:
        The Console instance attached to the logger.

    When called with a *console* argument after the logger has already been
    set up (e.g. at import time), the existing ``RichHandler`` is replaced so
    that all subsequent log output goes through the new Console.  This allows
    batch runners to call ``setup_logging(shared_console)`` **after** imports
    and have the shared Console take effect.
    """
    global _logging_console, _rich_handler

    if console is None:
        if _logging_console is not None:
            # Already initialised with defaults, nothing to do.
            return _logging_console
        console = Console(stderr=True, force_terminal=True)

    root = logging.getLogger("minisweagent")
    root.setLevel(logging.DEBUG)

    # Remove the previous RichHandler if we are re-initialising.
    if _rich_handler is not None:
        root.removeHandler(_rich_handler)

    handler = RichHandler(
        console=console,
        show_path=False,
        show_time=False,
        show_level=False,
        markup=True,
    )
    formatter = logging.Formatter("%(name)s: %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)

    _logging_console = console
    _rich_handler = handler

    return console


def get_logging_console() -> Console | None:
    """Return the Console currently used for logging (or *None*)."""
    return _logging_console


def add_file_handler(path: Path | str, level: int = logging.DEBUG, *, print_path: bool = True) -> None:
    root = logging.getLogger("minisweagent")
    handler = logging.FileHandler(path)
    handler.setLevel(level)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)
    if print_path:
        root.info(f"Logging to '{path}'")


# Auto-setup with default Console so that ``from minisweagent.utils.log import logger``
# works without an explicit ``setup_logging()`` call (e.g. interactive mode).
# Batch runners can later call ``setup_logging(shared_console)`` to switch to a
# shared Console before any worker threads start.
_ensure_setup()
logger = logging.getLogger("minisweagent")


__all__ = ["logger", "setup_logging", "get_logging_console", "add_file_handler"]
