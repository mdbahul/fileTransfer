import socket
import struct
import unittest
import uuid
from unittest.mock import Mock

import protocol


class TestFileMetadata(unittest.TestCase):
    def test_pack_unpack_metadata(self):
        transfer_id = uuid.uuid4()
        filename = "test.zip"
        file_size = 12345
        chunk_size = 4096

        data = protocol.pack_file_metadata(
            filename,
            file_size,
            transfer_id,
            chunk_size,
        )

        (
            result_transfer_id,
            result_filename,
            result_file_size,
            result_chunk_size,
        ) = protocol.unpack_file_metadata(data)

        self.assertEqual(result_transfer_id, transfer_id)
        self.assertEqual(result_filename, filename)
        self.assertEqual(result_file_size, file_size)
        self.assertEqual(result_chunk_size, chunk_size)

    def test_unicode_filename(self):
        transfer_id = uuid.uuid4()
        filename = "मेरा_file.zip"
        file_size = 5000
        chunk_size = 4096

        data = protocol.pack_file_metadata(
            filename,
            file_size,
            transfer_id,
            chunk_size,
        )

        (
            result_transfer_id,
            result_filename,
            result_file_size,
            result_chunk_size,
        ) = protocol.unpack_file_metadata(data)

        self.assertEqual(result_transfer_id, transfer_id)
        self.assertEqual(result_filename, filename)
        self.assertEqual(result_file_size, file_size)
        self.assertEqual(result_chunk_size, chunk_size)

    def test_filename_too_long(self):
        transfer_id = uuid.uuid4()
        filename = "a" * 256

        with self.assertRaises(ValueError):
            protocol.pack_file_metadata(filename, 100, transfer_id, 4096)

    def test_non_positive_chunk_size(self):
        transfer_id = uuid.uuid4()

        for chunk_size in (0, -1):
            with self.subTest(chunk_size=chunk_size):
                with self.assertRaises(ValueError):
                    protocol.pack_file_metadata(
                        "test.zip",
                        100,
                        transfer_id,
                        chunk_size,
                    )

    def test_metadata_too_short(self):
        with self.assertRaises(ValueError):
            protocol.unpack_file_metadata(b"\x00" * 28)

    def test_metadata_filename_length_must_fit_payload(self):
        transfer_id = uuid.uuid4()
        malformed = (
            transfer_id.bytes
            + struct.pack("!B", 10)
            + b"short"
            + struct.pack("!Q", 100)
            + struct.pack("!I", 4096)
        )

        with self.assertRaises(ValueError):
            protocol.unpack_file_metadata(malformed)

    def test_metadata_rejects_truncation(self):
        transfer_id = uuid.uuid4()
        metadata = protocol.pack_file_metadata(
            "test.zip",
            100,
            transfer_id,
            4096,
        )

        with self.assertRaises(ValueError):
            protocol.unpack_file_metadata(metadata[:-1])

    def test_metadata_rejects_trailing_bytes(self):
        transfer_id = uuid.uuid4()
        metadata = protocol.pack_file_metadata(
            "test.zip",
            100,
            transfer_id,
            4096,
        )

        with self.assertRaises(ValueError):
            protocol.unpack_file_metadata(metadata + b"\x00")


class TestMessages(unittest.TestCase):
    def test_hash_request_round_trip(self):
        data = protocol.pack_hash_request(3)

        self.assertEqual(protocol.unpack_hash_request(data), 3)

    def test_hash_response_round_trip(self):
        hashes = [b"a" * protocol.HASH_SIZE, b"b" * protocol.HASH_SIZE]
        data = protocol.pack_hash_response(hashes)

        self.assertEqual(protocol.unpack_hash_response(data), hashes)

    def test_hash_messages_reject_invalid_data(self):
        with self.assertRaises(ValueError):
            protocol.pack_hash_request(-1)

        with self.assertRaises(ValueError):
            protocol.unpack_hash_request(b"\x03")

        with self.assertRaises(ValueError):
            protocol.pack_hash_response([b"short"])

        with self.assertRaises(ValueError):
            protocol.unpack_hash_response(b"\x03" + b"\x00" * 8)

        response = protocol.pack_hash_response([b"a" * protocol.HASH_SIZE])
        with self.assertRaises(ValueError):
            protocol.unpack_hash_response(response[:-1])

        with self.assertRaises(ValueError):
            protocol.unpack_hash_response(response + b"\x00")

    def test_transfer_result_round_trip(self):
        for status in (
            protocol.TRANSFER_COMPLETE,
            protocol.TRANSFER_FAILED,
        ):
            with self.subTest(status=status):
                data = protocol.pack_transfer_result(status)
                self.assertEqual(protocol.unpack_transfer_result(data), status)

    def test_transfer_result_rejects_invalid_data(self):
        with self.assertRaises(ValueError):
            protocol.pack_transfer_result(protocol.START_TRANSFER)

        with self.assertRaises(ValueError):
            protocol.unpack_transfer_result(b"\x01\x00")

        with self.assertRaises(ValueError):
            protocol.unpack_transfer_result(b"\x01")

    def test_transfer_acceptance_round_trip(self):
        data = protocol.pack_transfer_acceptance()
        self.assertIsNone(protocol.unpack_transfer_acceptance(data))

    def test_transfer_acceptance_rejects_invalid_data(self):
        with self.assertRaises(ValueError):
            protocol.unpack_transfer_acceptance(b"\x01")

    def test_transfer_status_round_trip(self):
        for status in (protocol.START_TRANSFER, protocol.RESUME_TRANSFER):
            with self.subTest(status=status):
                data = protocol.pack_transfer_status(status, 4096)
                self.assertEqual(
                    protocol.unpack_transfer_status(data),
                    (status, 4096),
                )

    def test_transfer_status_rejects_invalid_data(self):
        with self.assertRaises(ValueError):
            protocol.unpack_transfer_status(b"\x01")

        with self.assertRaises(ValueError):
            protocol.pack_transfer_status(99, 0)

        with self.assertRaises(ValueError):
            protocol.pack_transfer_status(protocol.START_TRANSFER, -1)

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