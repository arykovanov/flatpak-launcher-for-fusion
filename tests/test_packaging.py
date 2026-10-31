# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fusion_bootstrapper", ROOT / "packaging/fusion360.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fusion package tests ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.app = module.Fusion(data=self.base / "data", cache=self.base / "cache",
                                 shared=self.base / "shared")
        self.app.flatpak = False

    def executable(self, name="Fusion360.exe"):
        target = self.app.prefix / "drive_c/Program Files/Autodesk/webdeploy/production/version" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"MZtest")
        return target

    def runtime(self):
        for name in ("wine", "wineserver", "wineboot"):
            target = self.app.runtime / "bin" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/bin/sh\nexit 0\n")
            target.chmod(0o755)

    def installed(self):
        self.runtime()
        self.executable()
        self.app.marker.write_text(json.dumps({"wine_version": self.app.sources["wine"]["version"]}))

    def test_status_and_dry_run_do_not_create_data(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.base / "fresh-data"),
                                    "XDG_CACHE_HOME": str(self.base / "fresh-cache")}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(["--status"]), 1)
                self.assertEqual(module.main(["--dry-run"]), 0)
        self.assertEqual(list(self.base.iterdir()), [])

    def test_symlinked_entrypoint_finds_sources(self):
        entry = self.base / "fusion360"
        entry.symlink_to(ROOT / "packaging/fusion360.py")
        result = subprocess.run(["python3", str(entry), "--dry-run"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wine", json.loads(result.stdout)["sources"])

    def test_ready_requires_marker_runtime_and_application(self):
        self.assertFalse(self.app.ready())
        self.installed()
        self.assertTrue(self.app.ready())
        self.executable().unlink()
        self.assertFalse(self.app.ready())

    def test_corrupt_marker_is_not_installed(self):
        self.installed()
        for state in ("broken json", "[]", "null"):
            self.app.marker.write_text(state)
            self.assertFalse(self.app.ready())

    def test_environment_uses_private_prefix_and_runtime(self):
        with patch.dict(os.environ, {"WINEPREFIX": "/wrong", "WINEDLLPATH": "/wrong"}):
            env = self.app.environment()
        self.assertEqual(env["WINEPREFIX"], str(self.app.prefix))
        self.assertEqual(env["WINE"], str(self.app.runtime / "bin/wine"))
        self.assertNotIn("WINEDLLPATH", env)

    def test_shared_folder_is_wine_drive_h(self):
        self.app.configure_shared_drive()
        drive = self.app.prefix / "dosdevices/h:"
        self.assertTrue(self.app.shared_models.is_dir())
        self.assertTrue(drive.is_symlink())
        self.assertEqual(drive.resolve(), self.app.shared_models.resolve())
        # Reconfiguration is idempotent and does not replace the mapping.
        self.app.configure_shared_drive()
        self.assertEqual(drive.resolve(), self.app.shared_models.resolve())

    def test_default_shared_folder_uses_real_host_home(self):
        with patch.dict(os.environ, {"HOME": str(self.base / "flatpak-private-home")}):
            app = module.Fusion(data=self.base / "other-data", cache=self.base / "other-cache")
        expected = Path(module.pwd.getpwuid(os.getuid()).pw_dir) / ".autodesk_fusion"
        self.assertEqual(app.shared_models, expected)

    def test_existing_drive_h_mapping_is_not_overwritten(self):
        drive = self.app.prefix / "dosdevices/h:"
        drive.parent.mkdir(parents=True)
        drive.symlink_to(self.base / "different")
        with self.assertRaisesRegex(module.SetupError, "drive H: already exists"):
            self.app.configure_shared_drive()
        self.assertEqual(os.readlink(drive), str(self.base / "different"))

    def test_flatpak_uses_bundled_tools_and_does_not_set_host_mime_defaults(self):
        self.app.flatpak = True
        self.runtime()
        with patch.object(self.app, "download") as downloader, \
                patch.object(self.app, "run_logged") as runner:
            self.app.install_runtime()
            self.app.register_callback()
            downloader.assert_not_called()
            runner.assert_not_called()
        self.assertEqual(self.app.environment()["BROWSER"], "/app/bin/cad-wine-launcher-browser")

    def test_initial_boot_can_suppress_optional_download_dialogs(self):
        with patch.object(module.subprocess, "run") as runner:
            self.app.run_logged(["wine", "wineboot.exe", "--init"],
                                env_updates={"WINEDLLOVERRIDES": "mscoree,mshtml="})
        env = runner.call_args.kwargs["env"]
        self.assertEqual(env["WINEDLLOVERRIDES"], "mscoree,mshtml=")
        self.assertNotIn("mscoree,mshtml=", self.app.environment()["WINEDLLOVERRIDES"])

    def test_download_rejects_hash_mismatch_without_overwriting_cache(self):
        self.app.cache.mkdir()
        target = self.app.cache / "test"
        target.write_bytes(b"old")
        source = {"url": "https://example.invalid/file", "sha256": "0" * 64}
        def fake_curl(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(b"new")
        with patch.object(self.app, "run_logged", side_effect=fake_curl):
            with self.assertRaisesRegex(module.SetupError, "SHA-256 mismatch"):
                self.app.download(source, "test")
        self.assertEqual(target.read_bytes(), b"old")
        self.assertFalse((self.app.cache / "test.part").exists())

    def test_download_uses_validated_pinned_cache(self):
        self.app.cache.mkdir()
        target = self.app.cache / "test"
        target.write_bytes(b"content")
        source = {"url": "https://example.invalid/file", "sha256": hashlib.sha256(b"content").hexdigest()}
        with patch.object(self.app, "run_logged") as runner:
            self.assertEqual(self.app.download(source, "test"), target)
            runner.assert_not_called()

    def test_html_download_is_not_executed(self):
        self.app.cache.mkdir()
        def fake_curl(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(b"<html>failure</html>")
        with patch.object(self.app, "run_logged", side_effect=fake_curl):
            with self.assertRaisesRegex(module.SetupError, "not a Windows executable"):
                self.app.download({"url": "https://example.invalid/file"}, "test.exe", pe=True)
        self.assertEqual(list(self.app.cache.iterdir()), [])

    def test_user_selected_installer_must_be_a_windows_executable(self):
        bad = self.base / "installer.exe"
        bad.write_text("not an executable")
        with self.assertRaisesRegex(module.SetupError, "not a Windows executable"):
            self.app.select_installer(bad)

    def test_noninteractive_terms_require_explicit_confirmation(self):
        self.assertIn("does not download or\nredistribute the Autodesk installer", module.TERMS_NOTICE)
        self.assertIn("https://manage.autodesk.com/", module.TERMS_NOTICE)
        self.assertIn("Click OK only after", module.TERMS_NOTICE)
        with patch.dict(os.environ, {"DISPLAY": ""}, clear=False), \
                patch.object(module.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(module.SetupError, "Confirmation is required"):
                self.app.confirm_terms()
        self.app.confirm_terms(accepted=True)

    def test_graphical_warning_uses_ok_and_cancel_buttons(self):
        completed = subprocess.CompletedProcess([], 0)
        with patch.dict(os.environ, {"DISPLAY": ":99"}, clear=False), \
                patch.object(module.shutil, "which", return_value="/usr/bin/zenity"), \
                patch.object(module.subprocess, "run", return_value=completed) as runner:
            self.app.confirm_terms()
        command = runner.call_args.args[0]
        self.assertIn("--ok-label=OK", command)
        self.assertIn("--cancel-label=Cancel", command)
        self.assertIn(f"--text={module.TERMS_NOTICE}", command)

    def test_archive_rejects_traversal_and_escaping_symlinks(self):
        archive = self.base / "wine.tar.gz"
        for name, link in (("../escape", None), ("/escape", None),
                           ("other/file", None), ("fusion-wine-build/link", "/etc")):
            with tarfile.open(archive, "w:gz") as bundle:
                member = tarfile.TarInfo(name)
                if link:
                    member.type = tarfile.SYMTYPE
                    member.linkname = link
                bundle.addfile(member)
            with self.assertRaises((module.SetupError, tarfile.TarError)):
                module.extract_runtime(archive, self.base / "unpacked")

    def test_archive_accepts_expected_runtime(self):
        archive = self.base / "wine.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name in ("wine", "wineserver", "wineboot"):
                member = tarfile.TarInfo("fusion-wine-build/bin/" + name)
                member.mode = 0o755
                bundle.addfile(member)
        result = module.extract_runtime(archive, self.base / "unpacked")
        self.assertTrue(os.access(result / "bin/wine", os.X_OK))

    def test_setup_lock_prevents_concurrent_installation(self):
        self.app.data.mkdir()
        with (self.app.data / "setup.lock").open("w") as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(module.SetupError, "Another launcher setup"):
                with self.app.setup_session():
                    self.fail("The second installer acquired the lock")

    def test_automatic_setup_is_idempotent_and_update_is_explicit(self):
        self.runtime()
        selected = self.base / "selected-installer.exe"
        selected.write_bytes(b"MZtest")
        commands = []
        def fake_run(command, **kwargs):
            commands.append([str(arg) for arg in command])
            if "--globalinstall" in command:
                self.executable()
        def fake_download(source, filename, **kwargs):
            target = self.app.cache / filename
            target.write_bytes(b"MZtest")
            return target
        with patch.object(self.app, "install_runtime"), \
                patch.object(self.app, "run_logged", side_effect=fake_run), \
                patch.object(self.app, "download", side_effect=fake_download), \
                contextlib.redirect_stdout(io.StringIO()):
            self.app.install(installer=selected, terms_accepted=True)
            self.assertTrue(self.app.ready())
            initial_count = len(commands)
            self.app.install(installer=selected, terms_accepted=True)
            self.assertEqual(len(commands), initial_count)
            self.app.install(update=True, installer=selected, terms_accepted=True)
        installers = [cmd for cmd in commands if "--globalinstall" in cmd]
        self.assertTrue(any(cmd[1:] == ["wineboot.exe", "--init"] for cmd in commands))
        self.assertFalse(any(cmd[0].endswith("/wineboot") for cmd in commands))
        self.assertEqual(len(installers), 2)
        self.assertIn("--quiet", installers[0])
        self.assertEqual(installers[1][-2:], ["--process", "update"])
        self.assertEqual(installers[1].count("--process"), 1)

    def test_installer_failure_invalidates_previous_success(self):
        self.installed()
        selected = self.base / "selected-installer.exe"
        selected.write_bytes(b"MZtest")
        def fake_download(source, filename, **kwargs):
            target = self.app.cache / filename
            target.write_bytes(b"MZtest")
            return target
        def fake_run(command, **kwargs):
            if "--globalinstall" in command:
                raise module.SetupError("installer failed")
        with patch.object(self.app, "install_runtime"), \
                patch.object(self.app, "download", side_effect=fake_download), \
                patch.object(self.app, "run_logged", side_effect=fake_run), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(module.SetupError, "installer failed"):
                self.app.install(update=True, installer=selected, terms_accepted=True)
        self.assertFalse(self.app.marker.exists())
        self.assertEqual(selected.read_bytes(), b"MZtest")
        self.assertEqual(list(self.app.cache.glob("autodesk-installer-*.exe")), [])

    def test_callback_is_passed_as_one_argument_without_shell_or_logging(self):
        self.installed()
        self.executable("Autodesk Identity Manager/AdskIdentityManager.exe")
        callback = "adskidmgr:/callback?token=secret&other=$(do-not-execute)"
        with patch.object(module.subprocess, "call", return_value=0) as runner, \
                patch.object(self.app, "shutdown_wine") as shutdown:
            self.assertEqual(self.app.launch([], callback=callback), 0)
        command = runner.call_args.args[0]
        self.assertEqual(command[-1], callback)
        self.assertNotIn("shell", runner.call_args.kwargs)
        self.assertEqual(runner.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertIsNone(self.app.log_path)
        shutdown.assert_not_called()

    def test_main_launch_always_stops_private_wine_session(self):
        self.installed()
        with patch.object(module.subprocess, "call", return_value=7), \
                patch.object(self.app, "shutdown_wine") as shutdown:
            self.assertEqual(self.app.launch([]), 7)
        shutdown.assert_called_once_with(debug=False)

        with patch.object(module.subprocess, "call", side_effect=KeyboardInterrupt), \
                patch.object(self.app, "shutdown_wine") as shutdown:
            with self.assertRaises(KeyboardInterrupt):
                self.app.launch([], debug=True)
        shutdown.assert_called_once_with(debug=True)

    def test_wine_watchdog_escalates_when_graceful_shutdown_hangs(self):
        self.runtime()
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[-1] == "-w" and calls.count(command) == 1:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return subprocess.CompletedProcess(command, 0)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            self.app.shutdown_wine()
        options = [command[-1] for command in calls]
        self.assertEqual(options, ["-k", "-w", "-k9", "-w"])
        self.assertTrue(all(command[0].endswith("/wineserver") for command in calls))

    def test_bad_callback_is_rejected(self):
        self.installed()
        self.executable("AdskIdentityManager.exe")
        with patch.object(module.subprocess, "call") as runner:
            with self.assertRaisesRegex(module.SetupError, "Invalid Autodesk"):
                self.app.launch([], callback="https://example.invalid")
            runner.assert_not_called()

    def test_flatpak_permissions_do_not_expose_host_home(self):
        manifest = json.loads((ROOT / "flatpak/org.community.CADWineLauncher.json").read_text())
        permissions = manifest["finish-args"]
        self.assertIn("--allow=multiarch", permissions)
        self.assertIn("--filesystem=~/.autodesk_fusion:create", permissions)
        self.assertNotIn("--filesystem=home", permissions)
        self.assertNotIn("--filesystem=host", permissions)
        self.assertNotIn("--device=all", permissions)
        self.assertFalse(any("org.freedesktop.Flatpak" in item for item in permissions))

    def test_package_has_independent_identity_and_no_autodesk_installer_url(self):
        manifest_path = ROOT / "flatpak/org.community.CADWineLauncher.json"
        manifest = json.loads(manifest_path.read_text())
        sources = json.loads((ROOT / "packaging/sources.json").read_text())
        self.assertEqual(manifest["app-id"], "org.community.CADWineLauncher")
        self.assertEqual(manifest["command"], "cad-wine-launcher")
        self.assertEqual(module.APP_NAME, "Community CAD Launcher for Autodesk Fusion")
        self.assertNotIn("fusion", sources)
        package_text = "\n".join(path.read_text(errors="ignore") for path in (
            manifest_path, ROOT / "packaging/sources.json", ROOT / "packaging/fusion360.py"))
        self.assertNotIn("dl.appstreaming.autodesk.com", package_text)
        self.assertNotIn("Community CAD Wine Launcher", package_text)

    def test_project_is_gpl3_or_later(self):
        license_text = (ROOT / "LICENSE").read_text()
        metainfo = (ROOT / "flatpak/org.community.CADWineLauncher.metainfo.xml").read_text()
        copyright_text = (ROOT / "packaging/copyright").read_text()
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 3, 29 June 2007", license_text)
        self.assertIn("<project_license>GPL-3.0-or-later</project_license>", metainfo)
        self.assertIn("License: GPL-3+", copyright_text)

    def test_maintainer_metadata(self):
        maintainer = "Alexander Rykovanov <rykovanov.as@gmail.com>"
        control = (ROOT / "packaging/control").read_text()
        changelog = (ROOT / "packaging/changelog").read_text()
        copyright_text = (ROOT / "packaging/copyright").read_text()
        metainfo = (ROOT / "flatpak/org.community.CADWineLauncher.metainfo.xml").read_text()
        self.assertIn(f"Maintainer: {maintainer}", control)
        self.assertIn(f" -- {maintainer}", changelog)
        self.assertIn(f"Copyright: 2026 {maintainer}", copyright_text)
        self.assertIn("<name>Alexander Rykovanov</name>", metainfo)

    def test_release_version_and_artifact_names_are_consistent(self):
        version = "0.3.1"
        control = (ROOT / "packaging/control").read_text()
        changelog = (ROOT / "packaging/changelog").read_text()
        metainfo = (ROOT / "flatpak/org.community.CADWineLauncher.metainfo.xml").read_text()
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn(f"Version: {version}", control)
        self.assertTrue(changelog.startswith(f"cad-wine-launcher ({version})"))
        self.assertIn(f'<release version="{version}"', metainfo)
        self.assertIn("cad-wine-launcher_$(VERSION)_x86_64.flatpak", makefile)
        self.assertIn("cad-wine-launcher_$(VERSION)_amd64.deb", makefile)
        self.assertIn("cad-wine-launcher_$(VERSION)_sources.tar.gz", makefile)

    def test_version_bump_script_updates_current_references_and_preserves_history(self):
        fixture = self.base / "version-fixture"
        current = (ROOT / "packaging/control").read_text().split("Version: ", 1)[1].splitlines()[0]
        major, minor, patch_version = (int(part) for part in current.split("."))
        next_version = f"{major}.{minor}.{patch_version + 1}"
        files = {
            "README.md": f"bundle {current}\n",
            "packaging/README.md": f"release v{current} and bundle {current}\n",
            "packaging/control": (
                f"Package: cad-wine-launcher\nVersion: {current}\n"
                "Maintainer: Alexander Rykovanov <rykovanov.as@gmail.com>\n"
            ),
            "packaging/cad-wine-launcher.1": f"cad-wine-launcher {current}\n",
            "packaging/changelog": (
                f"cad-wine-launcher ({current}) unstable; urgency=medium\n"
            ),
            "source-offer/README.md": f"source {current}\n",
            "tests/test_packaging.py": f'version = "{current}"\n',
            ".github/workflows/release.yml": f"example v{current}\n",
            "flatpak/org.community.CADWineLauncher.metainfo.xml": (
                f"<releases>\n  <release version=\"{current}\" date=\"2026-10-31\"/>\n"
                "</releases>\n"
            ),
        }
        for name, contents in files.items():
            target = fixture / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)
        script = fixture / "scripts/bump-version.sh"
        script.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "scripts/bump-version.sh", script)

        result = subprocess.run(
            [script, next_version, "Fix Wine lifecycle cleanup."],
            cwd=fixture, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Version increased from {current} to {next_version}", result.stdout)
        for name in (
                "README.md", "packaging/README.md", "packaging/control",
                "packaging/cad-wine-launcher.1", "source-offer/README.md",
                "tests/test_packaging.py", ".github/workflows/release.yml"):
            text = (fixture / name).read_text()
            self.assertIn(next_version, text)
            self.assertNotIn(current, text)
        changelog = (fixture / "packaging/changelog").read_text()
        self.assertTrue(changelog.startswith(f"cad-wine-launcher ({next_version})"))
        self.assertIn("Fix Wine lifecycle cleanup.", changelog)
        self.assertIn(f"cad-wine-launcher ({current})", changelog)
        metainfo = (fixture / "flatpak/org.community.CADWineLauncher.metainfo.xml").read_text()
        self.assertIn(f'<release version="{next_version}"', metainfo)
        self.assertIn(f'<release version="{current}"', metainfo)

        control_before = (fixture / "packaging/control").read_text()
        invalid = subprocess.run([script, f"{major}.{minor}"], cwd=fixture,
                                 capture_output=True, text=True)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual((fixture / "packaging/control").read_text(), control_before)

    def test_readme_documents_manual_autodesk_download(self):
        for path in (ROOT / "README.md", ROOT / "packaging/README.md"):
            text = path.read_text()
            self.assertIn("Sign in to the [Autodesk Account]", text)
            self.assertIn("accept Autodesk's applicable user agreement", text)
            self.assertIn("select the downloaded installer", text)
            self.assertIn("does not", text)
            self.assertIn("automatically fetch the Fusion installer", text)
            self.assertIn("complete, preconfigured", text)
            self.assertIn("do not need to", text)
            self.assertIn("Wine manually", text)
            self.assertIn("flatpak install --user --reinstall", text)
            self.assertIn("flatpak run org.community.CADWineLauncher --update", text)

    def test_release_workflow_builds_and_publishes_on_github_runner(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertNotIn("self-hosted", workflow)
        self.assertIn("make clean", workflow)
        self.assertIn("make all", workflow)
        self.assertIn("sha256sum --check dist/SHA256SUMS", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("Push the default branch before", workflow)
        for artifact in (
                "cad-wine-launcher_${{ steps.release.outputs.version }}_x86_64.flatpak",
                "cad-wine-launcher_${{ steps.release.outputs.version }}_amd64.deb",
                "cad-wine-launcher_${{ steps.release.outputs.version }}_sources.tar.gz",
                "SHA256SUMS"):
            self.assertIn(artifact, workflow)


if __name__ == "__main__":
    unittest.main()
