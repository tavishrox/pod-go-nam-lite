// MORF-X desktop app: the MORF-X page (web/pod-go/morph.html) in its own window, talking to a Line 6 unit over
// WebUSB. Electron is Chromium, so the page's USB code runs as it does in Chrome; this file only serves the
// page and answers the USB questions a browser would ask the user.
const { app, BrowserWindow, protocol, net, session, shell } = require('electron');
const path = require('path');
const { pathToFileURL } = require('url');

app.setName('MORF-X');

// The units MORF-X knows (as in podgo-usb.js): POD Go, Helix, HX Stomp, HX Stomp XL.
const LINE6 = 0x0e41, PRODUCTS = [0x424b, 0x4248, 0x4246, 0x4253];
const isUnit = d => d && d.vendorId === LINE6 && PRODUCTS.includes(d.productId);

// app://morf-x/... serves ./web: a secure origin, so WebUSB, fetch() and IndexedDB work as on the website.
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } }
]);
const WEB = path.join(__dirname, 'web');

function createWindow() {
  const win = new BrowserWindow({
    width: 1180, height: 920, minWidth: 420, minHeight: 600, title: 'MORF-X', backgroundColor: '#100e1f',
    icon: path.join(__dirname, 'res', 'MORF-X.png'),
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false }
  });
  win.on('page-title-updated', e => { e.preventDefault(); win.setTitle('MORF-X'); });
  // The website's nav links to pages the app doesn't carry: hide it. Links leave the app for the browser.
  win.webContents.on('did-finish-load', () => win.webContents.insertCSS('.neon-nav { display: none !important; }'));
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('app://morf-x/')) { e.preventDefault(); shell.openExternal(url); }
  });
  win.loadURL('app://morf-x/morph.html?app=1');
  if (process.env.MORFX_SELFTEST) require('./selftest')(win);
}

app.whenReady().then(() => {
  protocol.handle('app', req => {
    const rel = decodeURIComponent(new URL(req.url).pathname).replace(/^\/+/, '');
    const file = path.normalize(path.join(WEB, rel));
    if (!file.startsWith(WEB)) return new Response('not found', { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });

  const ses = session.defaultSession;
  // A browser shows a device chooser here; the app picks the connected Line 6 unit itself.
  ses.on('select-usb-device', (event, details, callback) => {
    event.preventDefault();
    const unit = details.deviceList.find(isUnit);
    callback(unit ? unit.deviceId : '');
  });
  ses.setPermissionCheckHandler((wc, permission) => permission === 'usb' || permission === 'fileSystem');
  ses.setDevicePermissionHandler(details => details.deviceType === 'usb' && isUnit(details.device));

  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => app.quit());
