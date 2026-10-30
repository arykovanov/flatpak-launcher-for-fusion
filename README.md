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

Build all artifacts with:

```bash
make
```

Install the Flatpak bundle with:

```bash
flatpak install --user ./dist/CADWineLauncher.flatpak
xdg-mime default org.community.CADWineLauncher.Callback.desktop \
  x-scheme-handler/adskidmgr
flatpak run org.community.CADWineLauncher
```

The launcher, packaging code, and original artwork are licensed under the
[GNU General Public License version 3 or later](LICENSE). Bundled third-party
components retain their own licenses, included with the package and its
corresponding-source archive.
