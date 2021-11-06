"""Test suite for TCPAgent"""
from queue import Empty

import pytest

from tcp_agent import TCPServer, TCPClient, SendThread, RecvThread

@pytest.mark.timeout(10)
def test_send_receive_fixed_length_message():
    """Make connection and send fixed length string message."""
    test_msg_1 = "test_message1"
    test_msg_2 = "test_message2"

    tcp_server = TCPServer(recv_message_length=len(test_msg_1))
    tcp_client = TCPClient(recv_message_length=len(test_msg_1))
    tcp_server.start()
    tcp_client.start()

    tcp_client.send_queue.put(test_msg_1)
    tcp_server.send_queue.put(test_msg_2)

    recv_msg_client = tcp_client.recv_queue.get(block=True)
    assert recv_msg_client == test_msg_2
    recv_msg_server = tcp_server.recv_queue.get(block=True)
    assert recv_msg_server == test_msg_1

    tcp_server.terminate()
    tcp_client.terminate()

@pytest.mark.timeout(10)
def test_send_receive_variable_length_message():
    """Make connection and send variable length string message."""
    test_msg_1 = "test_message1_with some extra_padding"
    test_msg_2 = "test_message2"
    test_msg_3 = "another one"

    tcp_server = TCPServer(recv_fixed_length=False,
                           recv_length_descriptor_size=8,
                           send_length_descriptor_size=16)
    tcp_client = TCPClient(recv_fixed_length=False,
                           recv_length_descriptor_size=16,
                           send_length_descriptor_size=8)
    tcp_server.start()
    tcp_client.start()

    tcp_client.send_queue.put(test_msg_1)
    tcp_server.send_queue.put(test_msg_2)
    tcp_client.send_queue.put(test_msg_3)

    recv_msg_client = tcp_client.recv_queue.get(block=True)
    assert recv_msg_client == test_msg_2
    recv_msg_server = tcp_server.recv_queue.get(block=True)
    assert recv_msg_server == test_msg_1
    recv_msg_server = tcp_server.recv_queue.get(block=True)
    assert recv_msg_server == test_msg_3

    tcp_server.terminate()
    tcp_client.terminate()

def test_run_logic_override():
    """Test overriding the base TCPAgent logic."""
    class EchoTCPServer(TCPServer):
        """Echo all incoming messages back to the sender."""
        def run_logic(self) -> None:
            """Echo the incoming message back to the sender."""
            while not self.is_terminated():
                try:
                    msg = self.recv_queue.get(timeout=1)
                    self.send_queue.put(msg)
                except Empty:
                    continue

    echo_server = EchoTCPServer(port=6969,
                                recv_fixed_length=False,
                                recv_length_descriptor_size=8,
                                send_length_descriptor_size=8)
    client = TCPClient(port=6969,
                       recv_fixed_length=False,
                       recv_length_descriptor_size=8,
                       send_length_descriptor_size=8)

    echo_server.start()
    client.start()

    msg1 = "first test message to be echo'd"
    msg2 = "second message to be echo'd as well."

    client.send_queue.put(msg1)
    client.send_queue.put(msg2)

    echo_msg1 = client.recv_queue.get()
    assert echo_msg1 == msg1
    echo_msg2 = client.recv_queue.get()
    assert echo_msg2 == msg2

    client.terminate()
    echo_server.terminate()

def test_decode():
    """Test custom decoding fn."""
    class CaesarCipherRecvThread(RecvThread):
        """Recv thread that decodes messages accordign to
        a Ceasar cipher."""
        def __init__(self, *args, shift=1, **kwargs):
            """Init.

            Args:
                shift (int, optional): the shift value for the Caesar Cipher. Defaults to 1.
            """
            super().__init__(*args, **kwargs)
            self.shift = shift

        def decode_message(self, message):
            """Shift message after utf-8 decoding.
            source: https://likegeeks.com/python-caesar-cipher/#Encryption_for_Capital_Letters"""
            message = message.decode()
            plain_text = ""
            for char in message:
                # check if character is an uppercase letter
                if char.isupper():
                    # find the position in 0-25
                    c_index = ord(char) - ord("A")
                    # perform the negative shift
                    new_index = (c_index - self.shift) % 26
                    # convert to new character
                    new_unicode = new_index + ord("A")
                    new_character = chr(new_unicode)
                    # append to plain string
                    plain_text = plain_text + new_character
                else:
                    # since character is not uppercase, leave it as it is
                    plain_text += char
            return plain_text

    server = TCPServer(port=6969,
                       recv_fixed_length=False,
                       recv_length_descriptor_size=8,
                       recv_thread_cls=CaesarCipherRecvThread,
                       recv_thread_cls_kwargs={'shift': 3})

    client = TCPClient(port=6969,
                       send_length_descriptor_size=8)

    server.start()
    client.start()

    encrypted_msg = "GR BRX NQRZ WKH GHILQLWLRQ RI LQVDQLWB"
    decrypted_msg = "DO YOU KNOW THE DEFINITION OF INSANITY"

    client.send_queue.put(encrypted_msg)
    received_msg = server.recv_queue.get()
    try:
        assert received_msg == decrypted_msg
    except AssertionError:
        pass

    server.terminate()
    client.terminate()

def test_message_processing():
    """Test custom processing fn."""
    class CountingRecvThread(RecvThread):
        """RecvThread that counts the number of received messages."""
        def __init__(self, *args, **kwargs):
            """Init."""
            super().__init__(*args, **kwargs)
            self.count = 0

        def process(self, _) -> None:
            """Count number of messages."""
            self.count += 1

    class CountingSendThread(SendThread):
        """SendThread that counts the number of sent messages."""
        def __init__(self, *args, **kwargs):
            """Init."""
            super().__init__(*args, **kwargs)
            self.count = 0

        def process(self, _) -> None:
            """Count the number of messages."""
            self.count += 1

    server = TCPServer(port=6969,
                       send_thread_cls=CountingSendThread,
                       recv_thread_cls=CountingRecvThread)

    client = TCPClient(port=6969)

    server.start()
    client.start()

    server.send_queue.put("first message")
    server.send_queue.put("second message")
    client.send_queue.put("third message")

    server.recv_queue.get()
    client.recv_queue.get()
    client.recv_queue.get()

    assert server.recv_thread.count == 1
    assert server.send_thread.count == 2

    server.terminate()
    client.terminate()
