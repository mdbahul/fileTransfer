import socket
import protocol

HOST = "127.0.0.1"
PORT = 8080
CHUNK_SIZE = 4096

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()

    print(f"Waiting for a client on {HOST}:{PORT}...")
    connection, client_address = server_socket.accept()

    with connection:
        print(f"Connected to {client_address}")
        metadata = protocol.receive_message(connection)
        filename, file_size = protocol.unpack_file_metadata(metadata)
        newFileName = f"new_{filename}"

        remaining = file_size
        with open(newFileName, "wb") as f:
            while remaining > 0:
                chunk = connection.recv(min(remaining, CHUNK_SIZE))

                if chunk == b"":
                    raise ConnectionError("Connection closed during transfer")

                f.write(chunk)
                remaining -= len(chunk)

        print(f"Received: {newFileName} ({file_size} bytes)")



