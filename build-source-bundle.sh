#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (( $# > 1 )); then
    printf 'Usage: %s [OUTPUT_DIRECTORY]\n' "$0" >&2
    exit 2
fi
output=${1:-"$root/dist"}
mkdir -p -- "$output" "$root/build/source-downloads"
output=$(cd -- "$output" && pwd)
version=$(sed -n 's/^Version: //p' "$root/packaging/control")
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    printf 'Invalid package version: %s\n' "$version" >&2
    exit 1
}
downloads="$root/build/source-downloads"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT

fetch() {
    local name=$1 url=$2 expected=$3 target="$downloads/$1"
    if [[ ! -f $target ]] || ! printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status; then
        curl --fail --location --show-error --retry 3 --output "$target.part" "$url"
        printf '%s  %s\n' "$expected" "$target.part" | sha256sum --check --status || {
            rm -f -- "$target.part"
            printf 'SHA-256 mismatch: %s\n' "$name" >&2
            exit 1
        }
        mv -- "$target.part" "$target"
    fi
    cp -- "$target" "$stage/$name"
}

fetch wine-11.10.tar.xz \
    https://dl.winehq.org/wine/source/11.x/wine-11.10.tar.xz \
    e4c35ebe26f4f8eef5f2143e24a1fb9fd103f1d46132ad4755479227d086b8e7
fetch 7zip-b88c6bc09339de32f7d18bbab900686b244f42ba.tar.gz \
    https://github.com/ip7z/7zip/archive/b88c6bc09339de32f7d18bbab900686b244f42ba.tar.gz \
    d06cf3c4b4cb085f9a9a5c385b80e46d9ab47849860a4e2c00e1882409c7f830
fetch cabextract-1.11.tar.gz \
    https://deb.debian.org/debian/pool/main/c/cabextract/cabextract_1.11.orig.tar.gz \
    b5546db1155e4c718ff3d4b278573604f30dd64c3c5bfd4657cd089b823a3ac6
fetch winetricks-f3890f670867b5ffbc3938726db45c0f7d16c8ba \
    https://raw.githubusercontent.com/Winetricks/winetricks/f3890f670867b5ffbc3938726db45c0f7d16c8ba/src/winetricks \
    672a1ff4442e8691a3ffc0e6860137e201a1d1227e9b3044245f1731e9e9837e

install -Dm644 "$root/source-offer/README.md" "$stage/README.md"
install -Dm644 "$root/LICENSE" "$stage/launcher/LICENSE"
install -Dm644 "$root/source-offer/wine-captionless-popups.patch" "$stage/wine-captionless-popups.patch"
install -Dm755 "$root/packaging/fusion360.py" "$stage/launcher/launcher.py"
install -Dm644 "$root/packaging/sources.json" "$stage/launcher/sources.json"
install -Dm644 "$root/packaging/copyright" "$stage/launcher/copyright"
install -Dm644 "$root/packaging/control" "$stage/launcher/debian/control"
install -Dm644 "$root/packaging/changelog" "$stage/launcher/debian/changelog"
install -Dm644 "$root/packaging/README.md" "$stage/launcher/debian/README.md"
install -Dm644 "$root/packaging/cad-wine-launcher.1" "$stage/launcher/debian/cad-wine-launcher.1"
install -Dm644 "$root/packaging/cad-wine-launcher.desktop" "$stage/launcher/debian/cad-wine-launcher.desktop"
install -Dm644 "$root/packaging/cad-wine-launcher-callback.desktop" "$stage/launcher/debian/cad-wine-launcher-callback.desktop"
install -Dm644 "$root/Makefile" "$stage/launcher/Makefile"
install -Dm755 "$root/build-flatpak.sh" "$stage/launcher/build-flatpak.sh"
install -Dm755 "$root/build-deb.sh" "$stage/launcher/build-deb.sh"
install -Dm755 "$root/build-source-bundle.sh" "$stage/launcher/build-source-bundle.sh"
install -Dm644 "$root/flatpak/org.community.CADWineLauncher.json" "$stage/launcher/flatpak-manifest.json"
install -Dm755 "$root/flatpak/cad-wine-launcher-browser" "$stage/launcher/cad-wine-launcher-browser"
install -Dm644 "$root/flatpak/org.community.CADWineLauncher.desktop" "$stage/launcher/org.community.CADWineLauncher.desktop"
install -Dm644 "$root/flatpak/org.community.CADWineLauncher.Callback.desktop" "$stage/launcher/org.community.CADWineLauncher.Callback.desktop"
install -Dm644 "$root/flatpak/org.community.CADWineLauncher.metainfo.xml" "$stage/launcher/org.community.CADWineLauncher.metainfo.xml"
install -Dm644 "$root/flatpak/org.community.CADWineLauncher.svg" "$stage/launcher/org.community.CADWineLauncher.svg"
cp -a -- "$root/flatpak/licenses" "$stage/launcher/licenses"

archive="$output/cad-wine-launcher_${version}_sources.tar.gz"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
    -czf "$archive" -C "$stage" .
printf 'Built %s\n' "$archive"
