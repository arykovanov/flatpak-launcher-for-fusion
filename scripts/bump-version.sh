#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/bump-version.sh VERSION [CHANGELOG_MESSAGE]

Increase the project version everywhere release artifacts mention it. VERSION
must be a greater semantic version in MAJOR.MINOR.PATCH form. The script adds
new changelog and AppStream release entries while preserving release history.

Example:
  scripts/bump-version.sh 0.3.1 "Stop leftover Wine processes after Fusion exits."
EOF
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

version_is_greater() {
    local old_version=$1 new_version=$2 index old_part new_part
    local -a old_parts new_parts
    IFS=. read -r -a old_parts <<<"$old_version"
    IFS=. read -r -a new_parts <<<"$new_version"
    for index in 0 1 2; do
        old_part=$((10#${old_parts[$index]}))
        new_part=$((10#${new_parts[$index]}))
        if ((new_part > old_part)); then
            return 0
        fi
        if ((new_part < old_part)); then
            return 1
        fi
    done
    return 1
}

if (($# < 1 || $# > 2)); then
    usage >&2
    exit 2
fi

new_version=$1
message=${2:-"Prepare release ${new_version}."}
semver='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
[[ $new_version =~ $semver ]] || die "version must use MAJOR.MINOR.PATCH without leading zeroes"
[[ $message != *$'\n'* && -n $message ]] || die "changelog message must be one non-empty line"

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$script_dir/.." && pwd)
cd -- "$root"

control=packaging/control
[[ -f $control ]] || die "run this script from a complete source tree"
current_version=$(sed -n 's/^Version: //p' "$control")
[[ $current_version =~ $semver ]] || die "invalid current version in $control: $current_version"
version_is_greater "$current_version" "$new_version" \
    || die "new version $new_version must be greater than $current_version"

replace_files=(
    README.md
    packaging/README.md
    packaging/control
    packaging/cad-wine-launcher.1
    source-offer/README.md
    tests/test_packaging.py
    .github/workflows/release.yml
)

for file in "${replace_files[@]}" packaging/changelog \
        flatpak/org.community.CADWineLauncher.metainfo.xml; do
    [[ -f $file ]] || die "required file is missing: $file"
done
for file in "${replace_files[@]}"; do
    grep -Fq -- "$current_version" "$file" \
        || die "$file does not contain current version $current_version"
done
grep -Fxq -- "Version: $current_version" "$control" \
    || die "$control does not contain exactly formatted current version"

changelog=packaging/changelog
metainfo=flatpak/org.community.CADWineLauncher.metainfo.xml
first_changelog_line=$(sed -n '1p' "$changelog")
[[ $first_changelog_line == "cad-wine-launcher ($current_version) unstable; urgency=medium" ]] \
    || die "$changelog does not start with current version $current_version"
grep -Fq -- "<release version=\"$current_version\"" "$metainfo" \
    || die "$metainfo does not contain current version $current_version"
grep -Fq -- "cad-wine-launcher ($new_version)" "$changelog" \
    && die "changelog already contains version $new_version"
grep -Fq -- "<release version=\"$new_version\"" "$metainfo" \
    && die "AppStream metadata already contains version $new_version"
[[ $(grep -c '^[[:space:]]*<releases>[[:space:]]*$' "$metainfo") -eq 1 ]] \
    || die "$metainfo must contain exactly one <releases> opening element"

maintainer=$(sed -n 's/^Maintainer: //p' "$control")
[[ -n $maintainer ]] || die "Maintainer is missing from $control"
release_date=$(date +%F)
changelog_date=$(LC_ALL=C date -R)

old_pattern=${current_version//./\\.}
for file in "${replace_files[@]}"; do
    sed -i "s/${old_pattern}/${new_version}/g" "$file"
done

sed -i "/^[[:space:]]*<releases>[[:space:]]*$/a\\    <release version=\"$new_version\" date=\"$release_date\"/>" \
    "$metainfo"

temporary=$(mktemp "${changelog}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
{
    printf 'cad-wine-launcher (%s) unstable; urgency=medium\n\n' "$new_version"
    printf '  * %s\n\n' "$message"
    printf ' -- %s  %s\n\n' "$maintainer" "$changelog_date"
    cat -- "$changelog"
} >"$temporary"
chmod --reference="$changelog" "$temporary"
mv -f -- "$temporary" "$changelog"
trap - EXIT

printf 'Version increased from %s to %s.\n' "$current_version" "$new_version"
printf 'Review the changelog, run make test, commit, push main, then tag v%s.\n' "$new_version"
