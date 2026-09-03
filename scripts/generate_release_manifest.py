from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
MAX_ZIP_EXECUTABLE_BYTES = 256 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description="Génère et valide le manifeste JSON d'une mise en ligne.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--virustotal-report", type=Path)
    parser.add_argument("--require-clean-virustotal", action="store_true")
    args = parser.parse_args()

    version = args.version.strip().lstrip("v")
    name = "CodaMND"
    dist = Path("dist")
    app_dir = dist / name
    exe = app_dir / f"{name}.exe"
    portable_zip = dist / f"{name}-v{version}-portable.zip"
    exe_sha_file = dist / f"{name}-v{version}-portable.exe.sha256"
    zip_sha_file = dist / f"{name}-v{version}-portable.zip.sha256"
    package_sha_file = dist / f"{name}-v{version}.package.sha256"
    vt_report = args.virustotal_report or dist / f"{name}-v{version}.virustotal.md"
    output = args.output or dist / f"{name}-v{version}.release-manifest.json"

    issues = []
    for path in (exe, portable_zip, exe_sha_file, zip_sha_file, package_sha_file):
        if not path.exists():
            issues.append(f"Artefact manquant: {path}")

    exe_sha256 = sha256_file(exe) if exe.exists() else ""
    zip_sha256 = sha256_file(portable_zip) if portable_zip.exists() else ""
    expected_exe_sha256 = read_sha256(exe_sha_file) if exe_sha_file.exists() else ""
    expected_zip_sha256 = read_sha256(zip_sha_file) if zip_sha_file.exists() else ""
    package_sha256 = read_sha256(package_sha_file) if package_sha_file.exists() else ""
    if expected_exe_sha256 and exe_sha256.lower() != expected_exe_sha256.lower():
        issues.append("L'empreinte SHA256 de l'exécutable ne correspond pas au fichier .sha256.")
    if expected_zip_sha256 and zip_sha256.lower() != expected_zip_sha256.lower():
        issues.append("L'empreinte SHA256 du paquet portable ne correspond pas au fichier .sha256.")
    if package_sha_file.exists() and not package_sha256:
        issues.append("L'empreinte SHA256 du paquet applicatif est illisible.")
    if portable_zip.exists():
        try:
            zipped_exe_sha256 = zip_member_sha256(portable_zip, f"{name}/{exe.name}")
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
            issues.append(f"Le contenu du paquet portable est invalide: {error}")
        else:
            if exe_sha256 and zipped_exe_sha256.lower() != exe_sha256.lower():
                issues.append("L'exécutable contenu dans le ZIP ne correspond pas à l'exécutable contrôlé.")

    virustotal = parse_virustotal_report(vt_report)
    virustotal_provenance_valid = is_clean_virustotal_report(virustotal, exe_sha256)
    if args.require_clean_virustotal:
        if not vt_report.exists():
            issues.append(f"Rapport VirusTotal manquant: {vt_report}")
        elif not virustotal_provenance_valid:
            issues.append(
                "Le rapport VirusTotal doit confirmer l'exécutable exact, une analyse completed et 0 malicious / 0 suspicious."
            )

    if issues:
        for issue in issues:
            print(f"- {issue}")
        return 1

    signature = authenticode_status(exe) if exe.exists() else "n/d"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "application": name,
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "distribution": {
            "format": "portable_zip",
            "signed": signature == "Valid",
            "authenticode_status": signature,
            "primary_asset_policy": "portable_zip_only",
            "smartscreen_note": "Application non signée; avertissement SmartScreen possible.",
        },
        "package_sha256": package_sha256.lower(),
        "artifacts": [
            {
                "name": portable_zip.name,
                "type": "portable_zip",
                "sha256": zip_sha256.lower(),
            },
            {
                "name": exe.name,
                "type": "windows_executable_inside_zip",
                "path_inside_zip": f"{name}/{exe.name}",
                "sha256": exe_sha256.lower(),
            },
            {
                "name": exe_sha_file.name,
                "type": "sha256",
                "sha256": sha256_file(exe_sha_file).lower() if exe_sha_file.exists() else "",
            },
            {
                "name": zip_sha_file.name,
                "type": "sha256",
                "sha256": sha256_file(zip_sha_file).lower() if zip_sha_file.exists() else "",
            },
            {
                "name": package_sha_file.name,
                "type": "package_sha256",
                "sha256": package_sha256.lower(),
            },
        ],
        "virustotal": virustotal,
        "privacy": {
            "payroll_files_submitted": False if virustotal_provenance_valid else None,
            "only_public_executable_submitted": virustotal_provenance_valid,
            "report_bound_to_public_executable": virustotal_provenance_valid,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zip_member_sha256(path: Path, member_name: str) -> str:
    with zipfile.ZipFile(path) as archive:
        matches = [info for info in archive.infolist() if info.filename == member_name]
        if len(matches) != 1 or matches[0].is_dir():
            raise ValueError(f"le ZIP doit contenir exactement un fichier {member_name}.")
        member = matches[0]
        if member.file_size > MAX_ZIP_EXECUTABLE_BYTES:
            raise ValueError("l'exécutable contenu dans le ZIP dépasse la taille maximale permise.")
        digest = hashlib.sha256()
        total = 0
        with archive.open(member) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                total += len(chunk)
                if total > MAX_ZIP_EXECUTABLE_BYTES:
                    raise ValueError("l'exécutable contenu dans le ZIP dépasse la taille maximale permise.")
                digest.update(chunk)
    return digest.hexdigest()


def read_sha256(path: Path) -> str:
    match = SHA256_RE.search(path.read_text(encoding="ascii", errors="ignore"))
    return match.group(0) if match else ""


def parse_virustotal_report(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "report": path.name,
        "submitted": None,
        "status": "n/d",
        "malicious": None,
        "suspicious": None,
        "sha256": "",
        "link": "",
    }
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- Soumis à VirusTotal :"):
            result["submitted"] = stripped.endswith("oui")
        elif stripped.startswith("- SHA256 :"):
            match = SHA256_RE.search(stripped)
            result["sha256"] = match.group(0).lower() if match else ""
        elif stripped.startswith("- Statut :"):
            result["status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Lien :"):
            result["link"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- malicious :"):
            result["malicious"] = int(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("- suspicious :"):
            result["suspicious"] = int(stripped.split(":", 1)[1].strip())
    return result


def is_clean_virustotal_report(report: dict[str, Any], exe_sha256: str) -> bool:
    normalized_sha256 = exe_sha256.lower()
    return (
        report.get("submitted") is True
        and report.get("status") == "completed"
        and isinstance(report.get("malicious"), int)
        and not isinstance(report.get("malicious"), bool)
        and isinstance(report.get("suspicious"), int)
        and not isinstance(report.get("suspicious"), bool)
        and report.get("malicious") == 0
        and report.get("suspicious") == 0
        and str(report.get("sha256") or "").lower() == normalized_sha256
        and report.get("link") == f"https://www.virustotal.com/gui/file/{normalized_sha256}"
    )


def authenticode_status(path: Path) -> str:
    pe_status = pe_certificate_status(path)
    if pe_status == "NotSigned":
        return pe_status

    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    powershell = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe" if system_root else None
    if powershell is None or not powershell.is_file():
        return pe_status or "Non vérifiée"

    try:
        completed = subprocess.run(
            [
                str(powershell),
                "-NoProfile",
                "-Command",
                "$path = $env:CODAMND_SIGNATURE_PATH; Import-Module Microsoft.PowerShell.Security; (Get-AuthenticodeSignature -LiteralPath $path).Status",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env={**os.environ, "CODAMND_SIGNATURE_PATH": str(path.resolve())},
            cwd=Path(__file__).resolve().parents[1],
        )
    except FileNotFoundError:
        return pe_status or "Non vérifiée"
    return completed.stdout.strip() or pe_status or "Non vérifiée"


def pe_certificate_status(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None

    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 >= len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        return None

    optional_header_offset = pe_offset + 24
    magic = struct.unpack_from("<H", data, optional_header_offset)[0]
    if magic == 0x10B:
        data_directory_offset = optional_header_offset + 96
    elif magic == 0x20B:
        data_directory_offset = optional_header_offset + 112
    else:
        return None

    security_directory_offset = data_directory_offset + (8 * 4)
    if security_directory_offset + 8 > len(data):
        return None
    certificate_table_offset, certificate_table_size = struct.unpack_from("<II", data, security_directory_offset)
    if certificate_table_offset == 0 or certificate_table_size == 0:
        return "NotSigned"
    return "SignaturePresent"


if __name__ == "__main__":
    raise SystemExit(main())
