from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import VERSION
from .config import STATE_DIR, load_config

GITHUB_API = "https://api.github.com"
INSTALL_ROOT = Path(os.getenv("HOMEHUB_INSTALL_ROOT", "/opt/homehub"))


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.removeprefix("v").split(".") if part.isdigit())


@dataclass
class VerifiedRelease:
    version: str
    manifest: dict[str, Any]
    artifact_url: str
    manifest_url: str
    signature_url: str


def _asset_map(release: dict[str, Any]) -> dict[str, str]:
    return {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}


def _get(url: str) -> bytes:
    response = requests.get(url, timeout=30, headers={"Accept": "application/vnd.github+json", "User-Agent": f"HomeHub/{VERSION}"})
    response.raise_for_status()
    return response.content


def load_public_key(path: Path) -> Ed25519PublicKey:
    if not path.exists():
        raise RuntimeError(f"OTA signing is not enrolled: missing {path}")
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimeError("HomeHub update public key is not Ed25519")
    return key


def verify_manifest(manifest_bytes: bytes, signature_bytes: bytes, public_key_path: Path) -> dict[str, Any]:
    signature = base64.b64decode(signature_bytes.strip(), validate=True)
    load_public_key(public_key_path).verify(signature, manifest_bytes)
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or not all(key in manifest for key in ("version", "artifact", "sha256")):
        raise RuntimeError("Update manifest is incomplete")
    return manifest


def check_release() -> VerifiedRelease | None:
    cfg = load_config()
    updates = cfg.get("updates", {})
    repository = str(updates.get("repository", "")).strip()
    if not repository or "/" not in repository:
        raise RuntimeError("Set updates.repository to OWNER/REPOSITORY in HomeHub setup")
    release = requests.get(
        f"{GITHUB_API}/repos/{repository}/releases/latest",
        timeout=20,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"HomeHub/{VERSION}"},
    )
    release.raise_for_status()
    release_data = release.json()
    assets = _asset_map(release_data)
    manifest_url = assets.get("manifest.json")
    signature_url = assets.get("manifest.sig")
    if not manifest_url or not signature_url:
        raise RuntimeError("Latest GitHub Release has no signed HomeHub manifest")
    manifest_bytes = _get(manifest_url)
    manifest = verify_manifest(
        manifest_bytes,
        _get(signature_url),
        Path(updates.get("public_key_path", "/etc/homehub/update-public.key")),
    )
    artifact_url = assets.get(str(manifest["artifact"]))
    if not artifact_url:
        raise RuntimeError("Signed artifact named by the manifest is missing")
    if version_tuple(str(manifest["version"])) <= version_tuple(VERSION):
        return None
    return VerifiedRelease(str(manifest["version"]), manifest, artifact_url, manifest_url, signature_url)


def _safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        root = destination.resolve()
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError("Update archive contains an unsafe path")
        # Every member was resolved and checked above. Avoid the newer `filter`
        # argument so the updater also works on Raspberry Pi OS with Python 3.11.
        tar.extractall(destination)


def install_release(expected_version: str = "") -> None:
    if os.geteuid() != 0:
        raise PermissionError("Updates must run through the root HomeHub update service")
    release = check_release()
    if release is None:
        return
    if expected_version and release.version != expected_version:
        raise RuntimeError(f"Requested {expected_version}, but signed latest release is {release.version}")
    update_dir = STATE_DIR / "updates" / release.version
    update_dir.mkdir(parents=True, exist_ok=True)
    archive = update_dir / str(release.manifest["artifact"])
    archive.write_bytes(_get(release.artifact_url))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != release.manifest["sha256"]:
        raise RuntimeError("Update artifact SHA-256 does not match the signed manifest")

    releases = INSTALL_ROOT / "releases"
    destination = releases / release.version
    staging = releases / f".{release.version}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _safe_extract(archive, staging)
    children = [item for item in staging.iterdir()]
    source = children[0] if len(children) == 1 and children[0].is_dir() else staging
    preflight = source / "installer" / "preflight.sh"
    subprocess.run([str(preflight), str(source)], check=True)
    if destination.exists():
        shutil.rmtree(destination)
    if source == staging:
        staging.replace(destination)
    else:
        source.replace(destination)
        shutil.rmtree(staging, ignore_errors=True)

    current = INSTALL_ROOT / "current"
    previous = current.resolve() if current.exists() else None
    next_link = INSTALL_ROOT / ".current.next"
    next_link.unlink(missing_ok=True)
    next_link.symlink_to(destination)
    next_link.replace(current)
    try:
        subprocess.run([str(destination / "installer" / "activate.sh"), str(destination)], check=True)
        deadline = time.monotonic() + 45
        healthy = False
        while time.monotonic() < deadline:
            try:
                response = requests.get("http://127.0.0.1:8080/api/health", timeout=2)
                healthy = response.ok and response.json().get("version") == release.version
                if healthy:
                    break
            except requests.RequestException:
                pass
            time.sleep(2)
        if not healthy:
            raise RuntimeError("New HomeHub version failed its health check")
        subprocess.run(["systemctl", "restart", "homehub-kiosk.service"], check=True)
    except Exception:
        if previous:
            rollback = INSTALL_ROOT / ".current.rollback"
            rollback.unlink(missing_ok=True)
            rollback.symlink_to(previous)
            rollback.replace(current)
            subprocess.run([str(previous / "installer" / "activate.sh"), str(previous)], check=False)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    install = sub.add_parser("install")
    install.add_argument("--version", default="")
    args = parser.parse_args()
    if args.command == "check":
        release = check_release()
        print(json.dumps({"current": VERSION, "available": bool(release), "version": release.version if release else None}))
    else:
        install_release(args.version)


if __name__ == "__main__":
    main()
