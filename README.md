# Community CAD Launcher for Autodesk Fusion

This repository builds dedicated Flatpak and Debian launcher packages for use
with Autodesk Fusion. See the [packaging instructions](packaging/README.md) for
build, installation, data-isolation, and removal instructions.

This independent project is unofficial and unaffiliated with Autodesk. It does
not include or automatically download Autodesk Fusion. The user must obtain the
Windows installer from their Autodesk Account, accept Autodesk's terms, and
have a valid entitlement.

Autodesk and Autodesk Fusion are trademarks of the Autodesk group of
companies. Community CAD Launcher is not affiliated with Autodesk.

## Why installation is not fully automatic

Installation deliberately requires a few manual steps:

1. Sign in to the [Autodesk Account](https://manage.autodesk.com/) associated
   with your Fusion entitlement.
2. Review and accept Autodesk's applicable user agreement and download terms.
3. Download the Windows Autodesk Fusion installer from your account.
4. Start this launcher and select the downloaded installer when prompted.

This is less convenient than a one-click installation, but it is intentional.
Autodesk Fusion is proprietary software supplied through Autodesk's account,
license-entitlement, and terms-acceptance process. This independent project
cannot grant those rights on Autodesk's behalf, so it does not include, mirror,
or automatically fetch the Fusion installer. Requiring the account holder to
obtain and select the installer avoids bypassing that process and keeps
Autodesk software outside this GPL-licensed package. After you select the
installer, the launcher runs it in its private Wine environment.

Although obtaining the Autodesk installer is manual, the Linux compatibility
environment is not. The package provides a complete, preconfigured environment
for running Fusion: patched Wine, an isolated Wine prefix, required helper
tools and prerequisites, sign-in callback integration, and the shared `H:`
drive. You do not need to install, configure, or tune Wine manually. This does
not make Linux an officially supported Autodesk platform or guarantee that
every Fusion feature will work on every system.

Build all artifacts with:

```bash
make
```

Install the Flatpak bundle with:

```bash
flatpak install --user ./dist/cad-wine-launcher_0.3.1_x86_64.flatpak
flatpak run org.community.CADWineLauncher
```

On first run, follow the manual Autodesk download workflow described above and
select the downloaded `.exe` file in the launcher's file chooser.

## Update an existing installation

To replace the installed launcher with a newer downloaded Flatpak bundle while
keeping its private Fusion installation and settings:

```bash
flatpak install --user --reinstall \
  ./cad-wine-launcher_0.3.1_x86_64.flatpak
```

To update Autodesk Fusion itself, sign in to your Autodesk Account, accept the
applicable terms, download the current Windows installer, and run:

```bash
flatpak run org.community.CADWineLauncher --update
```

The launcher asks you to select the downloaded installer and updates Fusion in
the existing Wine prefix. It does not remove your existing settings or shared
files in `~/.autodesk_fusion`.

After the main Fusion window exits, the launcher also shuts down the private
Wine session. This removes WebView2, Edge Updater, and Wine service processes
that would otherwise keep the Flatpak running and obstruct its next launch.
This cleanup affects only this launcher's Wine prefix, not host applications.

Most desktops register the included sign-in callback automatically. If the web
browser does not return to Fusion after authentication, register the callback
once on the host:

```bash
xdg-mime default org.community.CADWineLauncher.Callback.desktop \
  x-scheme-handler/adskidmgr
```

The launcher, packaging code, and original artwork are licensed under the
[GNU General Public License version 3 or later](LICENSE). Bundled third-party
components retain their own licenses, included with the package and its
corresponding-source archive.
