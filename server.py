import socket

HOST = "127.0.0.1"
PORT = 8080

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()

    print(f"Waiting for a client on {HOST}:{PORT}...")
    connection, client_address = server_socket.accept()

    with connection:
        print(f"Connected to {client_address}")
        message = connection.recv(1024)
        print(f"Received: {message.decode('utf-8')}")
        connection.sendall(b"Hello from server")
