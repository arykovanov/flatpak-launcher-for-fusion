#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unofficial per-user CAD Wine launcher; no Autodesk software is bundled."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import pwd
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time


class SetupError(Exception):
    pass


APP_NAME = "Community CAD Launcher for Autodesk Fusion"
TERMS_URL = "https://www.autodesk.com/company/terms-of-use/en/general-terms"
AUTODESK_ACCOUNT_URL = "https://manage.autodesk.com/"
TERMS_NOTICE = f"""{APP_NAME} is an unofficial community project and is not
affiliated with, endorsed by, or supported by Autodesk, Inc.

Before continuing, you must read and accept Autodesk's terms at:
{TERMS_URL}

You must also confirm that you have a valid entitlement to install and use
Autodesk Fusion. Autodesk Fusion remains subject to Autodesk's own terms.

For legal and licensing reasons, this launcher does not download or
redistribute the Autodesk installer. You must sign in to your Autodesk Account
and download the Fusion installer yourself:
{AUTODESK_ACCOUNT_URL}

Click OK only after you have downloaded the installer and are ready to select
that file. Otherwise, click Cancel."""


def xdg_path(variable, fallback):
    path = Path(os.environ.get(variable) or fallback)
    if not path.is_absolute():
        raise SetupError(f"{variable} must be an absolute path.")
    return path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_windows_installer(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise SetupError(f"Installer not found: {path}")
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise SetupError("The selected file is not a Windows executable.")
    return path


def extract_runtime(archive, destination):
    """Extract only the expected tree; reject escaping paths and links."""
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts
                    or not path.parts or path.parts[0] != "fusion-wine-build"):
                raise SetupError(f"Unexpected path in Wine archive: {member.name}")
        bundle.extractall(destination, members=members, filter="data")
    runtime = destination / "fusion-wine-build"
    for name in ("wine", "wineserver", "wineboot"):
        if not os.access(runtime / "bin" / name, os.X_OK):
            raise SetupError(f"Wine archive is missing bin/{name}.")
    return runtime


