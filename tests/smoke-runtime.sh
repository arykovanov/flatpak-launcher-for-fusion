#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run INSIDE the Flatpak with networking disabled and a disposable X display.
set -euo pipefail
export WINEPREFIX
WINEPREFIX=$(mktemp -d /tmp/cad-wine-launcher-smoke.XXXXXXXX)
export WINEARCH=win64 WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
export WINESERVER=/app/opt/fusion-wine-build/bin/wineserver
wine=/app/opt/fusion-wine-build/bin/wine
trap '"$WINESERVER" -k >/dev/null 2>&1 || true; rm -rf -- "$WINEPREFIX"' EXIT
cad-wine-launcher --dry-run
"$wine" --version
cabextract --version
7zz i >/dev/null
"$wine" wineboot.exe --init
"$WINESERVER" -w
"$wine" cmd.exe /c ver
"$wine" 'C:\windows\syswow64\cmd.exe' /c ver
"$wine" reg.exe add 'HKCU\Software\CADWineLauncherPackageTest' /v Working /t REG_SZ /d yes /f
"$wine" reg.exe query 'HKCU\Software\CADWineLauncherPackageTest' /v Working
printf 'Wine prefix initialization, Windows execution and registry checks passed.\n'
