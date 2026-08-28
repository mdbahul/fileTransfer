import hashlib
import os
import select
import socket
import sys
import time
from threading import Event, Lock, Thread
from typing import Callable

import checksum
import discovery
import protocol
import utils

RESUME_RETENTION_SECONDS = 8 * 60 * 60
APPROVAL_TIMEOUT_SECONDS = 120
CONSENT_LOCK = Lock()


def _read_input_with_timeout(prompt: str, timeout: float) -> str | None:
    print(prompt, end="", flush=True)
    deadline = time.monotonic() + timeout

    if os.name == "nt":
        import msvcrt

        characters = []
        while time.monotonic() < deadline:
            if not msvcrt.kbhit():
                time.sleep(0.05)
                continue
            character = msvcrt.getwch()
            if character in ("\r", "\n"):
                print()
                return "".join(characters)
            if character == "\b":
                if characters:
                    characters.pop()
                    print("\b \b", end="", flush=True)
                continue
            characters.append(character)
            print(character, end="", flush=True)
        print()
        return None

    remaining = max(0.0, deadline - time.monotonic())
    readable, _, _ = select.select([sys.stdin], [], [], remaining)
    if not readable:
        print()
        return None
    return sys.stdin.readline().rstrip("\n")


def prompt_for_transfer(
    filename: str,
    file_size: int,
    client_address: tuple[str, int],
) -> bool:
    with CONSENT_LOCK:
        answer = _read_input_with_timeout(
            f"Accept {filename} ({file_size} bytes) from "
            f"{client_address[0]}? [y/N] (expires in 120 seconds): ",
            APPROVAL_TIMEOUT_SECONDS,
        )
    if answer is None:
        print("Transfer approval timed out; rejecting transfer")
        return False
    return answer.strip().lower() in {"y", "yes"}


def _handle_connection(
    connection: socket.socket,
    client_address: tuple[str, int],
    output_directory: str,
    timeout: float,
    approval_callback: Callable[[str, int, tuple[str, int]], bool] | None = None,
) -> str | None:
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
            part_path = os.path.join(output_directory, f"{transfer_id}.part")
            meta_path = os.path.join(output_directory, f"{transfer_id}.meta")

            if approval_callback is not None and not approval_callback(
                filename,
                file_size,
                client_address,
            ):
                if os.path.exists(part_path):
                    os.remove(part_path)
                if os.path.exists(meta_path):
                    os.remove(meta_path)
                protocol.send_message(
                    connection,
                    protocol.pack_transfer_result(protocol.TRANSFER_FAILED),
                )
                print(f"Transfer rejected from {client_address}")
                return None

            if approval_callback is not None:
                protocol.send_message(
                    connection,
                    protocol.pack_transfer_acceptance(),
                )

            output_path = os.path.join(output_directory, f"received_{filename}")

            if os.path.exists(meta_path):
                with open(meta_path, "rb") as file:
                    existing_meta = file.read()
                if existing_meta != metadata:
                    raise ValueError("Metadata does not match existing transfer")
            else:
                with open(meta_path, "wb") as file:
                    file.write(metadata)

            current_size = (
                os.path.getsize(part_path) if os.path.exists(part_path) else 0
            )
            if current_size > file_size:
                raise ValueError("Partial file is larger than expected file size")

            current_size -= current_size % chunk_size
            with open(part_path, "ab") as file:
                file.truncate(current_size)

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
                with open(part_path, "rb") as file:
                    for received_hash in received_hashes:
                        chunk = file.read(chunk_size)
                        actual_hash = hashlib.sha256(chunk).digest()
                        if not checksum.digest_match(received_hash, actual_hash):
                            break
                        safe_offset += len(chunk)

                with open(part_path, "ab") as file:
                    file.truncate(safe_offset)
                current_size = safe_offset
                status = protocol.RESUME_TRANSFER
            else:
                status = protocol.START_TRANSFER

            protocol.send_message(
                connection,
                protocol.pack_transfer_status(status, current_size),
            )

            with open(part_path, "rb") as file:
                while chunk := file.read(chunk_size):
                    hasher.update(chunk)

            remaining = file_size - current_size
            with open(part_path, "ab") as file:
                while remaining > 0:
                    chunk = connection.recv(min(remaining, chunk_size))
                    if chunk == b"":
                        raise ConnectionError("Connection closed during transfer")
                    hasher.update(chunk)
                    file.write(chunk)
                    remaining -= len(chunk)
                file.flush()
                os.fsync(file.fileno())
                expected_digest = protocol.receive_message(connection)

            if not checksum.digest_match(expected_digest, hasher.digest()):
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
            return _handle_connection(
                connection,
                client_address,
                output_directory,
                timeout,
            )
    except OSError as error:
        print(f"Server startup error: {error}")
        return None


def serve(
    output_directory: str,
    host: str,
    port: int,
    timeout: float = 30.0,
) -> None:
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
        print(f"Waiting for clients on {host}:{port}...")

        while True:
            connection, client_address = server_socket.accept()
            Thread(
                target=_handle_connection,
                args=(
                    connection,
                    client_address,
                    output_directory,
                    timeout,
                    prompt_for_transfer,
                ),
                daemon=True,
            ).start()


if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = 8080
    OUTPUT_DIRECTORY = "tests"

    discovery_thread = Thread(
        target=discovery.listen_for_discovery,
        kwargs={
            "device_name": socket.gethostname(),
            "tcp_port": PORT,
        },
        daemon=True,
    )
    discovery_thread.start()
    serve(OUTPUT_DIRECTORY, HOST, PORT)
