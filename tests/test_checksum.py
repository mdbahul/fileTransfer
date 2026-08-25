import unittest
import checksum


class TestChecksum(unittest.TestCase):
    def test_matching_digests(self):
        self.assertTrue(checksum.digest_match(b"abc", b"abc"))

    def test_different_digests(self):
        self.assertFalse(checksum.digest_match(b"abc", b"xyz"))

    def test_different_lengths(self):
        self.assertFalse(checksum.digest_match(b"abc", b"ab"))


if __name__ == "__main__":
    unittest.main()