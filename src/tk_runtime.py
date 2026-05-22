"""Shared guard for Tk root lifetimes.

Tk/Tcl can crash natively on Windows when multiple independent ``tk.Tk()``
roots run in different threads.  The app still has a few Tk based windows, so
we serialize root lifetimes here instead of letting each module create roots
freely.
"""

from contextlib import contextmanager
import threading

from src.logger import setup_logger

log = setup_logger(__name__)

_TK_ROOT_LOCK = threading.RLock()


def acquire_tk_root(owner="tk"):
    """Acquire the process-wide Tk root guard."""
    log.debug("Waiting for Tk root guard: %s", owner)
    _TK_ROOT_LOCK.acquire()
    log.debug("Acquired Tk root guard: %s", owner)


def release_tk_root(owner="tk"):
    """Release the process-wide Tk root guard."""
    _TK_ROOT_LOCK.release()
    log.debug("Released Tk root guard: %s", owner)


@contextmanager
def exclusive_tk_root(owner="tk"):
    """Run a Tk root/mainloop while preventing concurrent Tk roots."""
    acquire_tk_root(owner)
    try:
        yield
    finally:
        release_tk_root(owner)
