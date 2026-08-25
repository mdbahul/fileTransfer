import struct
HEADER_FORMAT = "!I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

def recv_exactly(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if chunk == b'':
            raise ConnectionError('Connection closed before receiving enough data')

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

def pack_file_metadata(filename: str, file_size: int) -> bytes:
    filename_bytes = filename.encode("utf-8")
    if len(filename_bytes) > 255:
        raise ValueError("Filename too long")
    data = (
        struct.pack("!B", len(filename_bytes))
        + filename_bytes
        + struct.pack("!Q", file_size)
    )
    return data

def unpack_file_metadata(data: bytes) -> tuple[str, int]:
    filename_length = struct.unpack("!B", data[:1])[0]
    filename_start = 1
    filename_end = filename_start + filename_length

    filename_bytes = data[filename_start: filename_end]
    filename = filename_bytes.decode("utf-8")

    file_size = struct.unpack("!Q", data[filename_end:filename_end+8])[0]

    return filename, file_size


