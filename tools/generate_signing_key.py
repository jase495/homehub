from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    secret = ROOT.parent / "HomeHub-GitHub-signing-secret.txt"
    secret.write_text(base64.b64encode(raw).decode() + "\n", encoding="ascii")
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    (ROOT / "installer" / "update-public.key").write_bytes(public)
    print(f"Private GitHub secret (never commit): {secret}")
    print(f"Public appliance key: {ROOT / 'installer' / 'update-public.key'}")


if __name__ == "__main__":
    main()
