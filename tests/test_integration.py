import hashlib
import socket
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

import client
import discovery
import server


def unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class TestDiscoveryAndTransfer(unittest.TestCase):
    def test_discover_device_then_transfer_file(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            source_path = directory_path / "integration.bin"
            output_directory = directory_path / "received"
            contents = bytes(range(256)) * 64
            source_path.write_bytes(contents)

            tcp_port = unused_local_port()
            discovery_port = unused_local_port()
            tcp_ready = threading.Event()
            discovery_stop = threading.Event()

            server_result = []
            tcp_thread = threading.Thread(
                target=lambda: server_result.append(
                    server.receive_file(
                        str(output_directory),
                        "127.0.0.1",
                        tcp_port,
                        tcp_ready,
                    )
                )
            )
            discovery_thread = threading.Thread(
                target=discovery.listen_for_discovery,
                kwargs={
                    "device_name": "integration-device",
                    "tcp_port": tcp_port,
                    "discovery_port": discovery_port,
                    "stop_event": discovery_stop,
                },
            )

            discovery_thread.start()
            tcp_thread.start()
            self.assertTrue(tcp_ready.wait(timeout=2))

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                    udp_socket.settimeout(2)
                    udp_socket.sendto(
                        discovery.DISCOVERY_REQUEST,
                        ("127.0.0.1", discovery_port),
                    )
                    data, address = udp_socket.recvfrom(
                        discovery.MAX_PACKET_SIZE
                    )

                device = discovery.unpack_response(data, address[0])
                self.assertEqual(device.device_name, "integration-device")
                self.assertEqual(device.tcp_port, tcp_port)

                digest = client.send_file(
                    str(source_path),
                    device.ip_address,
                    device.tcp_port,
                    uuid.uuid4(),
                    4096,
                    show_progress=False,
                )
            finally:
                discovery_stop.set()
                discovery_thread.join(timeout=2)

            tcp_thread.join(timeout=2)
            self.assertFalse(tcp_thread.is_alive())
            self.assertIsNotNone(server_result[0])
            self.assertEqual(
                digest,
                hashlib.sha256(contents).digest(),
            )
            self.assertEqual(Path(server_result[0]).read_bytes(), contents)


if __name__ == "__main__":
    unittest.main()
