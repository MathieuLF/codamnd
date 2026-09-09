"""Download and verify pinned portable tools; never install or modify host Python."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "packaging/windows/native/toolchain.json"
TOOLS = ROOT / "build/native-tools"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_members(archive: zipfile.ZipFile, prefix: str) -> list[tuple[zipfile.ZipInfo, str]]:
    members = []
    seen = set()
    for member in archive.infolist():
        name = member.filename
        if prefix and not name.startswith(prefix):
            raise ValueError("Préfixe d'archive inattendu.")
        name = name.removeprefix(prefix)
        if not name or member.is_dir():
            continue
        path = PurePosixPath(name)
        if (path.is_absolute() or "\\" in name or ":" in name or ".." in path.parts
                or any(part.endswith((".", " ")) for part in path.parts)
                or stat.S_ISLNK(member.external_attr >> 16) or name.casefold() in seen):
            raise ValueError("Chemin d'archive non conforme.")
        seen.add(name.casefold())
        members.append((member, name))
    return members


def verify_tree(archive_path: Path, destination: Path, spec: dict) -> None:
    if sha256(archive_path) != spec["sha256"]:
        raise ValueError("Archive différente du verrou de construction.")
    if destination.is_symlink() or destination.is_junction():
        raise ValueError("Le dossier de construction doit être local, sans lien.")
    with zipfile.ZipFile(archive_path) as archive:
        members = checked_members(archive, spec["strip_prefix"])
        expected = {name.casefold() for _, name in members}
        for item in destination.rglob("*"):
            if item.is_symlink() or item.is_junction():
                raise ValueError("Lien dans la chaîne de construction.")
            relative = item.relative_to(destination)
            if item.is_file() and "__pycache__" not in relative.parts and relative.as_posix().casefold() not in expected:
                raise ValueError(f"Fichier ajouté à la chaîne de construction : {relative}")
        for member, name in members:
            target = destination / name
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Chemin extrait hors du dossier prévu.")
            if sha256(target) != hashlib.sha256(archive.read(member)).hexdigest():
                raise ValueError(f"Fichier différent de l'archive officielle : {name}")


def prepare(name: str, *, download: bool = False) -> Path:
    spec = json.loads(LOCK.read_text(encoding="utf-8"))[name]
    destination = TOOLS / spec["directory"]
    archive_path = TOOLS / spec["url"].rsplit("/", 1)[-1]
    TOOLS.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        if not download:
            raise ValueError("Exécutez scripts/prepare_native_toolchain.py avant la construction.")
        # Partial downloads stay separate. A failed verification is never executed.
        with tempfile.NamedTemporaryFile(dir=TOOLS, suffix=".download", delete=False) as stream:
            temporary = Path(stream.name)
            with urllib.request.urlopen(spec["url"], timeout=60) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("Téléchargement sans HTTPS refusé.")
                shutil.copyfileobj(response, stream)
        if sha256(temporary) != spec["sha256"]:
            raise ValueError("Téléchargement différent de l'empreinte officielle épinglée.")
        temporary.rename(archive_path)
    if sha256(archive_path) != spec["sha256"]:
        raise ValueError("Archive différente du verrou de construction.")
    if not destination.exists():
        temporary_dir = Path(tempfile.mkdtemp(prefix="extract-", dir=TOOLS))
        with zipfile.ZipFile(archive_path) as archive:
            for member, relative in checked_members(archive, spec["strip_prefix"]):
                target = temporary_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        verify_tree(archive_path, temporary_dir, spec)
        temporary_dir.rename(destination)
    verify_tree(archive_path, destination, spec)
    return destination


if __name__ == "__main__":
    for tool in ("python", "zig"):
        print(f"{tool}: {prepare(tool, download=True)}")
