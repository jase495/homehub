from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text().strip()
DIST = ROOT / "dist"
ARTIFACT = f"homehub-{VERSION}.tar.gz"
EXCLUDED = {".git", ".venv", ".pytest_cache", "dist", "work", "__pycache__"}


def include(path: Path) -> bool:
    return not any(
        part in EXCLUDED or part.endswith((".pyc", ".egg-info"))
        for part in path.relative_to(ROOT).parts
    )


def release_metadata(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Create portable ownership and executable modes, including on Windows."""
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    relative = Path(info.name).parts[1:]
    executable = relative and relative[0] == "installer" and (
        info.name.endswith(".sh") or Path(info.name).name.startswith("homehub-")
    )
    info.mode = 0o755 if executable else 0o644
    return info


def main() -> None:
    DIST.mkdir(exist_ok=True)
    archive = DIST / ARTIFACT
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and include(path):
                tar.add(
                    path,
                    arcname=Path(f"homehub-{VERSION}") / path.relative_to(ROOT),
                    recursive=False,
                    filter=release_metadata,
                )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {"artifact": ARTIFACT, "schema": 1, "sha256": digest, "version": VERSION}
    (DIST / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(archive)


if __name__ == "__main__":
    main()
