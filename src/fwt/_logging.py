"""Logging for FWT."""
import logging
from typing import Optional


LOG_LEVELS = ["QUIET", "ERROR", "WARNING", "INFO", "DEBUG"]


def setup_logging(loglevel: str, logfile: Optional[str] = None) -> None:
    """Setup logging for FWT.

    Args:
        loglevel: Log level for console output.
        logfile: File to output log messages to. Defaults to ``None``.
    """
    if logfile:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
    if loglevel != "QUIET":
        if logfile:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(loglevel)
            logging.getLogger("").addHandler(console_handler)
        else:
            logging.basicConfig(level=loglevel)
