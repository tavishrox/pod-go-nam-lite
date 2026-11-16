#!/bin/sh
# Make res/MORF-X.icns (Mac), res/MORF-X.png (window icon) from the MORF-X mark (web/pod-go/morf-x-icon.svg).
# Draws it with headless Chrome on a transparent 1024 px canvas, inside the Mac icon grid (824 px).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SVG="$(cd ../../web/pod-go && pwd)/morf-x-icon.svg"
mkdir -p res/iconset
cat > res/iconset/icon.html <<HTML
<!doctype html><html><body style="margin:0;background:transparent">
<img src="file://$SVG" style="position:absolute;left:100px;top:100px;width:824px;height:824px"></body></html>
HTML
"$CHROME" --headless --disable-gpu --hide-scrollbars --default-background-color=00000000 --allow-file-access-from-files \
  --window-size=1024,1024 --screenshot="$PWD/res/MORF-X.png" "file://$PWD/res/iconset/icon.html" 2>/dev/null
I=res/MORF-X.iconset; rm -rf "$I"; mkdir -p "$I"
for s in 16 32 128 256 512; do
  sips -z $s $s res/MORF-X.png --out "$I/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); sips -z $d $d res/MORF-X.png --out "$I/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$I" -o res/MORF-X.icns
rm -rf "$I"
echo "res/MORF-X.icns and res/MORF-X.png made"
