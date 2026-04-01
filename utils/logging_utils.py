"""
Logging utilities
-----------------
Context-aware utilities to add a per-step label to log records.

Usage:
    - Add `StepFilter()` to logging handlers (done in `main.setup_logging`).
    - Wrap step execution with `with step_context(step_number):` to include
      " - LeveL {n}" in the log level bracket, e.g. "[INFO - LeveL 2]".
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Optional

# Context variable holding the current step (or None)
_current_step: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "_current_step", default=None
)


def get_current_step() -> Optional[int]:
    return _current_step.get()


@contextmanager
def step_context(step: int):
    """Context manager that sets the current step for logging records.

    Example:
        with step_context(2):
            logger.info("...")  # formatted as [INFO - LeveL 2]
    """
    token = _current_step.set(step)
    try:
        yield
    finally:
        _current_step.reset(token)


class StepFilter(logging.Filter):
    """Logging filter that injects `step_label` into LogRecord.

    The formatter can include `%(step_label)s` to show either an empty
    string (when no step is set) or " - LeveL {n}" when a step is active.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - very small
        step = _current_step.get()
        if step is None:
            record.step_label = ""
        else:
            # Include a compact padded step code so logs show: [LEVEL - LeveL n - 00n]
            record.step_label = f" - LeveL {step} - {step:03d}"
        return True
