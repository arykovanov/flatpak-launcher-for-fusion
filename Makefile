# SPDX-License-Identifier: GPL-3.0-or-later

.DEFAULT_GOAL := all

.PHONY: all flatpak deb source-bundle checksums test clean

all: checksums

flatpak:
	./build-flatpak.sh

deb:
	./build-deb.sh

source-bundle:
	./build-source-bundle.sh

checksums: flatpak deb source-bundle
	sha256sum \
		dist/CADWineLauncher.flatpak \
		dist/cad-wine-launcher_0.2.0_amd64.deb \
		dist/CADWineLauncher-0.2.0-sources.tar.gz \
		> dist/SHA256SUMS

test:
	python3 -m unittest discover -s tests -v

clean:
	@test -n "$(CURDIR)" -a "$(CURDIR)" != "/"
	rm -rf -- "$(CURDIR)/build" "$(CURDIR)/dist"
