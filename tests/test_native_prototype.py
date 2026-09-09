from __future__ import annotations

import hashlib
import json
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.build_native import FIXED_TIME, output_path, package_record_path, zip_entries


ROOT = Path(__file__).resolve().parents[1]


class NativePrototypeTests(unittest.TestCase):
    def test_toolchain_rejects_modified_and_unlisted_extracted_files(self):
        from scripts.prepare_native_toolchain import verify_tree

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "tool.zip"
            destination = root / "tool"
            destination.mkdir()
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("runtime.dll", b"synthetic")
            spec = {"sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(), "strip_prefix": ""}
            (destination / "runtime.dll").write_bytes(b"synthetic")
            verify_tree(archive_path, destination, spec)
            (destination / "runtime.dll").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_tree(archive_path, destination, spec)
            (destination / "runtime.dll").write_bytes(b"synthetic")
            (destination / "unexpected.dll").write_bytes(b"added")
            with self.assertRaises(ValueError):
                verify_tree(archive_path, destination, spec)

    def test_toolchain_rejects_unsafe_zip_paths_and_case_collisions(self):
        from scripts.prepare_native_toolchain import checked_members

        for names in (("../outside",), ("C:/outside",), ("x\\..\\outside",), ("x./file",), ("A", "a")):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as temporary:
                archive_path = Path(temporary) / "tool.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    for name in names:
                        archive.writestr(name, b"synthetic")
                with zipfile.ZipFile(archive_path) as archive, self.assertRaises(ValueError):
                    checked_members(archive, "")

    def test_virustotal_zero_with_failed_required_engine_blocks_release(self):
        from scripts import submit_virustotal as vt, generate_release_manifest as manifest

        for verdict, expected in (("failure", 6), ("undetected", 0), ("malicious", 4), ("unavailable", 6)):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as temporary:
                report = Path(temporary) / "report.md"
                stats = {"malicious": 0, "suspicious": 0, "undetected": 69}
                results = {"Zillya": {"category": verdict, "result": None}}
                args = ["submit_virustotal.py", "--file", "dist/CodaMND/CodaMND.exe", "--output", str(report),
                        "--no-dotenv", "--require-submit", "--fail-on-detections", "--require-engine", "Zillya"]
                with (patch("sys.argv", args), patch.dict(vt.os.environ, {"VT_API_KEY": "synthetic"}),
                      patch.object(vt, "validate_public_executable", return_value=Path("CodaMND.exe")),
                      patch.object(vt, "read_public_executable", return_value=b"synthetic"),
                      patch.object(vt, "post_file", return_value={"data": {"id": "synthetic"}}),
                      patch.object(vt, "poll_analysis", return_value={"data": {"attributes": {"status": "completed", "stats": stats, "results": results}}}),
                      patch.object(vt, "get_file_report", return_value={} )):
                    self.assertEqual(vt.main(), expected)
                parsed = manifest.parse_virustotal_report(report)
                self.assertEqual(parsed["required_engine"], "Zillya")
                self.assertEqual(parsed["required_engine_verdict"], verdict)

    def test_native_toolchain_and_ci_share_the_exact_python_version(self):
        lock = json.loads((ROOT / "packaging/windows/native/toolchain.json").read_text(encoding="utf-8"))
        for workflow in ("ci.yml", "release.yml"):
            self.assertIn(f'python-version: "{lock["python"]["version"]}"', (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8"))

    def test_signature_result_never_turns_unknown_or_offline_into_valid(self):
        from codamnd.integrity import signature_status

        results = {
            0: "Valid (cache local)", 0x800B0100: "NotSigned", 0x80096010: "HashMismatch",
            0x800B010C: "Revoked", 0x80092013: "Non vérifiée", 1: "Non vérifiée",
        }
        with patch("codamnd.integrity.sys.platform", "win32"), patch.object(Path, "is_file", return_value=True):
            for code, expected in results.items():
                with self.subTest(code=code), patch("codamnd.integrity._winverifytrust", return_value=code):
                    self.assertEqual(signature_status(Path("synthetic.exe")), expected)
            with patch("codamnd.integrity._winverifytrust", side_effect=OSError("unavailable")):
                self.assertEqual(signature_status(Path("synthetic.exe")), "Non vérifiée")

    def test_wintrust_is_offline_noninteractive_and_closes_provider_state(self):
        import ctypes
        from codamnd.integrity import _winverifytrust

        calls = []

        def verify(window, action, data_pointer):
            data = data_pointer._obj
            calls.append((window.value, data.ui, data.revocation, data.flags, data.state_action, data.file.contents.path))
            return -2146762496  # TRUST_E_NOSIGNATURE as signed LONG

        with patch.object(ctypes, "WinDLL", create=True) as loader:
            loader.return_value.WinVerifyTrust.side_effect = verify
            self.assertEqual(_winverifytrust(Path("synthetic.exe")), -2146762496)
        loader.assert_called_once_with("wintrust.dll", winmode=0x800)
        self.assertEqual([call[4] for call in calls], [1, 2])
        self.assertTrue(all(call[1:4] == (2, 1, 0x1080) for call in calls))
        self.assertTrue(all(call[5] == "synthetic.exe" for call in calls))

    def test_output_is_new_and_scoped_to_prototype_builds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = root / "build/native-release"
            for target in (root, allowed, root / "dist/CodaMND", allowed / "../../outside"):
                with self.assertRaises(ValueError):
                    output_path(target, root)
            child = allowed / "one"
            self.assertEqual(output_path(child, root), child.resolve())
            child.mkdir(parents=True)
            with self.assertRaises(ValueError):
                output_path(child, root)

    def test_package_record_filter_rejects_escaping_and_development_paths(self):
        for path in ("../Scripts/tool.exe", "/absolute.py", "C:/absolute.py", "x\\..\\secret", "x/__pycache__/a.pyc", "x/direct_url.json", "x/a.pyc"):
            with self.subTest(path=path):
                self.assertFalse(package_record_path(path))
        for path in ("pdfplumber/__init__.py", "pypdfium2_raw/pdfium.dll", "x.dist-info/licenses/LICENSE"):
            self.assertTrue(package_record_path(path))

    def test_zip_is_reproducible_and_uses_no_host_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"synthetic")
            first, second = root / "first.zip", root / "second.zip"
            zip_entries(first, [("b", source), ("a", source)])
            zip_entries(second, [("a", source), ("b", source)])
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ["a", "b"])
                self.assertTrue(all(info.date_time == FIXED_TIME for info in archive.infolist()))
            with self.assertRaises(FileExistsError):
                zip_entries(first, [])

    def test_entry_does_not_accept_interpreter_options(self):
        spec = importlib.util.spec_from_file_location("native_entry_test", ROOT / "packaging/windows/native/entry.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "configure_runtime"):
            for args in (["-c", "print(1)"], ["-m", "http.server"], ["arbitrary.py"], ["--diagnostic"]):
                self.assertEqual(module.main(args), 2)

    def test_entry_clears_tcl_environment_without_changing_package_code(self):
        spec = importlib.util.spec_from_file_location("native_environment_test", ROOT / "packaging/windows/native/entry.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(module.os.environ, {"TCL_LIBRARY": "ambient", "TK_LIBRARY": "ambient", "TCLLIBPATH": "ambient"}), patch.object(module.sys, "frozen", False, create=True):
            module.configure_runtime()
            self.assertTrue(module.sys.frozen)
            self.assertFalse(any(name in module.os.environ for name in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH")))


if __name__ == "__main__":
    unittest.main()
