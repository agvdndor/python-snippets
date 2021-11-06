"""Boilerplate code for an agent that sends and receives
messages over TCP/IP either as a client or as a server"""

from abc import ABC, abstractmethod
import logging
import socket
from threading import Event, Thread
from queue import Empty, Queue
import time
from typing import Any, Dict

from helpers import get_logger, receive_n_bytes, SocketDisconnectedException

class TCPAgent(Thread, ABC):
    """Abstract Parent object for Recv and Send Thread over TCP/IP.
    It handles the lifecycle of its member threads and the
    socket connect/disconnect."""
    def __init__(self,
                 address: str = "127.0.0.1",
                 port: int = 6969,
                 log_level = logging.ERROR,
                 recv_fixed_length: bool = False,
                 recv_length_descriptor_size: int = 8,
                 recv_message_length: int = None,
                 send_fixed_length: bool = False,
                 send_length_descriptor_size: int = 8,
                 send_message_length: int = None,
                 send_thread_cls = None,
                 send_thread_cls_kwargs: Dict[str, Any] = None,
                 recv_thread_cls = None,
                 recv_thread_cls_kwargs: Dict[str, Any] = None):
        """Init TCPAgent.

        Args:
            address (str, optional): Address to connect/bind socket to. Defaults to "127.0.0.1".
            port (int, optional): Port to connect/bind socket to. Defaults to 6969.
            log_level (logging.LEVEL, optional): Logging level. Defaults to logging.ERROR.
            recv_fixed_length (bool, optional): Fixed length message communication or not.
            Defaults to False.
            recv_length_descriptor_size (int, optional): Size of length descriptor for
            variable size message sending, only relevant if recv_fixed_length=False. Defaults to 8.
            recv_message_length (int, optional): Lenght of fixed length message communication,
            only relevant if recv_fixed_length=True. Defaults to None.
            send_fixed_length (bool, optional): Fixed length message communication
            for sending or not. Defaults to False.
            send_length_descriptor_size (int, optional): Size of length descriptor for
            variable size message sending only relevant if send_fixed_length=False. Defaults to 8.
            send_message_length (int, optional): Size of fixed length message for fixed
            size message sending. Defaults to None.
            send_thread_cls (SendThread, optional): Custom SendThread class reference.
            Defaults to None.
            send_thread_cls_kwargs (Dict[str, Any], optional): Additional kwargs for custom
            SendThread class. Defaults to None.
            recv_thread_cls (RecvThread, optional): Custom RecvThread class reference.
            Defaults to None.
            recv_thread_cls_kwargs (Dict[str, Any], optional): Additional kwargs for custom
            Recvthread class. Defaults to None.
        """
        self.address = address
        self.port = port
        self.send_queue = Queue()
        self.recv_queue = Queue()

        # to avoid dangerous default value {}
        if send_thread_cls_kwargs is None:
            send_thread_cls_kwargs = {}
        if recv_thread_cls_kwargs is None:
            recv_thread_cls_kwargs = {}

        if send_thread_cls:
            self.send_thread = send_thread_cls(
                parent=self,
                fixed_length = send_fixed_length,
                send_message_length = send_message_length,
                send_length_descriptor_size=send_length_descriptor_size,
                **send_thread_cls_kwargs)
        else:
            self.send_thread = SendThread(
                parent=self,
                fixed_length = send_fixed_length,
                send_message_length = send_message_length,
                send_length_descriptor_size=send_length_descriptor_size)

        if recv_thread_cls:
            self.recv_thread = recv_thread_cls(
                parent=self,
                fixed_length=recv_fixed_length,
                recv_message_length=recv_message_length,
                recv_length_descriptor_size=recv_length_descriptor_size,
                **recv_thread_cls_kwargs)
        else:
            self.recv_thread = RecvThread(
                parent=self,
                fixed_length=recv_fixed_length,
                recv_message_length=recv_message_length,
                recv_length_descriptor_size=recv_length_descriptor_size)

        self.sock = None
        self._running = False
        self._terminated = True # stop signal has been sent
        self._running = False # thread has exited
        self.logger = get_logger(name=__name__ + "." + self.__class__.__name__,
                                 level=log_level)
        self.terminate_event = Event()
        super().__init__()

    @abstractmethod
    def connect(self) -> None:
        """Connect socket, called by RecvThread
        when a disconnected socket is discovered."""

    def start(self) -> None:
        """Start itself and member threads."""
        if not self._terminated:
            self.logger.warning("Thread was already started, call to start was ignored."
                             " Invoke terminate before calling start again")
            return

        self._terminated = False
        self.recv_thread.start()
        self.send_thread.start()
        super().start()

    def terminate(self) -> None:
        """Send terminate signal to itself
        member threads. Does not guarantee
        (immediate) termination."""
        if self._terminated:
            self.logger.warning("Thread was already terminated, call to terminate was ignored."
                                " Invoke start before calling terminate again")
            return

        self._terminated = True
        self.terminate_event.set()
        self.send_thread.terminate()
        self.recv_thread.terminate()
        for thread in [self.send_thread, self.recv_thread, self]:
            try:
                thread.join()
            except RuntimeError: #pylint: disable=broad-except
                pass # RuntimeError is raised if the thread finishes beofre we call join()
        self.disconnect()

    def is_terminated(self) -> bool:
        "Return whether the object has been terminated or not."
        return self._terminated

    def run(self) -> None:
        """Control is_running logic and call
        run_logic implemented by child classes."""
        self._running = True
        self.run_logic()
        self._running = False
        super().__init__()

    def run_logic(self) -> None:
        """Run loop. Should terminate gracefully when
        terminate() is called."""
        self.terminate_event.wait()

    def disconnect(self) -> None:
        """Disconnect socket and free system resources."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
        except Exception: #pylint: disable=broad-except
            pass # disconnect is best-effort

    def is_running(self) -> bool:
        """Whether the thread is still running or not."""
        return self._running


class SendThread(Thread):
    """Thread that is responsible for monitoring the
    send queue: popping, encoding, processing and sending the
    messages added to it."""
    def __init__(self,
                 parent,
                 fixed_length: bool = False,
                 send_message_length: int = None,
                 send_length_descriptor_size: int = None):
        """Init SendThread object.

        Args:
            parent (TCPAgent): parent TCPAgent object.
            fixed_length (bool, optional): Whether communication uses
            fixed length messages or not. Defaults to False.
            send_message_length (int, optional): The length of messages
            (if fixed_length=True). Defaults to None.
            send_length_descriptor_size (int, optional): The length of the size descriptor
            (if fixed_length=False). Defaults to None.
        """
        super().__init__()
        self._running = False
        self._terminated = True
        self.parent = parent
        self.fixed_length = fixed_length

        if self.fixed_length:
            if send_message_length is None:
                raise ValueError("If fixed_length is True then argument"
                                    "send_message_length must be provided")
            self.send_message_length = send_message_length
        else:
            if send_length_descriptor_size is None:
                raise ValueError("if fixed_length is False then argument"
                                    "send_length_descriptor_size must be provided")
            self.send_length_descriptor_size = send_length_descriptor_size

    def terminate(self) -> None:
        """Stop the SendThread."""
        self._terminated = True

    def start(self) -> None:
        """Start thread."""
        self._terminated = False
        super().start()

    def is_running(self) -> bool:
        "Return whether the object is still running or not."
        return self._running

    def is_terminated(self) -> bool:
        "Return whether the object has been terminated or not."
        return self._terminated

    def encode_message(self, message) -> bytes:
        """Encode the message object to bytestring.

        Args:
            message (Object): the message to encode

        Returns:
            bytes: the encoded message
        """
        return message.encode('utf-8')

    def process(self, message) -> None:
        """process outgoing message before encoding.
        To be overridden."""

    def send_or_retry(self, message) -> None:
        """Send message until successful or
        until the thread is being terminated.

        Args:
            message (Object): the message to send.
        """
        while not self._terminated:
            try:
                if self.parent.sock is None:
                    raise ConnectionError("Parent socket object is None")
                self.parent.sock.send(message)
                break
            except (ConnectionResetError, ConnectionError,
                    ConnectionAbortedError):
                time.sleep(1)

    def run(self) -> None:
        """Check the send queue for messages,
        encode them and send. Keep retrying until
        successful or terminate signal has been received"""
        self._running = True
        while not self._terminated:
            try:
                # get new message to send
                message = self.parent.send_queue.get(timeout=1)
                message_encoded = self.encode_message(message)
                if self.fixed_length and len(message_encoded) != self.send_message_length:
                    raise ValueError(f"Encoded message has length {len(message_encoded)}"
                                     + f"instead of fixed length {self.send_message_length}")
                self.parent.logger.debug("Sending message: %s, encoding: %s",
                                    str(message), message_encoded)

                if self.send_length_descriptor_size is not None:
                    message_encoded_size = f"{len(message_encoded):{'0' + str(self.send_length_descriptor_size) + 'd'}}" #pylint: disable=line-too-long
                    self.send_or_retry(message_encoded_size.encode('utf-8'))
                self.send_or_retry(message_encoded)
                self.process(message)
            except Empty:
                time.sleep(1)

        self.parent.logger.debug("send thread stopped.")
        self._running = False
        super().__init__() # Reset the thread object so that it can be restarted.


class RecvThread(Thread):
    """Class to receive, decode and process message. Additionally
    the RecvThread invokes its parent's connect method when it
    discovers a disconnected socket."""
    def __init__(self, parent,
                    fixed_length: bool = False,
                    recv_message_length: int = None,
                    recv_length_descriptor_size: int = None) -> None:
        """Init Recv Thread

        Args:
            parent (TCPAgent): reference to parent TCPagent object.
            fixed_length (bool, optional): Whether to use fixed length
            message communication. Defaults to False.
            recv_message_length (int, optional): The size of fixed length
            messages (only if fixed_length=True). Defaults to None.
            recv_length_descriptor_size (int, optional): The size of a length
            descriptor for variable size message communication
            (only if fixed_length=False). Defaults to None."""
        super().__init__()
        self._running = False
        self._terminated = False
        self.parent = parent

        self.fixed_length = fixed_length
        if self.fixed_length:
            if recv_message_length is None:
                raise ValueError("If fixed_length is True then argument"
                                    "recv_message_length must be provided")
            self.recv_message_length = recv_message_length
        else:
            if recv_length_descriptor_size is None:
                raise ValueError("if fixed_length is False then argument"
                                    "recv_length_descriptor_size must be provided")
            self.recv_length_descriptor_size = recv_length_descriptor_size


    def terminate(self):
        """Stop the receive thread."""
        self._terminated = True

    def start(self) -> None:
        """Start thread."""
        self._terminated = False
        super().start()

    def is_running(self) -> bool:
        "Return whether the object is still running or not."
        return self._running

    def is_terminated(self) -> bool:
        """Whether the thread has received the terminate signal or not."""
        return self._terminated

    def process(self, message) -> None:
        """Process the incoming message."""

    def decode_message(self, message: bytes) -> object:
        """Decode incoming bytestring

        Args:
            message (bytes): incoming bytestring

        Returns:
            Object: resulting message.
        """
        return message.decode()

    def recv(self) -> object:
        """Receive the next message according to the communication
        scheme chosen (fixed/variable length).

        Returns:
            object: the received message.
        """
        if self.fixed_length:
            message_encoded = receive_n_bytes(sock=self.parent.sock,
                                            num_bytes=self.recv_message_length,
                                            is_terminated_callback=self.is_terminated)
        else: # first receive variable message length and then receive actual message
            message_size_encoded = receive_n_bytes(sock=self.parent.sock,
                            num_bytes=self.recv_length_descriptor_size,
                            is_terminated_callback=self.is_terminated)
            message_size_decoded = int(message_size_encoded.decode())
            message_encoded = receive_n_bytes(
                sock=self.parent.sock,
                num_bytes=message_size_decoded,
                is_terminated_callback=self.is_terminated)
        message_decoded = self.decode_message(message_encoded)
        self.parent.logger.debug("received bytestring: %s, interpreted as %s",
                        message_encoded, str(message_decoded))
        self.parent.recv_queue.put(message_decoded)
        self.process(message_decoded)

    def run(self):
        """Receive, decode and process incoming messages. If a disconnected
        socket is discovered the parent's connect method is invoked."""
        self._running = True
        while not self._terminated:
            try:
                if self.parent.sock is None:
                    raise ConnectionError("Socket object is None.")
                else:
                    self.parent.sock.settimeout(2)
                self.recv()
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionError, WindowsError,
                    ConnectionAbortedError, OSError, SocketDisconnectedException):
                self.parent.disconnect()
                self.parent.connect()
                time.sleep(1)
            except Exception as e: #pylint: disable=broad-except
                if self._terminated:
                    break
                self.parent.logger.exception(e)

        self.parent.logger.debug("recv thread stopped.")
        self._running = False
        super().__init__() # Reset the thread object so that it can be restarted.

