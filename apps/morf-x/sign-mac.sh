#!/bin/sh
# Ad-hoc sign the packaged apps so macOS runs them on this Mac (not notarised: on another Mac, right-click > Open).
set -e
cd "$(dirname "$0")"
for a in dist/MORF-X-darwin-*/MORF-X.app; do
  codesign --force --deep --sign - "$a" && echo "signed (ad hoc): $a"
done
