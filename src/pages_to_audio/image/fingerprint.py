"""Perceptual hash utilities — §3.1.1."""

from __future__ import annotations

import hashlib


def dhash(image_bytes: bytes, hash_size: int = 8) -> int:
    """
    Difference hash (dHash) — fast perceptual hash for near-duplicate detection.
    Returns an integer hash. Pure function, deterministic.
    """
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
            pixels = list(img.getdata())
    except Exception:
        # Fallback: use SHA-256 prefix as pseudo-hash
        return int(hashlib.sha256(image_bytes).hexdigest()[:16], 16)

    diff = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            if left > right:
                diff |= 1 << (row * hash_size + col)
    return diff


def hamming_distance(hash1: int, hash2: int) -> int:
    """Hamming distance between two perceptual hashes."""
    return bin(hash1 ^ hash2).count("1")


def are_near_duplicates(hash1: int, hash2: int, threshold: int = 10) -> bool:
    """True if two images are perceptually near-identical."""
    return hamming_distance(hash1, hash2) <= threshold
