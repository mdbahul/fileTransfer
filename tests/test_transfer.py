import hashlib
import socket
import tempfile
import threading
import unittest
from pathlib import Path

import client
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


if __name__ == "__main__":
    unittest.main()
