"""Helpers for TCPAgent module."""
import sys
import logging

def get_logger(name: str, level) -> logging.Logger:
    """Return logger for calling module
    Args:
        name (str): [description]
        level ([type]): [description]
    Returns:
        logging.Logger: [description]
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt='[%(asctime)s] | %(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger