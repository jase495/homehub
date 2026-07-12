from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    encoded = os.environ.get("HOMEHUB_UPDATE_SIGNING_KEY", "")
    if not encoded:
        raise SystemExit("HOMEHUB_UPDATE_SIGNING_KEY is not set")
    private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded, validate=True))
    manifest = (ROOT / "dist" / "manifest.json").read_bytes()
    (ROOT / "dist" / "manifest.sig").write_bytes(base64.b64encode(private.sign(manifest)) + b"\n")


if __name__ == "__main__":
    main()