class TCPServer(TCPAgent):
    """Server implementation of TCPAgent class."""
    def connect(self) :
        """Accept incoming connection on PORT until
        an incoming connection is established or terminate()
        has been called."""
        # pylint: disable=invalid-name
        # wait till socket is connected
        self.logger.debug('(Re)connecting to Server...')
        while not self._terminated:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", self.port))
                    sock.settimeout(2)
                    sock.listen(1)
                    conn, _ = sock.accept()
                    self.sock = conn
                    self.logger.info("(Re)connected.")
                    return
                except socket.timeout:
                    pass
                except Exception as e: #pylint: disable=broad-except
                    self.logger.exception(e)


class TCPClient(TCPAgent):
    """Client implementation of TCPAgent class."""
    def connect(self):
        """Connect to the argument Address:Port. The method will block
        until a connection is established, a conneciton is not possible
        becasue there was already a connected socket or the plc is no longer
        running.

        After a connection is made, if possible, a type information message is sent immediately.
        Either a new one or the last sent one if present.
        """
        self.logger.debug('(Re)connecting to IO server...')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        while not self._terminated:
            try:
                self.sock.connect((self.address, self.port))
                self.logger.info("(Re)connected.")
                break
            except ConnectionRefusedError:
                time.sleep(1)
            except WindowsError as win_err:
                if win_err.winerror == 10056:
                    # socket is already reconnected
                    break
            except Exception as e: #pylint: disable=broad-except
                self.logger.exception(e)
