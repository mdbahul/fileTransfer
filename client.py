import hashlib
import os
import socket
import time
import uuid

import progress
import protocol


def send_file(
    file_path: str,
    host: str,
    port: int,
    transfer_id: uuid.UUID,
    chunk_size: int,
    show_progress: bool = True,
    timeout: float = 30.0,
) -> bytes:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if timeout <= 0:
        raise ValueError("Timeout must be positive")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.settimeout(timeout)
        client_socket.connect((host, port))

        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        metadata = protocol.pack_file_metadata(
            filename,
            file_size,
            transfer_id,
            chunk_size,
        )
        protocol.send_message(client_socket, metadata)
        response = protocol.receive_message(client_socket)
        if not response:
            raise ValueError("Empty server response")

        if response[0] == protocol.TRANSFER_FAILED:
            protocol.unpack_transfer_result(response)
            raise ValueError("Server rejected transfer")

        if response[0] == protocol.HASH_REQUEST:
            hash_count = protocol.unpack_hash_request(response)
            hashes = []
            with open(file_path, "rb") as f:
                for _ in range(hash_count):
                    chunk = f.read(chunk_size)
                    if len(chunk) != chunk_size:
                        raise ValueError("Source file changed during resume")
                    hashes.append(hashlib.sha256(chunk).digest())

            protocol.send_message(
                client_socket,
                protocol.pack_hash_response(hashes),
            )
            response = protocol.receive_message(client_socket)
            if not response:
                raise ValueError("Empty server response")
            if response[0] == protocol.TRANSFER_FAILED:
                protocol.unpack_transfer_result(response)
                raise ValueError("Server rejected resume")

        status, offset = protocol.unpack_transfer_status(response)
        if status == protocol.START_TRANSFER and offset != 0:
            raise ValueError("Invalid start offset")
        if offset > file_size:
            raise ValueError("Resume offset exceeds source file")

        start = time.monotonic()
        bytes_transferred = offset
        first_render = True
        hasher = hashlib.sha256()

        with open(file_path, "rb") as f:
            if offset:
                prefix_remaining = offset
                while prefix_remaining > 0:
                    chunk = f.read(min(prefix_remaining, chunk_size))
                    if chunk == b"":
                        raise ValueError("Resume offset exceeds source file")
                    hasher.update(chunk)
                    prefix_remaining -= len(chunk)
                f.seek(offset)

            while True:
                chunk = f.read(chunk_size)
                if chunk == b"":
                    break

                hasher.update(chunk)
                client_socket.sendall(chunk)
                bytes_transferred += len(chunk)

                if show_progress:
                    progress.render_progress(
                        filename,
                        bytes_transferred,
                        file_size,
                        time.monotonic() - start,
                        first_render,
                    )
                first_render = False

        digest = hasher.digest()
        protocol.send_message(client_socket, digest)
        result = protocol.unpack_transfer_result(
            protocol.receive_message(client_socket)
        )
        if result != protocol.TRANSFER_COMPLETE:
            raise ConnectionError("Server rejected transfer")

        if show_progress:
            progress.render_progress(
                filename,
                bytes_transferred,
                file_size,
                time.monotonic() - start,
                first_render,
            )
            print(f"Sent: {filename} {progress.format_bytes(file_size)}")

        return digest


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8080
    FILE_PATH = "/Users/new/Desktop/fileTransfer/tests/test.txt"
    CHUNK_SIZE = 4096

    transfer_id = uuid.uuid4()

    send_file(FILE_PATH, HOST, PORT, transfer_id, CHUNK_SIZE)
