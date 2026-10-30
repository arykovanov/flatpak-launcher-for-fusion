#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build only our downloader and integration files; never bundle Autodesk assets.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (( $# > 1 )); then
    printf 'Usage: %s [OUTPUT_DIRECTORY]\n' "$0" >&2
    exit 2
fi
output=${1:-"$root/dist"}
mkdir -p -- "$output"
output=$(cd -- "$output" && pwd)
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
install -d "$stage/DEBIAN" "$stage/usr/bin" "$stage/usr/lib/cad-wine-launcher" \
    "$stage/usr/share/applications" "$stage/usr/share/doc/cad-wine-launcher" \
    "$stage/usr/share/icons/hicolor/scalable/apps" "$stage/usr/share/man/man1"
install -m644 "$root/packaging/control" "$stage/DEBIAN/control"
install -m755 "$root/packaging/fusion360.py" "$stage/usr/lib/cad-wine-launcher/launcher.py"
install -m644 "$root/packaging/sources.json" "$stage/usr/lib/cad-wine-launcher/sources.json"
ln -s ../lib/cad-wine-launcher/launcher.py "$stage/usr/bin/cad-wine-launcher"
install -m644 "$root/packaging/"*.desktop "$stage/usr/share/applications/"
install -m644 "$root/flatpak/org.community.CADWineLauncher.svg" \
    "$stage/usr/share/icons/hicolor/scalable/apps/cad-wine-launcher.svg"
install -m644 "$root/packaging/README.md" "$stage/usr/share/doc/cad-wine-launcher/README.md"
install -m644 "$root/packaging/copyright" "$stage/usr/share/doc/cad-wine-launcher/copyright"
install -m644 "$root/LICENSE" "$stage/usr/share/doc/cad-wine-launcher/LICENSE"
gzip -n -9 -c "$root/packaging/changelog" > "$stage/usr/share/doc/cad-wine-launcher/changelog.gz"
gzip -n -9 -c "$root/packaging/cad-wine-launcher.1" > "$stage/usr/share/man/man1/cad-wine-launcher.1.gz"
chmod -R u=rwX,go=rX "$stage"
size=$(du -sk "$stage/usr" | cut -f1)
printf 'Installed-Size: %s\n' "$size" >> "$stage/DEBIAN/control"
dpkg-deb --build --root-owner-group "$stage" "$output/cad-wine-launcher_0.2.0_amd64.deb"
