import hmac

def digest_match(expected: bytes, actual: bytes) -> bool:
    return hmac.compare_digest(expected, actual)