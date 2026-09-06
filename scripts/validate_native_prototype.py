"""Exercise a built native prototype using synthetic fixtures and isolated paths."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(app: Path) -> Path:
    app = app.resolve(strict=True)
    if not (app / "PROTOTYPE.md").is_file():
        raise ValueError("Le dossier ne correspond pas au prototype.")
    if sys.platform != "win32":
        raise ValueError("La validation du binaire exige Windows.")
    workspace = Path(tempfile.mkdtemp(prefix="validation-", dir=ROOT / "build/native-prototype"))
    fixtures = workspace / "fixtures"
    fixtures.mkdir()
    for source in (ROOT / "samples").glob("*.txt"):
        shutil.copyfile(source, fixtures / source.name)
    # Reuse the repository's synthetic PDF generator; never use payroll files.
    spec = importlib.util.spec_from_file_location("native_test_fixtures", ROOT / "tests/test_converter.py")
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    config = fixture_module.load_app_config(ROOT / "config")
    entries = fixture_module.parse_employeurd_file(fixtures / "employeurd-balanced.txt")
    fixture_module._write_synthetic_gl_detail_pdf(fixtures / "control.pdf", entries, config)
    from codamnd.converter import build_conversion_draft
    from codamnd.errors import ValidationFailed

    reference = build_conversion_draft(fixtures / "employeurd-balanced.txt", config)
    rejected = []
    for name in ("employeurd-unbalanced.txt", "employeurd-unknown-account.txt", "employeurd-zero-amount.txt"):
        try:
            build_conversion_draft(fixtures / name, config)
        except ValidationFailed:
            rejected.append(name)

    hostile = workspace / "ambient"
    hostile.mkdir()
    for name in ("sitecustomize.py", "usercustomize.py", "_codamnd_native.py", "codamnd.py"):
        (hostile / name).write_text("raise RuntimeError('ambient module must not load')\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.update({
        "PATH": str(Path(os.environ["SystemRoot"]) / "System32"),
        "PYTHONHOME": str(hostile), "PYTHONPATH": str(hostile), "PYTHONSTARTUP": str(hostile / "sitecustomize.py"),
        "PYTHONINSPECT": "1", "PYTHONWARNINGS": "error", "PYTHONUTF8": "0",
        "TCL_LIBRARY": str(hostile), "TK_LIBRARY": str(hostile), "TCLLIBPATH": str(hostile),
        "LOCALAPPDATA": str(workspace / "appdata"), "APPDATA": str(workspace / "appdata"),
        "TEMP": str(workspace), "TMP": str(workspace),
    })
    relocation = workspace / "Déplacement avec espaces" / "CodaMND"
    shutil.copytree(app, relocation)
    archives = list(app.parent.glob("CodaMND-v*-native-prototype.zip"))
    if len(archives) != 1:
        raise ValueError("Un seul ZIP prototype doit accompagner le dossier applicatif.")
    extracted = workspace / "extracted-zip"
    with zipfile.ZipFile(archives[0]) as archive:
        for member in archive.infolist():
            destination = (extracted / member.filename).resolve()
            if not destination.is_relative_to(extracted.resolve()):
                raise ValueError("Chemin ZIP hors du dossier de validation.")
        archive.extractall(extracted)
    results = []
    for label, candidate in (("original", app), ("relocated-accented-path", relocation), ("zip-extracted", extracted / "CodaMND")):
        output = workspace / f"{label}.json"
        completed = subprocess.run(
            [str(candidate / "CodaMND.exe"), "--diagnostic", str(output), str(fixtures)],
            cwd=hostile, env=environment, timeout=60, capture_output=True, text=True,
        )
        if not output.exists():
            raise RuntimeError(f"Diagnostic {label} absent (code {completed.returncode}): {completed.stderr}")
        report = json.loads(output.read_text(encoding="utf-8"))
        if completed.returncode or not report.get("ok"):
            raise RuntimeError(f"Diagnostic {label} en échec: {json.dumps(report)}; stderr={completed.stderr}")
        assert report["mnd_sha256"] == reference.mnd_sha256
        assert report["source_rows"] == len(reference.source_entries) == 20
        assert report["pdf_rows"] == 20
        assert report["pdf_debit"] == report["pdf_credit"] == "6643.00"
        assert report["rejected_samples"] == rejected
        results.append({"case": label, "ok": True, "report": output.name, "exe_exit_code": completed.returncode})
    for args in (("-c", "raise SystemExit(99)"), ("-m", "http.server"), ("ambient.py",)):
        completed = subprocess.run([str(app / "CodaMND.exe"), *args], cwd=hostile, env=environment, timeout=15, capture_output=True)
        assert completed.returncode == 2, (args, completed.returncode)
        results.append({"case": "reject " + args[0], "ok": True})
    # No fallback to an installed Python or a DLL on PATH when the bundle is missing.
    missing = workspace / "without-runtime"
    missing.mkdir()
    (missing / "lib").mkdir()
    shutil.copyfile(app / "CodaMND.exe", missing / "CodaMND.exe")
    completed = subprocess.run(
        [str(missing / "CodaMND.exe"), "--diagnostic", str(workspace / "must-not-exist.json"), str(fixtures)],
        cwd=hostile, env=environment, timeout=15, capture_output=True,
    )
    assert completed.returncode != 0
    assert not (workspace / "must-not-exist.json").exists()
    results.append({"case": "missing-private-runtime-fails-closed", "ok": True})
    inventory = json.loads((app / "prototype-inventory.json").read_text(encoding="utf-8"))
    assert not any("freeze" in item["name"].lower() for item in inventory["distributions"])
    summary = {"ok": True, "app": str(app), "reference_mnd_sha256": reference.mnd_sha256, "checks": results,
               "limitation": "Python is installed on the test host; PATH/env isolation and loaded-module confinement are tested, not a clean Windows VM."}
    (workspace / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(workspace)
    return workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    args = parser.parse_args()
    run(args.app)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
