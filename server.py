import hashlib
import os
import socket
from threading import Event

import checksum
import protocol
import utils

RESUME_RETENTION_SECONDS = 8 * 60 * 60


def receive_file(
    output_directory: str,
    host: str,
    port: int,
    ready_event: Event | None = None,
    timeout: float = 30.0,
) -> str | None:
    try:
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        os.makedirs(output_directory, exist_ok=True)
        utils.cleanup_expired_transfers(
            output_directory,
            RESUME_RETENTION_SECONDS,
        )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((host, port))
            server_socket.listen()

            if ready_event is not None:
                ready_event.set()

            print(f"Waiting for a client on {host}:{port}...")
            connection, client_address = server_socket.accept()
            connection.settimeout(timeout)

            hasher = hashlib.sha256()
            output_path = None
            success = False

            with connection:
                print(f"Connected to {client_address}")

                try:
                    metadata = protocol.receive_message(connection)
                    transfer_id, filename, file_size, chunk_size = (
                        protocol.unpack_file_metadata(metadata)
                    )
                    filename = utils.validate_filename(filename)

                    part_path = os.path.join(
                        output_directory,
                        f"{transfer_id}.part",
                    )
                    meta_path = os.path.join(
                        output_directory,
                        f"{transfer_id}.meta",
                    )
                    output_path = os.path.join(
                        output_directory,
                        f"received_{filename}",
                    )

                    if os.path.exists(meta_path):
                        with open(meta_path, "rb") as f:
                            existing_meta = f.read()

                        if existing_meta != metadata:
                            raise ValueError(
                                "Metadata does not match existing transfer"
                            )
                    else:
                        with open(meta_path, "wb") as f:
                            f.write(metadata)

                    current_size = (
                        os.path.getsize(part_path)
                        if os.path.exists(part_path)
                        else 0
                    )

                    if current_size > file_size:
                        raise ValueError(
                            "Partial file is larger than expected file size"
                        )

                    current_size -= current_size % chunk_size
                    with open(part_path, "ab") as f:
                        f.truncate(current_size)

                    if current_size:
                        chunk_count = current_size // chunk_size
                        protocol.send_message(
                            connection,
                            protocol.pack_hash_request(chunk_count),
                        )
                        hash_response = protocol.receive_message(connection)
                        received_hashes = protocol.unpack_hash_response(hash_response)

                        if len(received_hashes) != chunk_count:
                            raise ValueError("Invalid number of chunk hashes")

                        safe_offset = 0
                        with open(part_path, "rb") as f:
                            for received_hash in received_hashes:
                                chunk = f.read(chunk_size)
                                actual_hash = hashlib.sha256(chunk).digest()
                                if not checksum.digest_match(
                                    received_hash,
                                    actual_hash,
                                ):
                                    break
                                safe_offset += len(chunk)

                        with open(part_path, "ab") as f:
                            f.truncate(safe_offset)
                        current_size = safe_offset
                        status = protocol.RESUME_TRANSFER
                    else:
                        status = protocol.START_TRANSFER

                    protocol.send_message(
                        connection,
                        protocol.pack_transfer_status(status, current_size),
                    )

                    with open(part_path, "rb") as f:
                        while True:
                            chunk = f.read(chunk_size)
                            if chunk == b"":
                                break
                            hasher.update(chunk)

                    remaining = file_size - current_size
                    with open(part_path, "ab") as f:
                        while remaining > 0:
                            chunk = connection.recv(min(remaining, chunk_size))

                            if chunk == b"":
                                raise ConnectionError(
                                    "Connection closed during transfer"
                                )

                            hasher.update(chunk)
                            f.write(chunk)
                            remaining -= len(chunk)
                        f.flush()
                        os.fsync(f.fileno())

                        expected_digest = protocol.receive_message(connection)

                    actual_digest = hasher.digest()
                    if not checksum.digest_match(expected_digest, actual_digest):
                        raise ValueError("SHA-256 checksum mismatch")

                    os.replace(part_path, output_path)
                    utils.sync_directory(output_directory)
                    if not os.path.isfile(output_path):
                        raise OSError("Published file is missing")
                    if os.path.getsize(output_path) != file_size:
                        raise OSError("Published file size does not match metadata")

                    os.remove(meta_path)
                    success = True
                    protocol.send_message(
                        connection,
                        protocol.pack_transfer_result(protocol.TRANSFER_COMPLETE),
                    )
                    print(
                        f"Received: {os.path.basename(output_path)} "
                        f"({file_size} bytes)"
                    )

                except ValueError as error:
                    try:
                        protocol.send_message(
                            connection,
                            protocol.pack_transfer_result(protocol.TRANSFER_FAILED),
                        )
                    except OSError as notify_error:
                        print(f"Failed to notify client: {notify_error}")
                    print(f"Transfer failed: {error}")

                except ConnectionError as error:
                    print(f"Connection error: {error}")

                except socket.timeout as error:
                    print(f"Transfer timed out: {error}")

                except OSError as error:
                    print(f"Filesystem error: {error}")

                finally:
                    if not success and "expected_digest" in locals():
                        try:
                            if os.path.exists(part_path):
                                os.remove(part_path)
                            if os.path.exists(meta_path):
                                os.remove(meta_path)
                        except OSError as error:
                            print(f"Cleanup failed: {error}")
                            print(f"Partial file remains at: {part_path}")

            return output_path if success else None

    except OSError as error:
        print(f"Server startup error: {error}")
        return None


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8080
    OUTPUT_DIRECTORY = "tests"

    receive_file(OUTPUT_DIRECTORY, HOST, PORT)
