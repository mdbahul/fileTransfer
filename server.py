import hashlib
import os
import socket
from threading import Event

import checksum
import protocol
import utils

CHUNK_SIZE = 4096


def receive_file(
    output_directory: str,
    host: str,
    port: int,
    ready_event: Event | None = None,
) -> str | None:
    try:
        os.makedirs(output_directory, exist_ok=True)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((host, port))
            server_socket.listen()

            if ready_event is not None:
                ready_event.set()

            print(f"Waiting for a client on {host}:{port}...")
            connection, client_address = server_socket.accept()

            hasher = hashlib.sha256()
            output_path = None
            success = False

            with connection:
                print(f"Connected to {client_address}")

                try:
                    metadata = protocol.receive_message(connection)
                    filename, file_size = protocol.unpack_file_metadata(metadata)
                    filename = utils.validate_filename(filename)
                    new_file_name = f"received_{filename}"
                    output_path = os.path.join(output_directory, new_file_name)

                    remaining = file_size
                    with open(output_path, "wb") as f:
                        while remaining > 0:
                            chunk = connection.recv(min(remaining, CHUNK_SIZE))

                            if chunk == b"":
                                raise ConnectionError(
                                    "Connection closed during transfer"
                                )

                            hasher.update(chunk)
                            f.write(chunk)
                            remaining -= len(chunk)

                        expected_digest = protocol.receive_message(connection)

                    actual_digest = hasher.digest()
                    if not checksum.digest_match(expected_digest, actual_digest):
                        raise ValueError("SHA-256 checksum mismatch")

                    success = True
                    print(f"Received: {new_file_name} ({file_size} bytes)")

                except ValueError as error:
                    print(f"Transfer failed: {error}")

                except ConnectionError as error:
                    print(f"Connection error: {error}")

                except OSError as error:
                    print(f"Filesystem error: {error}")

                finally:
                    if (
                        not success
                        and output_path is not None
                        and os.path.exists(output_path)
                    ):
                        try:
                            os.remove(output_path)
                        except OSError as error:
                            print(f"Cleanup failed: {error}")
                            print(f"Partial file remains at: {output_path}")

            return output_path if success else None

    except OSError as error:
        print(f"Server startup error: {error}")
        return None


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8080
    OUTPUT_DIRECTORY = "tests"

    receive_file(OUTPUT_DIRECTORY, HOST, PORT)
