import hashlib
import os
import socket
import stat
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from pathlib import Path

import client
import protocol
import server
import utils


CHUNK_SIZE = 4096


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

            transfer_id = uuid.uuid4()
            digest = client.send_file(
                str(source_path),
                "127.0.0.1",
                port,
                transfer_id,
                CHUNK_SIZE,
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

    def test_directory_transfer_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            source_directory = Path(directory) / "project folder"
            (source_directory / "nested").mkdir(parents=True)
            (source_directory / "empty").mkdir()
            (source_directory / "root.txt").write_text("root contents")
            (source_directory / "nested" / "data.bin").write_bytes(
                bytes(range(256))
            )
            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)

            digest = client.send_file(
                str(source_directory),
                "127.0.0.1",
                port,
                uuid.uuid4(),
                CHUNK_SIZE,
                show_progress=False,
            )

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            received_directory = Path(result[0])
            self.assertEqual(received_directory.name, "received_project folder")
            self.assertEqual(
                (received_directory / "root.txt").read_text(),
                "root contents",
            )
            self.assertEqual(
                (received_directory / "nested" / "data.bin").read_bytes(),
                bytes(range(256)),
            )
            self.assertTrue((received_directory / "empty").is_dir())
            self.assertEqual(len(digest), protocol.HASH_SIZE)

    def test_directory_archive_rejects_malicious_paths(self):
        malicious_names = (
            "../escape.txt",
            "/absolute.txt",
            "C:/absolute.txt",
            "nested\\escape.txt",
        )
        for malicious_name in malicious_names:
            with self.subTest(malicious_name=malicious_name):
                with tempfile.TemporaryDirectory() as directory:
                    archive_path = Path(directory) / "malicious.zip"
                    output_directory = Path(directory) / "received"
                    output_directory.mkdir()
                    with zipfile.ZipFile(archive_path, "w") as archive:
                        archive.writestr(malicious_name, b"bad")

                    with self.assertRaises(ValueError):
                        utils.extract_directory_archive(
                            str(archive_path),
                            str(output_directory),
                            "safe-name",
                        )
                    self.assertFalse(
                        (output_directory / "received_safe-name").exists()
                    )

        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "symlink.zip"
            output_directory = Path(directory) / "received"
            output_directory.mkdir()
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = stat.S_IFLNK << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(info, "outside.txt")

            with self.assertRaises(ValueError):
                utils.extract_directory_archive(
                    str(archive_path),
                    str(output_directory),
                    "safe-name",
                )

    def test_zip_file_transfer_is_not_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "bundle.zip"
            with zipfile.ZipFile(source_path, "w") as archive:
                archive.writestr("inside.txt", b"zip contents")

            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)
            client.send_file(
                str(source_path),
                "127.0.0.1",
                port,
                uuid.uuid4(),
                CHUNK_SIZE,
                show_progress=False,
            )

            server_thread.join(timeout=2)
            received_path = Path(result[0])
            self.assertTrue(received_path.is_file())
            self.assertTrue(zipfile.is_zipfile(received_path))
            self.assertFalse((received_path.parent / "inside.txt").exists())

    def start_server(
        self,
        output_directory: Path,
        port: int | None = None,
        timeout: float = 30.0,
    ):
        ready = threading.Event()
        result = []
        port = port if port is not None else unused_local_port()
        server_thread = threading.Thread(
            target=lambda: result.append(
                server.receive_file(
                    str(output_directory),
                    "127.0.0.1",
                    port,
                    ready,
                    timeout,
                )
            )
        )
        server_thread.start()
        self.assertTrue(ready.wait(timeout=2))
        return server_thread, result, port

    def test_interrupted_transfer_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "resume.bin"
            output_directory = Path(directory) / "received"
            contents = bytes(range(256)) * 64
            source_path.write_bytes(contents)
            transfer_id = uuid.uuid4()

            server_thread, result, port = self.start_server(output_directory)
            with socket.create_connection(("127.0.0.1", port)) as connection:
                metadata = protocol.pack_file_metadata(
                    source_path.name,
                    len(contents),
                    transfer_id,
                    CHUNK_SIZE,
                )
                protocol.send_message(connection, metadata)

                status, offset = protocol.unpack_transfer_status(
                    protocol.receive_message(connection)
                )
                self.assertEqual(status, protocol.START_TRANSFER)
                self.assertEqual(offset, 0)

                connection.sendall(contents[:CHUNK_SIZE])

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(
                (output_directory / f"{transfer_id}.part").read_bytes(),
                contents[:CHUNK_SIZE],
            )

            resumed_server, resumed_result, _ = self.start_server(
                output_directory,
                port,
            )
            digest = client.send_file(
                str(source_path),
                "127.0.0.1",
                port,
                transfer_id,
                CHUNK_SIZE,
                show_progress=False,
            )

            resumed_server.join(timeout=2)
            self.assertFalse(resumed_server.is_alive())
            self.assertIsNotNone(resumed_result[0])
            received_path = Path(resumed_result[0])
            self.assertEqual(received_path.read_bytes(), contents)
            self.assertEqual(digest, hashlib.sha256(contents).digest())
            self.assertFalse((output_directory / f"{transfer_id}.part").exists())
            self.assertFalse((output_directory / f"{transfer_id}.meta").exists())

    def test_corrupted_retained_chunk_is_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "repair.bin"
            output_directory = Path(directory) / "received"
            contents = bytes(range(256)) * 48
            source_path.write_bytes(contents)
            transfer_id = uuid.uuid4()

            output_directory.mkdir()
            metadata = protocol.pack_file_metadata(
                source_path.name,
                len(contents),
                transfer_id,
                CHUNK_SIZE,
            )
            corrupted = bytearray(contents[: CHUNK_SIZE * 3])
            corrupted[CHUNK_SIZE] ^= 0xFF
            (output_directory / f"{transfer_id}.part").write_bytes(corrupted)
            (output_directory / f"{transfer_id}.meta").write_bytes(metadata)

            server_thread, result, port = self.start_server(output_directory)
            digest = client.send_file(
                str(source_path),
                "127.0.0.1",
                port,
                transfer_id,
                CHUNK_SIZE,
                show_progress=False,
            )

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertIsNotNone(result[0])
            self.assertEqual(Path(result[0]).read_bytes(), contents)
            self.assertEqual(digest, hashlib.sha256(contents).digest())
            self.assertFalse((output_directory / f"{transfer_id}.part").exists())
            self.assertFalse((output_directory / f"{transfer_id}.meta").exists())

    def test_mismatched_resume_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            output_directory.mkdir()
            transfer_id = uuid.uuid4()

            original_metadata = protocol.pack_file_metadata(
                "resume.bin",
                100,
                transfer_id,
                CHUNK_SIZE,
            )
            part_path = output_directory / f"{transfer_id}.part"
            meta_path = output_directory / f"{transfer_id}.meta"
            part_path.write_bytes(b"partial")
            meta_path.write_bytes(original_metadata)

            server_thread, result, port = self.start_server(output_directory)
            mismatched_metadata = protocol.pack_file_metadata(
                "resume.bin",
                200,
                transfer_id,
                CHUNK_SIZE,
            )
            with socket.create_connection(("127.0.0.1", port)) as connection:
                protocol.send_message(connection, mismatched_metadata)
                self.assertEqual(
                    protocol.unpack_transfer_result(
                        protocol.receive_message(connection)
                    ),
                    protocol.TRANSFER_FAILED,
                )

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(part_path.read_bytes(), b"partial")
            self.assertEqual(meta_path.read_bytes(), original_metadata)

    def test_rejected_transfer_cleans_resume_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            output_directory.mkdir()
            transfer_id = uuid.uuid4()
            metadata = protocol.pack_file_metadata(
                "rejected.bin",
                100,
                transfer_id,
                CHUNK_SIZE,
            )
            part_path = output_directory / f"{transfer_id}.part"
            meta_path = output_directory / f"{transfer_id}.meta"
            part_path.write_bytes(b"partial")
            meta_path.write_bytes(metadata)

            server_socket, client_socket = socket.socketpair()
            server_thread = threading.Thread(
                target=server._handle_connection,
                args=(
                    server_socket,
                    ("127.0.0.1", 12345),
                    str(output_directory),
                    30.0,
                    lambda *_: False,
                ),
            )
            server_thread.start()
            try:
                protocol.send_message(client_socket, metadata)
                self.assertEqual(
                    protocol.unpack_transfer_result(
                        protocol.receive_message(client_socket)
                    ),
                    protocol.TRANSFER_FAILED,
                )
            finally:
                client_socket.close()

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertFalse(part_path.exists())
            self.assertFalse(meta_path.exists())

    def test_two_transfers_can_run_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            output_directory.mkdir()
            transfers = [
                (uuid.uuid4(), "first.bin", b"a" * (CHUNK_SIZE * 2)),
                (uuid.uuid4(), "second.bin", b"b" * (CHUNK_SIZE * 2)),
            ]
            socket_pairs = [socket.socketpair() for _ in transfers]
            server_threads = []
            client_results = []

            for (transfer_id, filename, _), (server_socket, _) in zip(
                transfers,
                socket_pairs,
            ):
                thread = threading.Thread(
                    target=server._handle_connection,
                    args=(
                        server_socket,
                        ("127.0.0.1", 12345),
                        str(output_directory),
                        30.0,
                    ),
                )
                server_threads.append(thread)
                thread.start()

            def send_transfer(
                client_socket: socket.socket,
                transfer_id: uuid.UUID,
                filename: str,
                contents: bytes,
            ) -> None:
                with client_socket:
                    metadata = protocol.pack_file_metadata(
                        filename,
                        len(contents),
                        transfer_id,
                        CHUNK_SIZE,
                    )
                    protocol.send_message(client_socket, metadata)
                    status, offset = protocol.unpack_transfer_status(
                        protocol.receive_message(client_socket)
                    )
                    self.assertEqual(status, protocol.START_TRANSFER)
                    self.assertEqual(offset, 0)
                    client_socket.sendall(contents)
                    protocol.send_message(
                        client_socket,
                        hashlib.sha256(contents).digest(),
                    )
                    client_results.append(
                        protocol.unpack_transfer_result(
                            protocol.receive_message(client_socket)
                        )
                    )

            client_threads = [
                threading.Thread(target=send_transfer, args=(pair[1], *transfer))
                for pair, transfer in zip(socket_pairs, transfers)
            ]
            for thread in client_threads:
                thread.start()
            for thread in client_threads:
                thread.join(timeout=2)
            for thread in server_threads:
                thread.join(timeout=2)

            self.assertEqual(
                client_results,
                [protocol.TRANSFER_COMPLETE, protocol.TRANSFER_COMPLETE],
            )
            self.assertEqual(
                (output_directory / "received_first.bin").read_bytes(),
                transfers[0][2],
            )
            self.assertEqual(
                (output_directory / "received_second.bin").read_bytes(),
                transfers[1][2],
            )

    def test_transfer_timeout_retains_partial_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            transfer_id = uuid.uuid4()
            server_thread, result, port = self.start_server(
                output_directory,
                timeout=0.05,
            )

            connection = socket.create_connection(("127.0.0.1", port))
            try:
                metadata = protocol.pack_file_metadata(
                    "timeout.bin",
                    100,
                    transfer_id,
                    CHUNK_SIZE,
                )
                protocol.send_message(connection, metadata)
                status, offset = protocol.unpack_transfer_status(
                    protocol.receive_message(connection)
                )
                self.assertEqual(status, protocol.START_TRANSFER)
                self.assertEqual(offset, 0)

                server_thread.join(timeout=2)
                self.assertFalse(server_thread.is_alive())
                self.assertEqual(result, [None])
                self.assertEqual(
                    (output_directory / f"{transfer_id}.part").read_bytes(),
                    b"",
                )
                self.assertTrue((output_directory / f"{transfer_id}.meta").exists())
            finally:
                connection.close()

    def test_expired_resume_state_is_cleaned_up(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            expired_meta = output_directory / "expired.meta"
            expired_part = output_directory / "expired.part"
            fresh_meta = output_directory / "fresh.meta"
            fresh_part = output_directory / "fresh.part"

            expired_meta.write_bytes(b"metadata")
            expired_part.write_bytes(b"partial")
            fresh_meta.write_bytes(b"metadata")
            fresh_part.write_bytes(b"partial")

            expired_time = time.time() - server.RESUME_RETENTION_SECONDS - 1
            os.utime(expired_meta, (expired_time, expired_time))

            utils.cleanup_expired_transfers(
                str(output_directory),
                server.RESUME_RETENTION_SECONDS,
            )

            self.assertFalse(expired_meta.exists())
            self.assertFalse(expired_part.exists())
            self.assertTrue(fresh_meta.exists())
            self.assertTrue(fresh_part.exists())

    def test_interrupted_transfer_retains_partial_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)

            transfer_id = uuid.uuid4()
            metadata = protocol.pack_file_metadata(
                "partial.bin",
                10,
                transfer_id,
                CHUNK_SIZE,
            )
            with socket.create_connection(("127.0.0.1", port)) as connection:
                protocol.send_message(connection, metadata)
                connection.sendall(b"short")

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(
                (output_directory / f"{transfer_id}.part").read_bytes(),
                b"short",
            )
            self.assertEqual(
                (output_directory / f"{transfer_id}.meta").read_bytes(),
                metadata,
            )

    def test_checksum_mismatch_removes_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)

            transfer_id = uuid.uuid4()
            with socket.create_connection(("127.0.0.1", port)) as connection:
                contents = b"valid file bytes"
                metadata = protocol.pack_file_metadata(
                    "invalid.bin",
                    len(contents),
                    transfer_id,
                    CHUNK_SIZE,
                )
                protocol.send_message(connection, metadata)
                connection.sendall(contents)
                protocol.send_message(connection, b"wrong digest")

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(list(output_directory.iterdir()), [])

    def test_existing_output_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            output_directory.mkdir()
            existing_path = output_directory / "received_existing.bin"
            existing_contents = b"keep this file"
            existing_path.write_bytes(existing_contents)

            server_thread, result, port = self.start_server(output_directory)
            transfer_id = uuid.uuid4()
            with socket.create_connection(("127.0.0.1", port)) as connection:
                contents = b"replacement bytes"
                metadata = protocol.pack_file_metadata(
                    "existing.bin",
                    len(contents),
                    transfer_id,
                    CHUNK_SIZE,
                )
                protocol.send_message(connection, metadata)
                self.assertEqual(
                    protocol.unpack_transfer_result(
                        protocol.receive_message(connection)
                    ),
                    protocol.TRANSFER_FAILED,
                )

            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(result, [None])
            self.assertEqual(existing_path.read_bytes(), existing_contents)

    def test_unsafe_filename_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "received"
            server_thread, result, port = self.start_server(output_directory)

            transfer_id = uuid.uuid4()
            with socket.create_connection(("127.0.0.1", port)) as connection:
                filename = "../outside.bin"
                metadata = protocol.pack_file_metadata(
                    filename,
                    0,
                    transfer_id,
                    CHUNK_SIZE,
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
