"""Explicit local diagnostic for the prototype. Uses supplied synthetic fixtures.

No upload or real update request. Never overwrite an existing report.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import traceback
from pathlib import Path


def inspect(fixtures: Path) -> dict:
    import ctypes
    import ssl
    from unittest.mock import patch

    import pypdfium2
    from codamnd.app_gui import CodaMNDApp
    from codamnd.config import load_app_config
    from codamnd.converter import build_conversion_draft
    from codamnd.errors import ValidationFailed
    from codamnd.integrity import app_package_sha256, check_running_app_integrity
    from codamnd.preferences import AppPreferences
    from codamnd.reports.gl_detail_pdf_parser import parse_gl_detail_pdf
    from codamnd.resource_paths import default_config_dir, package_asset_path
    from codamnd.update_check import check_for_update

    root = Path(sys.executable).resolve().parent
    before = app_package_sha256(root)
    if not before:
        raise AssertionError("Package hash unavailable")
    config_dir = default_config_dir()
    assert config_dir == root / "config"
    config = load_app_config(config_dir)
    source = fixtures / "employeurd-balanced.txt"
    draft = build_conversion_draft(source, config)
    rejected = []
    for name in ("employeurd-unbalanced.txt", "employeurd-unknown-account.txt", "employeurd-zero-amount.txt"):
        try:
            build_conversion_draft(fixtures / name, config)
        except ValidationFailed:
            rejected.append(name)
    pdf = parse_gl_detail_pdf(fixtures / "control.pdf")
    with pypdfium2.PdfDocument(str(fixtures / "control.pdf")) as document:
        page = document[0]
        bitmap = page.render(scale=0.25)
        rendered = bitmap.to_pil()
        rendered_size = list(rendered.size)
        rendered.close()
        bitmap.close()
        page.close()
    # Initialize the actual GUI; do not consult the user's saved preferences.
    with patch("codamnd.app_gui.load_preferences", return_value=AppPreferences()):
        app = CodaMNDApp()
    try:
        app.withdraw()
        app.update_idletasks()
        app.update()
        title = app.title()
        icons = len(app._window_icons)
        tcl_version = app.tk.call("info", "patchlevel")
        app.source_path.set(str(source))
        app.control_report_path.set(str(fixtures / "control.pdf"))
        app._refresh_all()
        validation = app.controller.validate(
            source_path=source, control_report_path=fixtures / "control.pdf", require_control_report=True,
        )
        assert validation.ok
        with tempfile.TemporaryDirectory(prefix="codamnd-probe-", dir=fixtures.parent) as temporary:
            generated = app.controller.generate(
                source_path=source, output_root=Path(temporary),
                control_report_path=fixtures / "control.pdf", require_control_report=True,
                write_report=True, write_validation_json=True,
            )
            conversion = generated.conversion
            assert generated.ok and conversion
            actual_mnd = hashlib.sha256(conversion.output_path.read_bytes()).hexdigest()
            assert actual_mnd == draft.mnd_sha256
            assert conversion.report_path.is_file() and conversion.validation_json_path.is_file()
    finally:
        app.destroy()
    # Exercise the real integrity/update logic against deterministic local replies.
    with patch("codamnd.integrity._fetch_json", return_value={"package_sha256": before}):
        integrity = check_running_app_integrity("https://example.invalid/unused", frozen=True)
    with patch("codamnd.update_check._fetch_json", return_value={"tag_name": "v0.2.1", "html_url": "https://github.com/MathieuLF/codamnd/releases/tag/v0.2.1"}):
        update = check_for_update("https://example.invalid/version.json")
    assert update.ok and not update.update_available, update.message
    after = app_package_sha256(root)
    assert before == after, "The running package was modified"
    assert integrity.verified, integrity.message
    assert icons > 0
    loaded_python = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetModuleFileNameW(ctypes.c_void_p(sys.dllhandle), loaded_python, len(loaded_python))
    assert Path(loaded_python.value).resolve() == root / "python314.dll"
    assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.dont_write_bytecode
    assert all(Path(item).resolve().is_relative_to(root) for item in sys.path)
    modules = {
        name: module.__file__
        for name, module in sorted(sys.modules.items())
        if getattr(module, "__file__", None)
    }
    assert all(Path(path).resolve().is_relative_to(root) for path in modules.values())
    return {
        "ok": True, "python": sys.version, "executable": sys.executable,
        "loaded_python": loaded_python.value, "sys_path": sys.path, "loaded_modules": modules,
        "isolated": sys.flags.isolated, "ignore_environment": sys.flags.ignore_environment,
        "write_bytecode": not sys.flags.dont_write_bytecode, "frozen": sys.frozen,
        "config_dir": str(config_dir), "icon": str(package_asset_path("app-icon.png")),
        "gui_title": title, "icons_loaded": icons, "tcl_version": tcl_version,
        "source_rows": len(draft.source_entries), "mnd_sha256": actual_mnd,
        "rejected_samples": rejected, "pdf_rows": pdf.row_count,
        "pdf_debit": str(pdf.debit_total), "pdf_credit": str(pdf.credit_total),
        "pdf_render_size": rendered_size, "openssl": ssl.OPENSSL_VERSION,
        "integrity": integrity.status, "update_ok": update.ok,
        "package_sha256_before": before, "package_sha256_after": after,
    }


def run(output: Path, fixtures: Path) -> int:
    # Reserve the report before doing work, and never silently replace user data.
    try:
        with output.open("x", encoding="utf-8") as stream:
            try:
                from unittest.mock import patch

                with patch("urllib.request.urlopen", side_effect=AssertionError("Network is forbidden in this diagnostic")):
                    report = inspect(fixtures.resolve(strict=True))
                result = 0
            except Exception:
                report = {"ok": False, "error": traceback.format_exc()}
                result = 1
            json.dump(report, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
        return result
    except OSError:
        return 2
