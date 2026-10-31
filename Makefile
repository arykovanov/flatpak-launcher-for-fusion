# SPDX-License-Identifier: GPL-3.0-or-later

.DEFAULT_GOAL := all

VERSION := $(shell sed -n 's/^Version: //p' packaging/control)

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
		dist/cad-wine-launcher_$(VERSION)_x86_64.flatpak \
		dist/cad-wine-launcher_$(VERSION)_amd64.deb \
		dist/cad-wine-launcher_$(VERSION)_sources.tar.gz \
		> dist/SHA256SUMS

test:
	python3 -m unittest discover -s tests -v

clean:
	@test -n "$(CURDIR)" -a "$(CURDIR)" != "/"
	rm -rf -- "$(CURDIR)/build" "$(CURDIR)/dist"