class Fusion:
    def __init__(self, data=None, cache=None, sources=None, shared=None):
        self.data = data or xdg_path("XDG_DATA_HOME", Path.home() / ".local/share") / "cad-wine-launcher"
        self.cache = cache or xdg_path("XDG_CACHE_HOME", Path.home() / ".cache") / "cad-wine-launcher"
        self.sources = sources or json.loads(Path(__file__).resolve().with_name("sources.json").read_text())
        self.flatpak = Path("/.flatpak-info").is_file()
        self.prefix = self.data / "prefix"
        # Flatpak changes $HOME to its private application directory, while
        # the passwd entry retains the user's real host home directory.
        host_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        self.shared_models = shared or host_home / ".autodesk_fusion"
        self.runtime = self.data / "runtimes" / self.sources["wine"]["version"] / "fusion-wine-build"
        if self.flatpak:
            self.runtime = Path("/app/opt/fusion-wine-build")
        self.marker = self.data / "installed.json"
        self.log = None
        self.log_path = None
        self.progress_dialog = None

    def progress(self, message):
        print(message, flush=True)
        if self.progress_dialog and self.progress_dialog.poll() is None:
            try:
                self.progress_dialog.stdin.write(f"# {message}\n")
                self.progress_dialog.stdin.flush()
            except BrokenPipeError:
                pass

    def environment(self, debug=False):
        env = os.environ.copy()
        env.update({
            "WINEPREFIX": str(self.prefix), "WINEARCH": "win64",
            "WINE": str(self.runtime / "bin/wine"),
            "WINELOADER": str(self.runtime / "bin/wine"),
            "WINESERVER": str(self.runtime / "bin/wineserver"),
            "PATH": str(self.runtime / "bin") + os.pathsep + env.get("PATH", "/usr/bin:/bin"),
            "WINETRICKS_LATEST_VERSION_CHECK": "disabled",
            "W_CACHE": str(self.cache / "winetricks-cache"),
            "WINEDEBUG": "-all,err+all,warn+all,+seh" if debug else "-all",
            "DXVK_LOG_LEVEL": "info" if debug else "none",
            "WINEDLLOVERRIDES": "winemenubuilder.exe=d;bcp47langs=;icuuc,icuin,icudt=n,b",
        })
        # Host Wine overrides must not silently switch this package to another runtime.
        for variable in ("WINEDLLPATH", "WINELOADERNOEXEC", "WINESERVERSOCKET"):
            env.pop(variable, None)
        if self.flatpak:
            env["BROWSER"] = "/app/bin/cad-wine-launcher-browser"
        return env

    def find_executable(self, name):
        roots = [self.prefix / "drive_c/Program Files/Autodesk/webdeploy/production"]
        users = self.prefix / "drive_c/users"
        if users.is_dir():
            roots.extend(users.glob("*/AppData/Local/Autodesk/webdeploy/production"))
        matches = [path for root in roots if root.is_dir()
                   for path in root.rglob(name) if path.is_file()]
        return max(matches, key=lambda path: (path.stat().st_mtime_ns, str(path)), default=None)

    def configure_shared_drive(self):
        """Expose only the dedicated host exchange folder as Wine drive H:."""
        self.shared_models.mkdir(parents=True, exist_ok=True, mode=0o700)
        dosdevices = self.prefix / "dosdevices"
        dosdevices.mkdir(parents=True, exist_ok=True)
        drive = dosdevices / "h:"
        if os.path.lexists(drive):
            if drive.is_symlink() and drive.resolve() == self.shared_models.resolve():
                return
            raise SetupError(f"Wine drive H: already exists with another target: {drive}")
        drive.symlink_to(self.shared_models, target_is_directory=True)

    def ready(self):
        try:
            state = json.loads(self.marker.read_text())
        except (OSError, ValueError):
            return False
        return (isinstance(state, dict)
                and state.get("wine_version") == self.sources["wine"]["version"]
                and os.access(self.runtime / "bin/wine", os.X_OK)
                and os.access(self.runtime / "bin/wineserver", os.X_OK)
                and self.find_executable("Fusion360.exe") is not None)

    @contextlib.contextmanager
    def setup_session(self):
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.data / "setup.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise SetupError("Another launcher setup is running. Wait for it to finish.") from error
            self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
            logs = self.data / "logs"
            logs.mkdir(exist_ok=True, mode=0o700)
            fd, filename = tempfile.mkstemp(prefix="setup-", suffix=".log", dir=logs)
            self.log_path = Path(filename)
            with os.fdopen(fd, "w") as self.log:
                print(f"Setup log: {self.log_path}", flush=True)
                try:
                    yield
                finally:
                    if self.progress_dialog:
                        try:
                            self.progress_dialog.stdin.close()
                        except BrokenPipeError:
                            pass
                        self.progress_dialog.wait(timeout=15)
                        self.progress_dialog = None

    def start_progress_dialog(self):
        if self.flatpak and not sys.stdout.isatty() and shutil.which("zenity"):
            self.progress_dialog = subprocess.Popen([
                "zenity", "--progress", "--pulsate", "--auto-close", "--no-cancel",
                f"--title={APP_NAME}", "--text=Preparing installation…",
            ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, text=True)

    def run_logged(self, command, timeout=3600, env_updates=None):
        environment = self.environment()
        environment.update(env_updates or {})
        try:
            subprocess.run([str(arg) for arg in command], check=True, env=environment,
                           stdout=self.log, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise SetupError("A setup step timed out. Its Wine child processes may still be running; "
                             "close them before retrying.") from error
        except subprocess.CalledProcessError as error:
            raise SetupError(f"Setup step failed (exit {error.returncode}): {Path(command[0]).name}") from error

    def download(self, source, filename, fresh=False, pe=False):
        target = self.cache / filename
        expected = source.get("sha256")
        if target.is_file() and expected and not fresh and digest(target) == expected:
            return target
        # Unpinned Autodesk and Microsoft bootstrappers are always fetched anew.
        part = target.with_suffix(target.suffix + ".part")
        try:
            self.run_logged([
                "curl", "--fail", "--location", "--show-error", "--silent",
                "--proto", "=https", "--proto-redir", "=https", "--retry", "3",
                "--connect-timeout", "20", "--max-time", "1800",
                "--output", part, source["url"],
            ], timeout=1900)
            if not part.is_file() or not part.stat().st_size:
                raise SetupError(f"Empty download: {filename}")
            if expected and digest(part) != expected:
                raise SetupError(f"SHA-256 mismatch for {filename}; the download was rejected.")
            if pe:
                with part.open("rb") as stream:
                    if stream.read(2) != b"MZ":
                        raise SetupError(f"The download is not a Windows executable: {filename}")
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
        return target

    def confirm_terms(self, accepted=False):
        """Require an affirmative terms/entitlement confirmation."""
        if accepted:
            return
        if os.environ.get("DISPLAY") and shutil.which("zenity"):
            result = subprocess.run([
                "zenity", "--question", f"--title={APP_NAME}", "--width=620",
                "--ok-label=OK", "--cancel-label=Cancel",
                f"--text={TERMS_NOTICE}",
            ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                return
            raise SetupError("Autodesk terms and entitlement were not confirmed.")
        if sys.stdin.isatty():
            print(TERMS_NOTICE)
            answer = input("\nType ACCEPT to accept the terms and confirm your entitlement: ")
            if answer.strip() == "ACCEPT":
                return
            raise SetupError("Autodesk terms and entitlement were not confirmed.")
        raise SetupError("Confirmation is required. Re-run interactively or pass "
                         "--accept-autodesk-terms after reviewing the terms.")

    def select_installer(self, installer=None):
        """Select a user-obtained Autodesk installer without downloading it."""
        if installer:
            return validate_windows_installer(installer)
        if os.environ.get("DISPLAY") and shutil.which("zenity"):
            result = subprocess.run([
                "zenity", "--file-selection", f"--title={APP_NAME}: select Autodesk installer",
                "--file-filter=Windows executables | *.exe", "--file-filter=All files | *",
            ], check=False, capture_output=True, text=True)
            if result.returncode != 0 or not result.stdout.strip():
                raise SetupError("No Autodesk installer was selected.")
            return validate_windows_installer(result.stdout.strip())
        if sys.stdin.isatty():
            selected = input("Path to an Autodesk Fusion installer downloaded by you: ").strip()
            return validate_windows_installer(selected)
        raise SetupError("An Autodesk installer is required. Pass --installer PATH.")

    def install_runtime(self):
        if self.flatpak:
            if not all(os.access(self.runtime / "bin" / name, os.X_OK)
                       for name in ("wine", "wineserver", "wineboot")):
                raise SetupError("The Flatpak Wine runtime is missing. Reinstall the Flatpak.")
            return
        version_dir = self.runtime.parent
        stamp = version_dir / "sha256"
        expected = self.sources["wine"]["sha256"]
        if stamp.is_file() and stamp.read_text().strip() == expected:
            if all(os.access(self.runtime / "bin" / name, os.X_OK)
                   for name in ("wine", "wineserver", "wineboot")):
                return
        if version_dir.exists():
            raise SetupError(f"The runtime is incomplete: {version_dir}. Move this directory aside and retry.")
        self.progress("Downloading the pinned Wine runtime (about 545 MiB)…")
        archive = self.download(self.sources["wine"], "wine.tar.gz")
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="extract-", dir=version_dir.parent) as staging:
            staging = Path(staging)
            extract_runtime(archive, staging)
            (staging / "sha256").write_text(expected + "\n")
            staging.rename(version_dir)

    def register_callback(self):
        if self.flatpak:
            # Flatpak exports the callback desktop entry to the host. Default-handler
            # Protocol registration belongs to the host installation step.
            return
        # Only called after successful setup, with this user's desktop environment.
        self.run_logged(["xdg-mime", "default", "cad-wine-launcher-callback.desktop",
                         "x-scheme-handler/adskidmgr"], timeout=30)

    def shutdown_wine(self, debug=False):
        """Stop every Wine process in this launcher's private prefix."""
        wineserver = self.runtime / "bin/wineserver"
        environment = self.environment(debug=debug)
        output = {} if debug else {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }

        def server(option, timeout):
            return subprocess.run([str(wineserver), option], check=False,
                                  env=environment, timeout=timeout, **output)

        try:
            # Fusion can leave WebView2/Edge updater and Windows service processes
            # behind. Ask their shared Wine server to terminate the entire prefix.
            server("-k", 10)
            server("-w", 15)
        except subprocess.TimeoutExpired:
            try:
                # The main Fusion process has already exited. If a helper ignores
                # graceful shutdown, do not leave the Flatpak instance wedged.
                server("-k9", 5)
                server("-w", 5)
            except (OSError, subprocess.TimeoutExpired) as error:
                print(f"Warning: Wine processes did not stop: {error}", file=sys.stderr)
        except OSError as error:
            # Cleanup failure must not replace Fusion's own exit status.
            print(f"Warning: Wine cleanup failed: {error}", file=sys.stderr)

    def install(self, update=False, installer=None, terms_accepted=False):
        with self.setup_session():
            if self.ready() and not update:
                print("Fusion is already installed. Use cad-wine-launcher --update to update it.")
                return
            self.confirm_terms(terms_accepted)
            selected_installer = self.select_installer(installer)
            self.start_progress_dialog()
            self.install_runtime()
            self.prefix.mkdir(exist_ok=True)
            wine = self.runtime / "bin/wine"
            dependencies = self.data / "dependencies.json"
            dependency_id = {"wine": self.sources["wine"]["sha256"],
                             "winetricks": self.sources["winetricks"]["sha256"], "recipe": 1}
            try:
                configured = json.loads(dependencies.read_text()) == dependency_id
            except (OSError, ValueError):
                configured = False
            if not configured:
                self.progress("Preparing the Wine prefix and Windows prerequisites…")
                if self.flatpak:
                    tricks = Path("/app/bin/winetricks")
                else:
                    tricks = self.download(self.sources["winetricks"], "winetricks")
                    tricks.chmod(0o700)
                # The pinned archive's wineboot shell wrapper prompts about a newer
                # project and can kill its parent. Invoke Wine's Windows boot program
                # directly so unattended setup never executes that shell wrapper.
                boot_overrides = self.environment()["WINEDLLOVERRIDES"] + ";mscoree,mshtml="
                self.run_logged([wine, "wineboot.exe", "--init"],
                                env_updates={"WINEDLLOVERRIDES": boot_overrides})
                self.run_logged([self.runtime / "bin/wineserver", "-w"])
                self.run_logged(["bash", tricks, "-q", "atmlib", "gdiplus", "corefonts",
                                 "dotnet48", "msxml4", "msxml6", "vcrun2022", "winhttp", "win11"])
                self.run_logged([wine, "reg", "add", r"HKCU\Software\Wine\X11 Driver",
                                 "/v", "Managed", "/t", "REG_SZ", "/d", "Y", "/f"])
                webview = self.download(self.sources["webview2"], "webview2.exe", pe=True)
                self.run_logged([wine, webview, "/silent", "/install"])
                # WebView2 is proprietary. Keep no package-managed installer copy
                # after a successful prerequisite installation.
                webview.unlink(missing_ok=True)
                dependencies.write_text(json.dumps(dependency_id) + "\n")
            self.configure_shared_drive()
            # Invalidate success before updating; an interrupted update must be retried.
            self.marker.unlink(missing_ok=True)
            self.progress("Installing Autodesk Fusion from the user-selected installer…")
            fd, staged_name = tempfile.mkstemp(prefix="autodesk-installer-", suffix=".exe", dir=self.cache)
            os.close(fd)
            staged_installer = Path(staged_name)
            try:
                shutil.copyfile(selected_installer, staged_installer)
                command = [wine, staged_installer, "--globalinstall", "--quiet"]
                if update:
                    command.extend(["--process", "update"])
                self.run_logged(command)
            finally:
                # Never retain a package-managed copy of Autodesk's proprietary installer.
                staged_installer.unlink(missing_ok=True)
            # The downloader can return before its worker publishes the application.
            deadline = time.monotonic() + 120
            while self.find_executable("Fusion360.exe") is None:
                if time.monotonic() >= deadline:
                    raise SetupError("The installer exited without producing Fusion360.exe.")
                time.sleep(2)
            self.register_callback()
            self.marker.write_text(json.dumps({"wine_version": self.sources["wine"]["version"]}) + "\n")
            print("Fusion installation files are present. Sign in with your Autodesk account on launch.")

    def launch(self, arguments, debug=False, callback=None):
        if not self.ready():
            if callback:
                raise SetupError("Fusion setup is incomplete. Run cad-wine-launcher --install first.")
            self.install()
        self.configure_shared_drive()
        executable = self.find_executable("AdskIdentityManager.exe" if callback else "Fusion360.exe")
        if executable is None:
            raise SetupError("The Autodesk Identity Manager executable was not found.")
        if callback:
            if not callback.lower().startswith("adskidmgr:") or any(c in callback for c in "\r\n\0"):
                raise SetupError("Invalid Autodesk sign-in callback URL.")
            arguments = [callback]
        command = [str(self.runtime / "bin/wine"), str(executable), *arguments]
        # Never put callback URLs in logs: they may contain authorization tokens.
        if callback:
            return subprocess.call(command, cwd=executable.parent, env=self.environment(),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if debug:
                return subprocess.call(command, cwd=executable.parent,
                                       env=self.environment(debug=True))
            return subprocess.call(command, cwd=executable.parent, env=self.environment(),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            # This launcher supervises the complete private Wine session. Fusion's
            # main process can exit while WebView2 and service helpers remain alive.
            self.shutdown_wine(debug=debug)


def main(argv=None):
    parser = argparse.ArgumentParser(description=f"{APP_NAME}: unofficial launcher for Autodesk Fusion.")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--install", action="store_true", help="install from an Autodesk installer selected by the user")
    operation.add_argument("--update", action="store_true", help="update from an Autodesk installer selected by the user")
    operation.add_argument("--status", action="store_true", help="show installation status without making changes")
    operation.add_argument("--dry-run", action="store_true", help="show sources and paths without downloads or changes")
    operation.add_argument("--callback", metavar="URL", help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", help="show Fusion and Wine diagnostics")
    parser.add_argument("--installer", metavar="PATH", help="installer obtained directly by the user from Autodesk")
    parser.add_argument("--accept-autodesk-terms", action="store_true",
                        help="confirm Autodesk terms and a valid entitlement non-interactively")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Fusion arguments, after --")
    args = parser.parse_args(argv)
    app = None
    try:
        app = Fusion()
        if args.status:
            print("Installed" if app.ready() else "Not installed or setup incomplete")
            print(f"Data: {app.data}\nCache: {app.cache}\nH: shared folder: {app.shared_models}")
            return 0 if app.ready() else 1
        if args.dry_run:
            print(json.dumps({"data": str(app.data), "cache": str(app.cache),
                              "runtime": str(app.runtime),
                              "shared_drive": {"H:": str(app.shared_models)},
                              "sources": app.sources}, indent=2))
            return 0
        if os.geteuid() == 0:
            raise SetupError("Run cad-wine-launcher as your desktop user, without sudo.")
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            raise SetupError("This package requires x86-64 Linux.")
        if not os.environ.get("DISPLAY"):
            raise SetupError("Run in a graphical session with X11 or XWayland (DISPLAY must be set).")
        os.umask(0o077)
        if args.install or args.update:
            app.install(update=args.update, installer=args.installer,
                        terms_accepted=args.accept_autodesk_terms)
            return 0
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        return app.launch(arguments, debug=args.debug, callback=args.callback)
    except (SetupError, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        if app and app.log_path:
            print(f"Details: {app.log_path}", file=sys.stderr)
        if app and app.flatpak and not sys.stderr.isatty() and shutil.which("zenity"):
            details = f"\n\nDetails: {app.log_path}" if app.log_path else ""
            subprocess.run(["zenity", "--error", f"--title={APP_NAME}", f"--text={error}{details}"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 1
    except KeyboardInterrupt:
        print("Setup interrupted. Downloaded files and prefix were retained for retry.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
