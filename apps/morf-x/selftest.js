// MORFX_SELFTEST=1 npx electron . : connect to the unit as a user would (Connect your device), print what
// MORF-X found, disconnect and quit. Reads only: the pad is never moved and nothing is saved.
const { app } = require('electron');
module.exports = win => {
  win.webContents.once('did-finish-load', async () => {
    const js = s => win.webContents.executeJavaScript(s, true);
    try {
      await new Promise(r => setTimeout(r, 1500));
      await js("document.getElementById('connect').click()");
      let status = '';
      for (let i = 0; i < 40; i++) {
        await new Promise(r => setTimeout(r, 250));
        status = await js("document.getElementById('conn').textContent");
        if (!/Connecting|reading the blocks/.test(status)) break;
      }
      const out = await js(`({ status: document.getElementById('conn').textContent,
        device: pg && pg.device ? pg.device.name : null,
        blocks: [...document.getElementById('pick').options].map(o => o.textContent),
        tones: cur ? KEYS.map(k => cur.set.regions[k].name) : [],
        saveShown: !document.getElementById('save').hidden,
        firmware: document.getElementById('unitFw').hidden ? null : document.getElementById('unitFw').textContent,
        build: document.getElementById('unitFw').title })`);
      out.presets = await js(`(async () => { const c = await pg.current();
        const l = await q(() => pg.presetList(c.setlist)); return { setlist: c.setlist, count: l.length,
        first: l.slice(0, 6).map(p => slotName(p.index) + ' ' + p.name) }; })()`);
      console.log('SELFTEST', JSON.stringify(out, null, 2));
      await js("document.getElementById('disconnect').click()");
      await new Promise(r => setTimeout(r, 800));
    } catch (e) { console.log('SELFTEST error', e.message); }
    app.quit();
  });
};
