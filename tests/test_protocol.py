import socket
import unittest
import protocol
from unittest.mock import Mock

class TestFileMetadata(unittest.TestCase):

    def test_pack_unpack_metadata(self):
        filename = "test.zip"
        file_size = 12345

        data = protocol.pack_file_metadata(filename, file_size)

        result_filename, result_file_size = (
            protocol.unpack_file_metadata(data)
        )

        self.assertEqual(result_filename, filename)
        self.assertEqual(result_file_size, file_size)

    def test_unicode_filename(self):
        filename = "मेरा_file.zip"
        file_size = 5000

        data = protocol.pack_file_metadata(filename, file_size)

        result_filename, result_file_size = (
            protocol.unpack_file_metadata(data)
        )

        self.assertEqual(result_filename, filename)
        self.assertEqual(result_file_size, file_size)

    def test_filename_too_long(self):
        filename = "a" * 256

        with self.assertRaises(ValueError):
            protocol.pack_file_metadata(filename, 100)


class TestMessages(unittest.TestCase):

    def test_send_receive_message(self):
        sender, receiver = socket.socketpair()

        try:
            payload = b"hello world"

            protocol.send_message(sender, payload)
            received = protocol.receive_message(receiver)

            self.assertEqual(received, payload)

        finally:
            sender.close()
            receiver.close()


class TestRecvExactly(unittest.TestCase):

    def test_recv_exactly_handles_partial_reads(self):
        fake_socket = Mock()
        fake_socket.recv.side_effect = [b"ab", b"cd"]

        result = protocol.recv_exactly(fake_socket, 4)

        self.assertEqual(result, b"abcd")
        self.assertEqual(fake_socket.recv.call_count, 2)

    def test_recv_exactly(self):
        sender, receiver = socket.socketpair()

        try:
            sender.sendall(b"hello")
            sender.sendall(b"world")

            result = protocol.recv_exactly(receiver, 10)

            self.assertEqual(result, b"helloworld")

        finally:
            sender.close()
            receiver.close()

    def test_recv_exactly_connection_closed(self):
        sender, receiver = socket.socketpair()

        try:
            sender.sendall(b"hello")
            sender.close()

            with self.assertRaises(ConnectionError):
                protocol.recv_exactly(receiver, 10)

        finally:
            receiver.close()


if __name__ == "__main__":
    unittest.main()