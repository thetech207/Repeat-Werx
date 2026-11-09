#!/bin/sh
# Build a .deb from dist/repeatwerx (run pyinstaller first).
# Usage: packaging/build-deb.sh <version>
set -eu
VER="$1"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE=$(mktemp -d)/repeatwerx-$VER
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/lib" "$STAGE/usr/bin" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE/usr/share/doc/repeatwerx"

cp -r "$ROOT/dist/repeatwerx" "$STAGE/usr/lib/repeatwerx"
chmod -R u=rwX,go=rX "$STAGE/usr/lib/repeatwerx"

printf '#!/bin/sh\nexec /usr/lib/repeatwerx/repeatwerx "$@"\n' \
    > "$STAGE/usr/bin/repeatwerx"
chmod 755 "$STAGE/usr/bin/repeatwerx"

install -m 644 "$ROOT/packaging/repeatwerx.desktop" \
    "$STAGE/usr/share/applications/repeatwerx.desktop"
install -m 644 "$ROOT/Images/repeatwerx-icon.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/repeatwerx.svg"
install -m 644 "$ROOT/Images/repeatwerx-icon-1024.png" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps/repeatwerx.png"

printf 'Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\nUpstream-Name: Repeat-Werx\nSource: https://github.com/thetech207/Repeat-Werx\n' \
    > "$STAGE/usr/share/doc/repeatwerx/copyright"

cat > "$STAGE/DEBIAN/control" <<CTL
Package: repeatwerx
Version: $VER
Section: graphics
Priority: optional
Architecture: amd64
Maintainer: thetech207 <https://github.com/thetech207>
Depends: libc6, libstdc++6, libgl1, libegl1, libxkbcommon0, libdbus-1-3, libfontconfig1, libglib2.0-0t64
Description: Seamless repeating pattern designer
 Designs seamless repeating tiles with constrained randomness:
 wrap-around Poisson-disc collision placement, tileable Perlin noise
 fields, Mondrian quadtrees, color harmonies and the 60-30-10 rule.
 Vector shapes, SVG and raster import with background keying, layers,
 and PNG/JPEG/TIFF/WebP/SVG/PDF export.
CTL

dpkg-deb --build --root-owner-group "$STAGE" \
    "$ROOT/dist/repeatwerx_${VER}_amd64.deb"
echo "built dist/repeatwerx_${VER}_amd64.deb"
