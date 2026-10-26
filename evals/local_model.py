"""Find, download and verify an open model to serve locally (python -m evals model resolve|fetch <preset>).

Downloads come from Hugging Face, which the GitHub runners can reach. Every file is pinned to the repo commit
it was resolved at and checked against the SHA-256 Hugging Face publishes for it, so a run records exactly
which weights produced its answers.
"""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path

PRESETS_FILE = Path(__file__).resolve().parent / "local_models.json"


class ModelError(Exception):
    pass


def presets() -> dict[str, dict]:
    return {k: v for k, v in json.loads(PRESETS_FILE.read_text()).items() if not k.startswith("_")}


def preset(name: str) -> dict:
    known = presets()
    if name not in known:
        raise ModelError(f"unknown preset {name!r}; choose one of {sorted(known)}")
    return known[name]


def choose_file(files: dict[str, str | None], pattern: str) -> str:
    """The one GGUF file whose name ends with `pattern`. `files` maps each file name to its SHA-256 (or None)."""
    matches = sorted(f for f in files if f.endswith(pattern) and "/" not in f)
    if len(matches) != 1:
        ggufs = sorted(f for f in files if f.endswith(".gguf"))
        raise ModelError(f"expected one file ending in {pattern!r}, found {matches or 'none'}; GGUF files: {ggufs[:20]}")
    return matches[0]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(name: str) -> dict:
    """Look the preset up on Hugging Face: the repo's current commit, the file, its size and SHA-256."""
    from huggingface_hub import HfApi

    spec = preset(name)
    info = HfApi().model_info(spec["repo"], files_metadata=True)
    files = {s.rfilename: (s.lfs.sha256 if s.lfs else None) for s in info.siblings}
    file = choose_file(files, spec["pattern"])
    if not files[file]:
        raise ModelError(f"{spec['repo']}/{file} has no published SHA-256 to check against")
    size = next(s.size for s in info.siblings if s.rfilename == file)
    return {"preset": name, "repo": spec["repo"], "file": file, "revision": info.sha, "sha256": files[file],
            "size_bytes": size, "parameters": spec["parameters"], "license": spec["license"]}


def fetch(resolved: dict, models_dir: Path) -> Path:
    """Download the resolved file into models_dir (unless a verified copy is already there) and check its SHA-256."""
    from huggingface_hub import hf_hub_download

    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / resolved["file"]
    if not (path.is_file() and sha256_file(path) == resolved["sha256"]):
        downloaded = Path(hf_hub_download(resolved["repo"], resolved["file"], revision=resolved["revision"],
                                          local_dir=models_dir))
        if downloaded.resolve() != path.resolve():
            downloaded.replace(path)
    actual = sha256_file(path)
    if actual != resolved["sha256"]:
        path.unlink()
        raise ModelError(f"{path.name}: SHA-256 {actual} doesn't match the published {resolved['sha256']}")
    return path


def server_version() -> str | None:
    try:
        return metadata.version("llama-cpp-python")
    except metadata.PackageNotFoundError:
        return None
