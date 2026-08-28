import argparse
import hashlib
import os
import socket
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

import discovery
import progress
import protocol

DEFAULT_CHUNK_SIZE = 64 * 1024


def _archive_directory(directory_path: str, archive_path: str) -> None:
    directory = Path(directory_path)

    def raise_on_error(error: OSError) -> None:
        raise error

    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for root, directories, filenames in os.walk(
            directory,
            topdown=True,
            onerror=raise_on_error,
            followlinks=False,
        ):
            directories.sort()
            filenames.sort()
            root_path = Path(root)
            relative_root = root_path.relative_to(directory)

            for name in directories:
                path = root_path / name
                if path.is_symlink():
                    raise ValueError(
                        "Directories containing symlinks are not supported"
                    )
                relative_name = (relative_root / name).as_posix() + "/"
                info = zipfile.ZipInfo(relative_name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (0o40755 << 16) | 0x10
                archive.writestr(info, b"")

            for name in filenames:
                path = root_path / name
                if path.is_symlink():
                    raise ValueError(
                        "Directories containing symlinks are not supported"
                    )
                relative_name = (relative_root / name).as_posix()
                info = zipfile.ZipInfo(relative_name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with path.open("rb") as source, archive.open(info, "w") as target:
                    while chunk := source.read(DEFAULT_CHUNK_SIZE):
                        target.write(chunk)


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

    if os.path.isdir(file_path):
        directory_name = os.path.basename(os.path.normpath(file_path))
        with tempfile.TemporaryDirectory(
            prefix="file-transfer-archive-"
        ) as temporary_directory:
            archive_path = os.path.join(temporary_directory, "directory.zip")
            _archive_directory(file_path, archive_path)
            return _send_prepared_file(
                archive_path,
                host,
                port,
                transfer_id,
                chunk_size,
                show_progress,
                timeout,
                protocol.TRANSFER_KIND_DIRECTORY,
                directory_name,
            )

    return _send_prepared_file(
        file_path,
        host,
        port,
        transfer_id,
        chunk_size,
        show_progress,
        timeout,
        protocol.TRANSFER_KIND_FILE,
        os.path.basename(file_path),
    )


def _send_prepared_file(
    file_path: str,
    host: str,
    port: int,
    transfer_id: uuid.UUID,
    chunk_size: int,
    show_progress: bool,
    timeout: float,
    transfer_kind: int,
    display_name: str,
) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.settimeout(timeout)
        client_socket.connect((host, port))

        file_size = os.path.getsize(file_path)

        metadata = protocol.pack_file_metadata(
            display_name,
            file_size,
            transfer_id,
            chunk_size,
            transfer_kind,
        )
        protocol.send_message(client_socket, metadata)
        response = protocol.receive_message(client_socket)
        if not response:
            raise ValueError("Empty server response")

        if response[0] == protocol.TRANSFER_FAILED:
            protocol.unpack_transfer_result(response)
            raise ValueError("Server rejected transfer")
        if response[0] == protocol.TRANSFER_ACCEPTED:
            protocol.unpack_transfer_acceptance(response)
            response = protocol.receive_message(client_socket)
            if not response:
                raise ValueError("Empty server response")

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
        session_transferred = 0
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
                session_transferred += len(chunk)

                if show_progress:
                    progress.render_progress(
                        display_name,
                        bytes_transferred,
                        file_size,
                        time.monotonic() - start,
                        first_render,
                        session_transferred,
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
                display_name,
                bytes_transferred,
                file_size,
                time.monotonic() - start,
                first_render,
                session_transferred,
            )
            print(f"Sent: {display_name} {progress.format_bytes(file_size)}")

        return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Send a file or directory to a LAN device"
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="path of the file or directory to send",
    )
    parser.add_argument(
        "--discovery-port",
        type=int,
        default=discovery.DISCOVERY_PORT,
        help="UDP discovery port",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=150.0,
        help="network operation timeout in seconds",
    )
    args = parser.parse_args()

    FILE_PATH = args.file or input(
        "Enter the path of the file or directory to send: "
    ).strip()
    if not FILE_PATH:
        raise SystemExit("A file or directory path is required")

    CHUNK_SIZE = DEFAULT_CHUNK_SIZE

    devices = discovery.broadcast_discovery(args.discovery_port)
    if not devices:
        raise SystemExit("No file-transfer devices found")

    print("Discovered devices:")
    for index, device in enumerate(devices, start=1):
        print(f"{index}. {device.device_name} ({device.ip_address}:{device.tcp_port})")

    try:
        selection = int(input("Choose a device number: "))
        device = devices[selection - 1]
    except (ValueError, IndexError):
        raise SystemExit("Invalid device selection")

    file_stat = os.stat(FILE_PATH)
    transfer_key = (
        f"{os.path.abspath(FILE_PATH)}:"
        f"{file_stat.st_size}:{file_stat.st_mtime_ns}"
    )
    transfer_id = uuid.uuid5(uuid.NAMESPACE_URL, transfer_key)

    send_file(
        FILE_PATH,
        device.ip_address,
        device.tcp_port,
        transfer_id,
        CHUNK_SIZE,
        timeout=args.timeout,
    )
