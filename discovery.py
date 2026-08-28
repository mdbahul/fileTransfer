import json
import socket
from dataclasses import dataclass
from threading import Event


DISCOVERY_PORT = 37020
DISCOVERY_VERSION = 1
DISCOVERY_REQUEST = b"FILE_TRANSFER_DISCOVERY|1"
DISCOVERY_RESPONSE = "FILE_TRANSFER_DEVICE"
MAX_PACKET_SIZE = 1024


@dataclass(frozen=True)
class DiscoveredDevice:
    device_name: str
    tcp_port: int
    ip_address: str


def pack_response(device_name: str, tcp_port: int) -> bytes:
    if not device_name or "|" in device_name:
        raise ValueError("Invalid device name")
    if not 1 <= tcp_port <= 65535:
        raise ValueError("TCP port must be between 1 and 65535")

    return json.dumps(
        {
            "type": DISCOVERY_RESPONSE,
            "version": DISCOVERY_VERSION,
            "device_name": device_name,
            "tcp_port": tcp_port,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def unpack_response(data: bytes, ip_address: str) -> DiscoveredDevice:
    try:
        message = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed discovery response") from error

    if (
        not isinstance(message, dict)
        or message.get("type") != DISCOVERY_RESPONSE
        or message.get("version") != DISCOVERY_VERSION
        or not isinstance(message.get("device_name"), str)
        or not isinstance(message.get("tcp_port"), int)
        or isinstance(message.get("tcp_port"), bool)
        or not 1 <= message["tcp_port"] <= 65535
        or not message["device_name"]
    ):
        raise ValueError("Invalid discovery response")

    return DiscoveredDevice(
        device_name=message["device_name"],
        tcp_port=message["tcp_port"],
        ip_address=ip_address,
    )


def broadcast_discovery(
    discovery_port: int = DISCOVERY_PORT,
    timeout: float = 1.0,
) -> list[DiscoveredDevice]:
    if not 1 <= discovery_port <= 65535:
        raise ValueError("Discovery port must be between 1 and 65535")
    if timeout <= 0:
        raise ValueError("Timeout must be positive")

    devices: dict[tuple[str, int], DiscoveredDevice] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(("", 0))
        udp_socket.settimeout(timeout)
        udp_socket.sendto(
            DISCOVERY_REQUEST,
            ("255.255.255.255", discovery_port),
        )

        while True:
            try:
                data, address = udp_socket.recvfrom(MAX_PACKET_SIZE)
            except socket.timeout:
                break

            try:
                device = unpack_response(data, address[0])
            except ValueError:
                continue

            devices[(device.ip_address, device.tcp_port)] = device

    return list(devices.values())


def listen_for_discovery(
    device_name: str,
    tcp_port: int,
    discovery_port: int = DISCOVERY_PORT,
    stop_event: Event | None = None,
) -> None:
    response = pack_response(device_name, tcp_port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(("", discovery_port))
        if stop_event is not None:
            udp_socket.settimeout(0.5)

        while stop_event is None or not stop_event.is_set():
            try:
                data, address = udp_socket.recvfrom(MAX_PACKET_SIZE)
            except socket.timeout:
                continue

            if data == DISCOVERY_REQUEST:
                udp_socket.sendto(response, address)
