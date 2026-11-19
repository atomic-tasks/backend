import hashlib


def hash_secret(raw: str) -> str:
    """SHA-256 секрета (PAT, сессии браузера, state входа). В базе хранится только он."""
    return hashlib.sha256(raw.encode()).hexdigest()
