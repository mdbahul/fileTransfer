import socket

HOST = "127.0.0.1"
PORT = 8080

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
    client_socket.connect((HOST, PORT))
    message = "Hello from client"
    client_socket.sendall(message.encode("utf-8"))

    reply = client_socket.recv(1024)
    print(f"Server replied: {reply.decode('utf-8')}")
