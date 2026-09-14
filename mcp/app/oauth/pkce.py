import base64
import hashlib


def verify_pkce(code_verifier: str, code_challenge: str, code_challenge_method: str) -> bool:
    """OAuth 2.1 mandates PKCE with S256; plain is rejected everywhere it's asked for."""
    if code_challenge_method != "S256":
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return computed == code_challenge
