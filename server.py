import socket
from protocol import send_message, receive_message

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
        message = receive_message(connection)
        print(f"Received: {message.decode('utf-8')}")
        message = "Hello from server"
        send_message(connection, message.encode("utf-8"))
