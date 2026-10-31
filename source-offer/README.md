# Corresponding source for Community CAD Launcher for Autodesk Fusion 0.3.1

This directory identifies the complete corresponding source used by the
free-software components in the local Flatpak bundle. Run
`./build-source-bundle.sh` (or `make source-bundle`) to create
`dist/cad-wine-launcher_0.3.1_sources.tar.gz`, containing the verified source
archives, launcher source, build manifest, patch, licenses, and this document.

The Flatpak embeds no Autodesk software. Autodesk Fusion and its installer are
proprietary, are not corresponding source, and are intentionally absent.

## Patched Wine build

The Flatpak's prebuilt runtime is `fusion-wine-build.tar.gz`, SHA-256
`65812663c11a3221d6f4e63644afc4925446dd8ca8263bcdc1c3cdc56a1aa985`,
published as `Pre_Build_Wine/Proton_01.06.26` by the community project. Its
associated recipe revision is
`02c7b8d550427ee5646b4aedf7e337896733c786`, whose change records the runtime
as Wine 11.10. The source bundle contains the official Wine 11.10 source and
the exact `wine-captionless-popups.patch` from that revision.

The corresponding Wine build procedure recorded by that revision is:

```sh
patch -d wine-11.10 -p1 < wine-captionless-popups.patch
cd wine-11.10
./configure --prefix=/desired/prefix CC="ccache gcc" \
  i386_CC="ccache i686-w64-mingw32-gcc" \
  x86_64_CC="ccache x86_64-w64-mingw32-gcc" \
  --enable-archs=i386,x86_64 --disable-tests
make -j"$(nproc)"
make install
```

Wine is LGPL-2.1-or-later. The full license is in Wine's source archive and
`flatpak/licenses/wine/COPYING.LIB`.

## Other bundled free software

- Winetricks commit `f3890f670867b5ffbc3938726db45c0f7d16c8ba`, LGPL-2.1-or-later.
- 7-Zip commit `b88c6bc09339de32f7d18bbab900686b244f42ba`, under the licenses included in its source.
- cabextract 1.11, GPL-3.0-or-later.
- The launcher and integration files in this repository, GPL-3.0-or-later.

All downloads are pinned by SHA-256 in `build-source-bundle.sh`. The generated
archive is the preferred way to accompany any copy of the local Flatpak. Keep
the source archive available for as long as you keep or share the binary.

The upstream binary and its associated source metadata are third-party
artifacts. For the strongest provenance in a future public distribution,
compile Wine from the included source and patch in the Flatpak build instead
of consuming the upstream prebuilt archive.
