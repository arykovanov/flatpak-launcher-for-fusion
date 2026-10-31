# Community CAD Launcher for Autodesk Fusion packages

Community CAD Launcher is an independent, unofficial launcher for use
with Autodesk Fusion. It is not affiliated with, endorsed by, or supported by
Autodesk, Inc. “Autodesk Fusion” is used only to identify the software with
which the launcher interoperates. The package uses an original community cube
icon, not an Autodesk logo or product icon.

Autodesk and Autodesk Fusion are trademarks of the Autodesk group of
companies. Community CAD Launcher is not affiliated with Autodesk.

These packages are intended for private, local use and are not prepared for
publication in Flathub or a Debian archive. Autodesk Fusion is proprietary and
is **not included, redistributed, or downloaded by either package**. You must
obtain an installer directly from Autodesk, review and accept Autodesk's
[General Terms](https://www.autodesk.com/company/terms-of-use/en/general-terms),
and have a valid entitlement. Compatibility is experimental and Linux is not
an Autodesk-supported Fusion platform.

The launcher, packaging code, and original artwork are GPL-3.0-or-later.
Bundled third-party components retain their respective licenses.

## Why the Fusion installer must be downloaded manually

This package cannot provide a completely unattended, one-click Fusion
installation. Before the launcher can install Fusion, you must:

1. Sign in to the [Autodesk Account](https://manage.autodesk.com/) associated
   with your Fusion entitlement.
2. Review and accept Autodesk's applicable user agreement and download terms.
3. Find Fusion under Products and Services and download its Windows installer.
4. Run this launcher and select the downloaded installer in the file chooser.

The extra steps are inconvenient, but they are a deliberate licensing
boundary. Autodesk Fusion is proprietary software, and Autodesk controls
installer access through its account, entitlement, and terms-acceptance flow.
This independent GPL-licensed project cannot accept those terms or establish
an entitlement for you. It therefore does not bundle, redistribute, mirror, or
automatically fetch the Fusion installer. Automating that acquisition would
bypass the user-facing Autodesk flow and could retrieve or redistribute
proprietary software without clear authorization.

After you select the installer, the launcher automates the supported portion:
it prepares the private Wine prefix, installs prerequisites, runs the selected
installer, and configures the launcher integration. Autodesk may still require
interactive sign-in or agreement prompts during installation and first launch.

The package otherwise provides a complete, preconfigured compatibility
environment for running Fusion. It includes patched Wine, an isolated Wine
prefix, the required helper tools and prerequisites, browser sign-in callback
integration, and a shared `H:` drive for model files. Users do not need to
install, configure, or tune Wine manually. “Complete environment” describes
what the package configures; it is not a guarantee that every Fusion feature
works on every system, and Autodesk does not officially support this Linux
configuration.

## Build everything

On x86-64 Debian/Ubuntu, install Flatpak build tooling and the runtime:

```bash
sudo apt install flatpak flatpak-builder
flatpak remote-add --if-not-exists flathub \
  https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub \
  org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08
make
```

The default `all` target builds:

- `dist/cad-wine-launcher_0.3.0_x86_64.flatpak`
- `dist/cad-wine-launcher_0.3.0_amd64.deb`
- `dist/cad-wine-launcher_0.3.0_sources.tar.gz`

`make clean` removes only this project's generated `build/` and `dist/`
directories. Individual targets are `make flatpak`, `make deb`,
`make source-bundle`, and `make test`.

## Install the Flatpak file

```bash
flatpak install --user ./dist/cad-wine-launcher_0.3.0_x86_64.flatpak
flatpak run org.community.CADWineLauncher
```

These two commands are sufficient on desktops that automatically select the
included `adskidmgr` URL handler. If the browser completes authentication but
does not return to Fusion, register the callback once on the host:

```bash
xdg-mime default org.community.CADWineLauncher.Callback.desktop \
  x-scheme-handler/adskidmgr
```

On first run, the launcher displays its unofficial status, links Autodesk's
terms, asks you to confirm both acceptance and a valid entitlement, then opens
a file chooser. As explained above, for legal and licensing reasons you must
sign in to your [Autodesk Account](https://manage.autodesk.com/), download the
Windows installer yourself, and then select that file. The package contains no
Autodesk download URL. For an explicit terminal setup:

```bash
flatpak run org.community.CADWineLauncher --install \
  --installer /path/to/your/Autodesk-installer.exe
```

Interactive confirmation is the default. For automation only after reviewing
the terms, add `--accept-autodesk-terms`. The same flow applies to `--update`.
Other commands are `--status`, `--dry-run`, and `--debug`.

The launcher copies the selected installer into private temporary storage only
while Wine executes it and then deletes that copy. It never deletes the
original user-selected file. The downloaded Microsoft WebView2 installer is
also deleted after successful installation. Failed prerequisite downloads may
remain so setup can be diagnosed and retried.

## Isolation and data

The Flatpak bundles patched Wine, pinned Winetricks, 7-Zip, and cabextract on
Freedesktop 25.08. Its mutable prefix and logs live below
`~/.var/app/org.community.CADWineLauncher/data/cad-wine-launcher/`; cache lives
below `~/.var/app/org.community.CADWineLauncher/cache/cad-wine-launcher/`.
Default host file access is limited to `~/.autodesk_fusion`, which Flatpak
creates when needed. The launcher maps that directory to Windows drive `H:` in
its private Wine prefix, so models saved under `H:\` are immediately available
to Linux applications in `~/.autodesk_fusion`. The rest of the home directory
is not exposed. This shared folder remains after uninstalling or deleting the
Flatpak's private application data.

The app also has network, GPU, audio, X11/IPC, and multiarch access. X11
weakens isolation; Flatpak is not a VM or a complete security boundary.

The user-selected installer is normally exposed through Flatpak's document
portal. To grant another model directory deliberately:

```bash
flatpak override --user --filesystem=/absolute/path/to/models \
  org.community.CADWineLauncher
```

To uninstall the app **and its Wine prefix, installed Windows application,
settings, logs, and caches** in one operation, use:

```bash
flatpak uninstall --user --delete-data org.community.CADWineLauncher
```

Without `--delete-data`, Flatpak intentionally preserves everything below
`~/.var/app/org.community.CADWineLauncher/`; this can consume many gigabytes.
If an older `org.community.Fusion360` build was already uninstalled normally,
first verify its exact, case-sensitive path and size, then remove it only if no
models or settings need to be recovered:

```bash
du -sh -- "$HOME/.var/app/org.community.Fusion360"
rm -rf -- "$HOME/.var/app/org.community.Fusion360"
```

Do not substitute a broader `.var/app` path in the removal command.

## Debian alternative

```bash
sudo apt install ./dist/cad-wine-launcher_0.3.0_amd64.deb
cad-wine-launcher
```

The Debian package is not self-contained or sandboxed. It downloads the same
pinned Wine runtime and uses host libraries. Per-user data remains after the
package is removed.

## Corresponding source and licenses

The source archive built by `make source-bundle` contains Wine 11.10, the exact
community Wine patch and recorded build recipe, pinned Winetricks, 7-Zip and
cabextract source, launcher source, manifests, and license material. Every
download is SHA-256 verified. See `source-offer/README.md` for revisions,
hashes, build commands, and the provenance limitation of the third-party
prebuilt Wine archive. Keep this source archive with any retained or shared
copy of the Flatpak.

No Autodesk software appears in the source archive. Microsoft and Autodesk
components remain governed by their own terms.

Run offline tests with:

```bash
make test
```

The tests use temporary prefixes and fake installers; they do not install or
exercise Autodesk Fusion. A real acceptance test still needs installation,
browser sign-in, model open/save/export, rendering, and updating.

## GitHub-hosted releases

The `Build and publish release` GitHub Actions workflow performs release builds
entirely on a GitHub-hosted Ubuntu runner. It starts from a clean repository
checkout; files from a developer's local `build/` or `dist/` directory are
never used.

The workflow runs for a pushed semantic-version tag such as `v0.3.0`, or it can
be started from the Actions page with **Run workflow** and the same tag as its
input. The tag must exactly match the version in `packaging/changelog`.
The tagged commit must already be present on the repository's default branch;
GitHub will reject release creation when a tag points to an unpushed commit
that adds or changes workflow files.

For example:

```bash
git push origin main
git tag v0.3.0
git push origin v0.3.0
```

The runner installs the pinned Flatpak runtime, runs the tests and metadata
validators, executes `make clean` followed by `make all`, and verifies
`SHA256SUMS`. It then publishes these assets to the GitHub Release:

- `cad-wine-launcher_0.3.0_x86_64.flatpak`
- `cad-wine-launcher_0.3.0_amd64.deb`
- `cad-wine-launcher_0.3.0_sources.tar.gz`
- `SHA256SUMS`

GitHub also generates its standard source-code `.zip` and `.tar.gz` archives
for the release tag. The project source archive above is still included because
it carries the corresponding source and license material for the bundled free
software components.
