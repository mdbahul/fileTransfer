import hashlib
import os
import socket
import time

import progress
import protocol

CHUNK_SIZE = 4096


def send_file(
    file_path: str,
    host: str,
    port: int,
    show_progress: bool = True,
) -> bytes:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.connect((host, port))

        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        metadata = protocol.pack_file_metadata(filename, file_size)
        protocol.send_message(client_socket, metadata)

        start = time.monotonic()
        bytes_transferred = 0
        first_render = True
        hasher = hashlib.sha256()

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
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

    send_file(FILE_PATH, HOST, PORT)
