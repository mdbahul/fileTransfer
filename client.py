import socket
from protocol import send_message, receive_message

HOST = "127.0.0.1"
PORT = 8080

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
    client_socket.connect((HOST, PORT))
    message = "Hello from client"
    send_message(client_socket,message.encode("utf-8"))

    reply = receive_message(client_socket)
    print(f"Server replied: {reply.decode('utf-8')}")
