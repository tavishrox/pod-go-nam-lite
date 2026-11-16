// Copy the MORF-X page and its data from web/pod-go into ./web, so the app and the website share one source.
const fs = require('fs'), path = require('path');
const src = path.join(__dirname, '..', '..', 'web', 'pod-go'), dst = path.join(__dirname, 'web');
const files = ['morph.html', 'podgo-usb.js', 'neon.css', 'focus-defaults.json', 'focus-helix.json', 'morf-x-icon.svg'];
fs.mkdirSync(dst, { recursive: true });
for (const f of files) fs.copyFileSync(path.join(src, f), path.join(dst, f));
console.log(`copied ${files.length} files into web/`);
