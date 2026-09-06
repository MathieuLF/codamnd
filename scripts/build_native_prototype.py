"""Build a separate, inspectable Windows prototype; never publish or scan online.

Run using the Python 3.14 release venv. The official cx_Freeze workflow is untouched.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
import zipfile
from importlib import metadata
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "packaging/windows/native"
ZIG_VERSION = "0.15.2"
ZIG_ARCHIVE_SHA256 = "3a0ed1e8799a2f8ce2a6e6290a9ff22e6906f8227865911fb7ddedc3cc14cb0c"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def output_path(value: Path, root: Path = ROOT) -> Path:
    target = value.resolve()
    allowed = (root / "build/native-prototype").resolve()
    if target == allowed or not target.is_relative_to(allowed):
        raise ValueError("Choisissez un nouveau sous-dossier de build/native-prototype.")
    if target.exists():
        raise ValueError("Le dossier existe déjà; aucune preuve ni version existante ne sera remplacée.")
    return target


def zip_entries(destination: Path, entries: list[tuple[str, Path]]) -> None:
    """Stable ZIP metadata, no host paths or build timestamps."""
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, source in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, source.read_bytes(), compresslevel=9)


def runtime_distributions(lock: dict[str, str]) -> list[metadata.Distribution]:
    # Build-only dependency; ordinary tests/reviews need no packaging toolchain.
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    pending = ["pdfplumber"]
    found: dict[str, metadata.Distribution] = {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found:
            continue
        distribution = metadata.distribution(name)
        if distribution.version != lock.get(name):
            raise ValueError(f"Dépendance absente du verrou ou différente : {name}=={distribution.version}")
        found[name] = distribution
        for raw in distribution.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                installed = metadata.version(requirement.name)
                if installed not in requirement.specifier:
                    raise ValueError(f"Dépendance incompatible : {requirement}")
                pending.append(requirement.name)
    return [found[name] for name in sorted(found)]


def package_record_path(path: str) -> bool:
    relative = PurePosixPath(path)
    return (
        not relative.is_absolute()
        and "\\" not in path
        and ":" not in path
        and ".." not in relative.parts
        and "__pycache__" not in relative.parts
        and relative.suffix not in {".pyc", ".exe"}
        and relative.name not in {"direct_url.json", "INSTALLER", "REQUESTED"}
    )


def build(target: Path, zig: Path) -> Path:
    target = output_path(target)
    if sys.platform != "win32" or sys.version_info[:2] != (3, 14) or platform.machine() != "AMD64":
        raise ValueError("Le prototype exige CPython 3.14 Windows x64.")
    # Keep all compiler cache/artifacts inside the build workspace.
    zig = zig.resolve(strict=True)
    compiler_archive = zig.parent.parent / f"zig-x86_64-windows-{ZIG_VERSION}.zip"
    if sha256(compiler_archive) != ZIG_ARCHIVE_SHA256:
        raise ValueError("Archive du compilateur non conforme à l'empreinte épinglée.")
    with zipfile.ZipFile(compiler_archive) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            extracted = zig.parent.parent / member.filename
            if not extracted.resolve().is_relative_to(zig.parent) or extracted.is_symlink():
                raise ValueError("Chemin du compilateur extrait non conforme.")
            if hashlib.sha256(archive.read(member)).hexdigest() != sha256(extracted):
                raise ValueError(f"Fichier du compilateur différent de l'archive : {member.filename}")
    if subprocess.check_output([str(zig), "version"], text=True).strip() != ZIG_VERSION:
        raise ValueError("Version de compilateur différente de celle attendue.")

    from scripts.generate_sbom import _locked_requirements

    lock = _locked_requirements(ROOT / "requirements-release.txt")
    distributions = runtime_distributions(lock)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if len(version.split(".")) != 3 or not all(part.isdigit() for part in version.split(".")):
        raise ValueError("Version produit invalide.")
    runtime = Path(sys.base_prefix)
    if not (runtime / "tcl/libtcl9.0.4.zip").is_file() or not (runtime / "tcl/libtk9.0.4.zip").is_file():
        raise ValueError("Ce prototype exige les archives Tcl/Tk 9.0.4 de CPython 3.14.7.")
    if platform.python_version() != "3.14.7":
        raise ValueError("Ce prototype est validé avec CPython 3.14.7 uniquement.")
    target.mkdir(parents=True)
    app = target / "CodaMND"
    app.mkdir()
    lib = app / "lib"
    lib.mkdir()
    provenance: dict[str, dict[str, str]] = {}

    def copy(source: Path, relative: str, origin: str) -> None:
        destination = app / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Source absente ou lien non accepté : {relative}")
        if destination.exists():
            raise ValueError(f"Collision dans le paquet : {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        provenance[relative] = {"origin": origin, "sha256": sha256(destination)}

    for name in ("python314.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        copy(runtime / name, name, "CPython 3.14.7")
    copy(runtime / "LICENSE.txt", "licenses/Python.txt", "CPython 3.14.7")
    copy(zig.parent / "LICENSE", "licenses/Zig.txt", f"Zig {ZIG_VERSION}")
    copy(zig.parent / "lib/libc/mingw/COPYING", "licenses/mingw-w64.txt", f"Zig {ZIG_VERSION} mingw-w64 runtime")
    for source in sorted((runtime / "DLLs").iterdir()):
        if source.suffix.lower() in {".dll", ".pyd"} and not source.name.startswith(("_test", "_ctypes_test", "_remote_debugging")):
            copy(source, "lib/" + source.name, "CPython 3.14.7 DLLs")
    for source in sorted((runtime / "tcl").rglob("*")):
        relative = source.relative_to(runtime).as_posix()
        if source.is_file() and source.suffix not in {".lib", ".sh"} and "nmake" not in source.parts:
            copy(source, relative, "CPython Tcl/Tk 9.0.4")

    stdlib = runtime / "Lib"
    sources = []
    for source in sorted(stdlib.rglob("*.py")):
        relative = source.relative_to(stdlib)
        if any(part in {"site-packages", "__pycache__", "test", "tests", "idlelib", "ensurepip", "turtledemo"} for part in relative.parts):
            continue
        sources.append((relative.as_posix(), source))
    zip_entries(lib / "library.zip", sources)
    provenance["lib/library.zip"] = {"origin": "CPython 3.14.7 standard library", "sha256": sha256(lib / "library.zip")}

    for distribution in distributions:
        origin = f"{distribution.metadata['Name']}=={distribution.version}"
        for record in distribution.files or []:
            if not package_record_path(str(record)):
                continue
            source = Path(distribution.locate_file(record))
            if record.hash is not None:
                actual = hashlib.new(record.hash.mode, source.read_bytes()).digest()
                if base64.urlsafe_b64encode(actual).rstrip(b"=").decode() != record.hash.value:
                    raise ValueError(f"Fichier installé différent du RECORD : {origin}/{record}")
            copy(source, "lib/" + record.as_posix(), origin)
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", "src/codamnd", "config"], cwd=ROOT)
    for name in tracked.decode("utf-8").split("\0"):
        if name:
            relative = "lib/" + name.removeprefix("src/") if name.startswith("src/") else name
            copy(ROOT / name, relative, "CodaMND source")
    copy(NATIVE / "entry.py", "lib/_codamnd_native.py", "CodaMND native entry")
    copy(NATIVE / "probe.py", "lib/_codamnd_probe.py", "CodaMND prototype diagnostics")
    copy(ROOT / "LICENSE", "licenses/CodaMND.txt", "CodaMND license")
    copy(NATIVE / "README.md", "PROTOTYPE.md", "Prototype notice")

    # Resource compiler inputs are generated, not patched after linking.
    resource = target / "launcher.rc"
    icon = (ROOT / "packaging/windows/CodaMND.ico").as_posix()
    manifest = (ROOT / "packaging/windows/CodaMND.manifest").as_posix()
    resource.write_text(
        f'1 ICON "{icon}"\n1 24 "{manifest}"\n'
        f'1 VERSIONINFO\nFILEVERSION {version.replace(".", ",")},0\nPRODUCTVERSION {version.replace(".", ",")},0\n'
        'FILEOS 0x40004\nFILETYPE 1\nBEGIN\nBLOCK "StringFileInfo"\nBEGIN\nBLOCK "040904B0"\nBEGIN\n'
        'VALUE "FileDescription", "CodaMND - prototype"\nVALUE "ProductName", "CodaMND"\n'
        f'VALUE "FileVersion", "{version}"\nVALUE "ProductVersion", "{version}"\n'
        'VALUE "OriginalFilename", "CodaMND.exe"\nEND\nEND\nBLOCK "VarFileInfo"\nBEGIN\n'
        'VALUE "Translation", 0x0409, 1200\nEND\nEND\n', encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["ZIG_GLOBAL_CACHE_DIR"] = str(ROOT / "build/native-tools/cache")
    environment["ZIG_LOCAL_CACHE_DIR"] = str(target / "zig-cache")
    resource_object = target / "launcher.res"
    subprocess.run([str(zig), "rc", "/fo", str(resource_object), str(resource)], check=True, env=environment)
    command = [
        # Production symbol stripping keeps build-specific debug IDs/paths out
        # of the portable artifact; source and provenance remain available.
        str(zig), "cc", "-target", "x86_64-windows-gnu", "-std=c17", "-O2", "-g0", "-s",
        "-Wall", "-Wextra", "-Werror", "-municode", "-Wl,--subsystem,windows",
        str(NATIVE / "launcher.c"), str(resource_object), "-luser32", "-lshell32",
        "-o", str(app / "CodaMND.exe"),
    ]
    subprocess.run(command, check=True, env=environment)
    # Debug/build products belong outside the distributable if the linker creates any.
    for source in app.glob("*.pdb"):
        source.rename(target / source.name)
    provenance["CodaMND.exe"] = {"origin": f"launcher.c / Zig {ZIG_VERSION}", "sha256": sha256(app / "CodaMND.exe")}
    inventory = {
        "kind": "native-prototype-not-for-release", "version": version,
        "python": platform.python_version(), "compiler": f"Zig {ZIG_VERSION}",
        "compiler_archive_sha256": ZIG_ARCHIVE_SHA256,
        "lock_sha256": sha256(ROOT / "requirements-release.txt"),
        "launcher_source_sha256": sha256(NATIVE / "launcher.c"),
        "distributions": [{"name": item.metadata["Name"], "version": item.version} for item in distributions],
        "files": dict(sorted(provenance.items())),
    }
    (app / "prototype-inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    zip_path = target / f"CodaMND-v{version}-native-prototype.zip"
    zip_entries(zip_path, [(path.relative_to(target).as_posix(), path) for path in app.rglob("*") if path.is_file()])
    (target / (zip_path.name + ".sha256")).write_text(f"{sha256(zip_path)}  {zip_path.name}\n", encoding="ascii")
    print(json.dumps({"app": str(app), "exe_sha256": sha256(app / "CodaMND.exe"), "zip_sha256": sha256(zip_path)}, indent=2))
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--zig", type=Path, default=ROOT / f"build/native-tools/zig-x86_64-windows-{ZIG_VERSION}/zig.exe")
    args = parser.parse_args()
    build(output_path(args.output), args.zig)
    return 0


if __name__ == "__main__":
    # Support direct execution as well as python -m scripts.build_native_prototype.
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
