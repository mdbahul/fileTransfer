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
    (length,) = struct.unpack(HEADER_FORMAT, header)

    return recv_exactly(sock, length)

def send_message(sock, payload):
    header = struct.pack(HEADER_FORMAT, len(payload))
    sock.sendall(header)
    sock.sendall(payload)