import hashlib
import struct
import socket
import tempfile
import threading
import unittest
from pathlib import Path

import client
import protocol
import server


def unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class TestFileTransfer(unittest.TestCase):
    def transfer_file(self, filename: str, contents: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / filename
            output_directory = Path(directory) / "received"
            source_path.write_bytes(contents)

            ready = threading.Event()
            result = []
            port = unused_local_port()
            server_thread = threading.Thread(
                target=lambda: result.append(
                    server.receive_file(
                        str(output_directory),
                        "127.0.0.1",
                        port,
                        ready,
                    )
                )
            )
            server_thread.start()
            self.assertTrue(ready.wait(timeout=2))

            digest = client.send_file(
                str(source_path),
                "127.0.0.1",
                port,
                show_progress=False,
            )

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(len(result), 1)
            self.assertIsNotNone(result[0])

            received_path = Path(result[0])
            self.assertEqual(received_path.read_bytes(), contents)
            self.assertEqual(digest, hashlib.sha256(contents).digest())
            return received_path.read_bytes()

    def test_binary_file_transfer(self):
        contents = bytes(range(256)) * 32
        self.assertEqual(
            self.transfer_file("binary file.bin", contents),
            contents,
        )

    def test_empty_file_transfer(self):
        self.assertEqual(self.transfer_file("empty file.bin", b""), b"")

    def start_server(self, output_directory: Path):
        ready = threading.Event()
        result = []
        port = unused_local_port()
        server_thread = threading.Thread(
            target=lambda: result.append(
                server.receive_file(
                    str(output_directory),
                    "127.0.0.1",
                    port,
                    ready,
                )
            )
        )
        server_thread.start()
        self.assertTrue(ready.wait(timeout=2))
        return server_thread, result, port

    def test_interrupted_transfer_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)

            with socket.create_connection(("127.0.0.1", port)) as connection:
                metadata = protocol.pack_file_metadata("partial.bin", 10)
                protocol.send_message(connection, metadata)
                connection.sendall(b"short")

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(list(output_directory.iterdir()), [])

    def test_checksum_mismatch_removes_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)

            with socket.create_connection(("127.0.0.1", port)) as connection:
                contents = b"valid file bytes"
                metadata = protocol.pack_file_metadata("invalid.bin", len(contents))
                protocol.send_message(connection, metadata)
                connection.sendall(contents)
                protocol.send_message(connection, b"wrong digest")

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(list(output_directory.iterdir()), [])

    def test_unsafe_filename_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)

            with socket.create_connection(("127.0.0.1", port)) as connection:
                filename = "../outside.bin"
                filename_bytes = filename.encode("utf-8")
                metadata = (
                    struct.pack("!B", len(filename_bytes))
                    + filename_bytes
                    + struct.pack("!Q", 0)
                )
                protocol.send_message(connection, metadata)

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(list(output_directory.iterdir()), [])

    def test_server_startup_failure_is_handled(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
                occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                occupied.bind(("127.0.0.1", 0))
                occupied.listen()
                port = occupied.getsockname()[1]

                result = server.receive_file(
                    str(Path(directory) / "received"),
                    "127.0.0.1",
                    port,
                )

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
