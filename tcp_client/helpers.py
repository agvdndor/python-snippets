"""Helpers for TCPAgent module."""
import sys
import logging
from typing import Callable
import socket

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

class SocketDisconnectedException(Exception):
    """Exception raised when calling recv() on a
    blocking socket with timeout set returned an
    empty bytestring, which indicates that the client
    is no longer connected."""

def receive_n_bytes(sock, num_bytes : int,
                    is_terminated_callback: Callable,
                    logger = None) -> bytes:
    """Receive exactly num_bytes bytes from the socket,
    sock.recv(n) in itself may return with less than n bytes

    Args:
        num_bytes (int): The number of bytes to read from the socket

    Returns:
        bytes: The byte string read from the socket
    """
    # wait on data (with max message size)
    data = b""
    total_to_recv = sys.getsizeof(data) + num_bytes
    remaining_bytes = num_bytes
    while remaining_bytes > 0 and not is_terminated_callback():
        try:
            received_bytes = sock.recv(remaining_bytes)
            if not received_bytes:
                raise SocketDisconnectedException("Client seems to be disconnected.")
            data += received_bytes
            remaining_bytes = total_to_recv - sys.getsizeof(data)
        except socket.timeout as e:
            if remaining_bytes != num_bytes:
                if logger is not None:
                    logger.error("A timeout error was raised by the socket:"
                                " causing an incomplete message to be read")
                raise e
    # otherwise frame is corrupt
    assert sys.getsizeof(data) == total_to_recv

    return data
