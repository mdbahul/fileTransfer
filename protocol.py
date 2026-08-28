import struct
import uuid


HEADER_FORMAT = "!I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
TRANSFER_STATUS_FORMAT = "!BQ"
TRANSFER_STATUS_SIZE = struct.calcsize(TRANSFER_STATUS_FORMAT)
HASH_REQUEST_FORMAT = "!BQ"
HASH_REQUEST_SIZE = struct.calcsize(HASH_REQUEST_FORMAT)
HASH_RESPONSE_HEADER_FORMAT = "!BQ"
HASH_RESPONSE_HEADER_SIZE = struct.calcsize(HASH_RESPONSE_HEADER_FORMAT)
HASH_SIZE = 32
START_TRANSFER = 1
RESUME_TRANSFER = 2
HASH_REQUEST = 3
HASH_RESPONSE = 4
TRANSFER_COMPLETE = 5
TRANSFER_FAILED = 6
TRANSFER_ACCEPTED = 7
TRANSFER_KIND_FILE = 1
TRANSFER_KIND_DIRECTORY = 2


def recv_exactly(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if chunk == b"":
            raise ConnectionError("Connection closed before receiving enough data")

        data += chunk

    return data


def receive_message(sock):
    header = recv_exactly(sock, HEADER_SIZE)
    length = struct.unpack(HEADER_FORMAT, header)[0]

    return recv_exactly(sock, length)


def send_message(sock, payload):
    header = struct.pack(HEADER_FORMAT, len(payload))
    sock.sendall(header)
    sock.sendall(payload)


def pack_transfer_status(status: int, offset: int) -> bytes:
    if status not in (START_TRANSFER, RESUME_TRANSFER):
        raise ValueError("Invalid transfer status")
    if offset < 0:
        raise ValueError("Transfer offset cannot be negative")
    return struct.pack(TRANSFER_STATUS_FORMAT, status, offset)


def unpack_transfer_status(data: bytes) -> tuple[int, int]:
    if len(data) != TRANSFER_STATUS_SIZE:
        raise ValueError("Invalid transfer status length")
    status, offset = struct.unpack(TRANSFER_STATUS_FORMAT, data)
    if status not in (START_TRANSFER, RESUME_TRANSFER):
        raise ValueError("Invalid transfer status")
    return status, offset


def pack_hash_request(count: int) -> bytes:
    if count < 0:
        raise ValueError("Hash count cannot be negative")
    return struct.pack(HASH_REQUEST_FORMAT, HASH_REQUEST, count)


def unpack_hash_request(data: bytes) -> int:
    if len(data) != HASH_REQUEST_SIZE:
        raise ValueError("Invalid hash request length")
    message_type, count = struct.unpack(HASH_REQUEST_FORMAT, data)
    if message_type != HASH_REQUEST:
        raise ValueError("Invalid hash request type")
    return count


def pack_hash_response(hashes: list[bytes]) -> bytes:
    if any(len(digest) != HASH_SIZE for digest in hashes):
        raise ValueError("Each hash must be a 32-byte SHA-256 digest")
    return (
        struct.pack(HASH_RESPONSE_HEADER_FORMAT, HASH_RESPONSE, len(hashes))
        + b"".join(hashes)
    )


def unpack_hash_response(data: bytes) -> list[bytes]:
    if len(data) < HASH_RESPONSE_HEADER_SIZE:
        raise ValueError("Hash response is too short")

    message_type, count = struct.unpack(
        HASH_RESPONSE_HEADER_FORMAT,
        data[:HASH_RESPONSE_HEADER_SIZE],
    )
    if message_type != HASH_RESPONSE:
        raise ValueError("Invalid hash response type")

    expected_size = HASH_RESPONSE_HEADER_SIZE + count * HASH_SIZE
    if len(data) != expected_size:
        raise ValueError("Invalid hash response length")

    hashes_start = HASH_RESPONSE_HEADER_SIZE
    return [
        data[index : index + HASH_SIZE]
        for index in range(hashes_start, expected_size, HASH_SIZE)
    ]


def pack_transfer_result(status: int) -> bytes:
    if status not in (TRANSFER_COMPLETE, TRANSFER_FAILED):
        raise ValueError("Invalid transfer result")
    return struct.pack("!B", status)


def unpack_transfer_result(data: bytes) -> int:
    if len(data) != 1:
        raise ValueError("Invalid transfer result length")
    status = struct.unpack("!B", data)[0]
    if status not in (TRANSFER_COMPLETE, TRANSFER_FAILED):
        raise ValueError("Invalid transfer result")
    return status


def pack_transfer_acceptance() -> bytes:
    return struct.pack("!B", TRANSFER_ACCEPTED)


def unpack_transfer_acceptance(data: bytes) -> None:
    if len(data) != 1 or struct.unpack("!B", data)[0] != TRANSFER_ACCEPTED:
        raise ValueError("Invalid transfer acceptance")


def pack_file_metadata(
    filename: str,
    file_size: int,
    transfer_id: uuid.UUID,
    chunk_size: int,
    transfer_kind: int = TRANSFER_KIND_FILE,
) -> bytes:
    filename_bytes = filename.encode("utf-8")
    if len(filename_bytes) > 255:
        raise ValueError("Filename too long")
    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")
    if transfer_kind not in (TRANSFER_KIND_FILE, TRANSFER_KIND_DIRECTORY):
        raise ValueError("Invalid transfer kind")
    data = (
        transfer_id.bytes
        + struct.pack("!B", len(filename_bytes))
        + filename_bytes
        + struct.pack("!Q", file_size)
        + struct.pack("!I", chunk_size)
        + struct.pack("!B", transfer_kind)
    )
    return data


def unpack_file_metadata(data: bytes) -> tuple[uuid.UUID, str, int, int]:
    transfer_id, filename, file_size, chunk_size, _ = unpack_transfer_metadata(data)
    return transfer_id, filename, file_size, chunk_size


def unpack_transfer_metadata(
    data: bytes,
) -> tuple[uuid.UUID, str, int, int, int]:
    minimum_size = 16 + 1 + 8 + 4 + 1
    if len(data) < minimum_size:
        raise ValueError("Metadata is too short")

    transfer_id = uuid.UUID(bytes=data[:16])
    filename_length = struct.unpack("!B", data[16:17])[0]
    filename_start = 17
    filename_end = filename_start + filename_length
    expected_size = filename_end + 8 + 4 + 1
    if len(data) != expected_size:
        raise ValueError("Invalid metadata length")

    filename_bytes = data[filename_start:filename_end]
    try:
        filename = filename_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Filename is not valid UTF-8") from error

    file_size_start = filename_end
    file_size_end = file_size_start + 8
    file_size = struct.unpack("!Q", data[file_size_start:file_size_end])[0]

    chunk_size_start = file_size_end
    chunk_size_end = chunk_size_start + 4
    chunk_size = struct.unpack("!I", data[chunk_size_start: chunk_size_end])[0]

    transfer_kind = struct.unpack("!B", data[chunk_size_end:expected_size])[0]
    if transfer_kind not in (TRANSFER_KIND_FILE, TRANSFER_KIND_DIRECTORY):
        raise ValueError("Invalid transfer kind")

    return transfer_id, filename, file_size, chunk_size, transfer_kind
