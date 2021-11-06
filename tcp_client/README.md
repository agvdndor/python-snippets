# TCP Agent
Boilerplate code for an agent that sends and receives messages over TCP/IP either as a client or as a server. Currently limited to communication with 1 communication partner for simplicity.

## Usage
Two usage choices must be made:
1. who initiates the connection? Will my TCP agent be the server or the client? Choose `TCPServer` or `TCPClient` accordingly.

        # TCP agent initiates connection
        tcp_client = TCPClient(address="192.168.0.1", port=6969)

        # TCP agent accepts incoming connection
        tcp_server = TCPServer(address="127.0.0.1", port=6969)


2. Which communication scheme is used? Either fixed length messages or varaible length messages are supported right now. In the variable length scheme a fixed length descriptor containing the length of the following message is sent right before the actual message.

    * **Variable length for both send and recv thread**

            tcp_server = TCPServer(recv_fixed_length=False,
                            recv_length_descriptor_size=8,
                            send_length_descriptor_size=16,
                            log_level=logging.DEBUG)

            tcp_server.start()

    * **Fixed length for recv thread, variable length for send thread**

            tcp_server = TCPServer(recv_fixed_length=True,
                                   recv_message_length=8,
                                   send_fixed_length=False,
                                   send_length_descriptor_size=16)

            tcp_server.start()

## To implement manually
1. (Optional) Override `run_logic` method of the TCPAgent. The default implementation will wait idly for the terminate signal. The example below shows an implementation of an Echo server that simply responds with the incoming message.

        class EchoTCPServer(TCPServer):
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

2. (Optional) Override `encode_message` and `decode_message` in `SendThread` and `RecvThread` respectively. In the `Sendthread` a message is encoded after it has been popped from the `send_queue` and after it has been processed. In the `RecvThread` a message is decoded before being processed and being put in the `recv_queue`. The example below shows how it could be implemented for communication using a Ceasar Cipher.

        class CaesarCipherRecvThread(RecvThread):
            def __init__(self, *args, shift=1, **kwargs):
                super().__init__(*args, **kwargs)
                self.shift = shift

            def decode_message(self, message):
                """Shift message after utf-8 decoding"""
                message = message.decode()
                plain_text = ""
                for c in message:
                    # check if character is an uppercase letter
                    if c.isupper():
                        # find the position in 0-25
                        c_index = ord(c) - ord("A")
                        # perform the negative shift
                        new_index = (c_index - self.shift) % 26
                        # convert to new character
                        new_unicode = new_index + ord("A")
                        new_character = chr(new_unicode)
                        # append to plain string
                        plain_text = plain_text + new_character
                    else:
                        # since character is not uppercase, leave it as it is
                        plain_text += c
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
        assert received_msg == decrypted_msg

        server.terminate()
        client.terminate()

3. (Optional) Override `process` method in `SendThread` or `RecvThread`. A process function is called after decoding and after sending or receiving a message in the `SendThread` or `RecvThread` respectively. In the example below the process simply counts the amount of message sent/received

        class CountingRecvThread(RecvThread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.count = 0

            def process(self, _) -> None:
                self.count += 1

        class CountingSendThread(SendThread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.count = 0

            def process(self, _) -> None:
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