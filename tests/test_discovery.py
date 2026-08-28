import unittest

import discovery


class TestDiscoveryMessages(unittest.TestCase):
    def test_response_round_trip(self):
        data = discovery.pack_response("Laptop", 8080)

        self.assertEqual(
            discovery.unpack_response(data, "192.168.1.25"),
            discovery.DiscoveredDevice("Laptop", 8080, "192.168.1.25"),
        )

    def test_invalid_response_is_rejected(self):
        invalid_messages = (
            b"not json",
            b'{"type":"wrong","version":1,"device_name":"Laptop","tcp_port":8080}',
            b'{"type":"FILE_TRANSFER_DEVICE","version":1,"device_name":"Laptop","tcp_port":0}',
        )

        for message in invalid_messages:
            with self.subTest(message=message):
                with self.assertRaises(ValueError):
                    discovery.unpack_response(message, "127.0.0.1")

    def test_invalid_response_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            discovery.pack_response("", 8080)

        with self.assertRaises(ValueError):
            discovery.pack_response("Laptop", 70000)

        with self.assertRaises(ValueError):
            discovery.unpack_response(
                b'{"type":"FILE_TRANSFER_DEVICE","version":1,'
                b'"device_name":"Laptop","tcp_port":true}',
                "127.0.0.1",
            )


if __name__ == "__main__":
    unittest.main()
