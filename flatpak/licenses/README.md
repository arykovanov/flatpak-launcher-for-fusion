These notices accompany the bundled open source tools. The launcher's
GPL-3.0-or-later license is in
`/app/share/licenses/cad-wine-launcher/LICENSE`; its Debian-format notice is in
`/app/share/doc/cad-wine-launcher/copyright`. Winetricks contains its own
copyright and LGPL notice in `/app/bin/winetricks`; the full LGPL 2.1 text is
included under `wine/COPYING.LIB`.

Pinned upstream sources:

- Wine binary release and build project:
  https://github.com/Lolig4/Autodesk-Fusion-360-for-Linux/releases/tag/Pre_Build_Wine%2FProton_01.06.26
  https://github.com/Lolig4/Autodesk-Fusion-360-for-Linux
- Wine project: https://gitlab.winehq.org/wine/wine
- Winetricks: https://github.com/Winetricks/winetricks/tree/f3890f670867b5ffbc3938726db45c0f7d16c8ba
- 7-Zip: https://github.com/ip7z/7zip/tree/b88c6bc09339de32f7d18bbab900686b244f42ba
- cabextract: https://deb.debian.org/debian/pool/main/c/cabextract/cabextract_1.11.orig.tar.gz

The exact corresponding-source archive is produced by `make source-bundle`;
see `source-offer/README.md` in the project. Autodesk Fusion is neither bundled
nor downloaded by this package. A user-supplied Autodesk installer and
Microsoft software remain subject to their own terms.
