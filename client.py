import socket
import os
import protocol

HOST = "127.0.0.1"
PORT = 8080
CHUNK_SIZE = 4096

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
    client_socket.connect((HOST, PORT))

    file_path = "/Users/new/Desktop/fileTransfer/test.txt"
    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    
    metadata = protocol.pack_file_metadata(filename, file_size)
    protocol.send_message(client_socket, metadata)

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if chunk == b"":
                break
            client_socket.sendall(chunk)

    print(f"Sent: {filename} ({file_size} bytes)")



