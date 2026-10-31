#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
builder=${FLATPAK_BUILDER:-flatpak-builder}
command -v "$builder" >/dev/null || {
    printf 'Install flatpak-builder first (Debian/Ubuntu: sudo apt install flatpak-builder).\n' >&2
    exit 1
}
if (( $# > 1 )); then
    printf 'Usage: %s [OUTPUT_DIRECTORY]\n' "$0" >&2
    exit 2
fi
output=${1:-"$root/dist"}
mkdir -p -- "$output" "$root/build/flatpak-state"
output=$(cd -- "$output" && pwd)
version=$(sed -n 's/^Version: //p' "$root/packaging/control")
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    printf 'Invalid package version: %s\n' "$version" >&2
    exit 1
}
# Build and export locally. Installation is a separate command.
"$builder" --force-clean --arch=x86_64 --state-dir="$root/build/flatpak-state" \
    --repo="$root/build/flatpak-repo" "$root/build/flatpak-app" \
    "$root/flatpak/org.community.CADWineLauncher.json"
printf 'Creating the single-file bundle; compressing the Wine runtime can take several minutes.\n'
bundle="$output/cad-wine-launcher_${version}_x86_64.flatpak"
temporary_bundle="$output/.cad-wine-launcher_${version}_x86_64.flatpak.tmp"
rm -f -- "$temporary_bundle"
trap 'rm -f -- "$temporary_bundle"' EXIT
flatpak build-bundle --arch=x86_64 --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
    "$root/build/flatpak-repo" "$temporary_bundle" org.community.CADWineLauncher
mv -- "$temporary_bundle" "$bundle"
trap - EXIT
printf 'Built %s\n' "$bundle"
