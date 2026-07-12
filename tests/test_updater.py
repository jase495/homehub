import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from homehub.updater import verify_manifest, version_tuple


def test_signed_manifest_verification(tmp_path):
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    body = (json.dumps({"version": "1.2.3", "artifact": "homehub-1.2.3.tar.gz", "sha256": "a" * 64}, sort_keys=True) + "\n").encode()
    signature = base64.b64encode(private.sign(body))
    assert verify_manifest(body, signature, public_path)["version"] == "1.2.3"
    with pytest.raises(Exception):
        verify_manifest(body + b" ", signature, public_path)


def test_semantic_version_comparison_tuple():
    assert version_tuple("v1.10.0") > version_tuple("1.9.9")

