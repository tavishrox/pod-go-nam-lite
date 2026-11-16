// podgo-usb.js - talk to a running POD Go over WebUSB the way POD Go Edit does (the companion page).
// A port of tools/hx_ctl.py and tools/hx_dfu_reboot.py's Stream: keep the three in step.
//
//   var pg = await PODGOUSB.connect(navigator.usb, { log })   // asks the browser for the POD Go
//   await pg.current()          -> { setlist, preset, name }
//   await pg.presetList(setlist)-> [{ index, name }]
//   await pg.select(preset)     (loads it on the unit: unsaved edits there are lost)
//   await pg.readPreset(true)   -> Uint8Array l6-helix blob; true asks for snapshots 5 and 6 (key 14) too
//   await pg.writeEditBuffer(blob)   (the unit's edit buffer only: nothing saved)
//   await pg.restore(slot, blob, name, setlist)   writes blob into that slot and saves it (overwrites the slot)
//   await pg.slotInfo(pos)      -> null or { pos, model, on, values, types } for grid position 0..11 (read only, 0x2d)
//   await pg.setParam(pos, index, value, asInt)   one parameter of the edit buffer (0x1e; nothing saved)
//   pg.onNotify(fn)             every notify message (a Map); a knob change, the pad's or the unit's, is 0x1e
//   await pg.close()
//
// Wire format (hx_dfu_reboot.py's notes): one message per OUT transfer, padded to 4 bytes; transport header
// w0 = type<<28 | 2<<26 | len, w1 = src | dst<<16 (type 2 = SYN with an extra word mtu<<16); stream header
// w0 = flags<<24 | seq<<8, w1 = the receive-window edge (0x1000 + bytes consumed). Streams: editor 0x1000 <->
// 0x3ED (service 6), librarian 0x1001 <-> 0x3EF (2), notify 0x1002 <-> 0x3F0 (4). Each selects its service with
// {u16 1, u16 svc, u32 1, u8 svc}; requests are {u16 1, u16 svc, u32 len} + MessagePack {0x66 seq, 0x64 cmd,
// 0x65 params}, replies {u16 0, u16 svc, u32 len} + {0x66 seq, 0x67 status, 0x68 result}.
(function (root) {
  "use strict";

  var DEVICE = { vendorId: 0x0E41, productId: 0x424B };
  // Units that speak the same editor protocol (MORF-X passes these; the companion stays POD Go only).
  // slots: grid positions that hold blocks. Helix: 20 per DSP (1..8 path A, 11..18 path B), checked on a
  // Helix Floor 2026-11-16. HX Stomp: one DSP laid out the same way (not yet tried from the browser).
  var DEVICES = [
    { vendorId: 0x0E41, productId: 0x424B, name: "POD Go", family: "podgo", slots: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] },
    { vendorId: 0x0E41, productId: 0x4248, name: "Helix", family: "helix", bStart: 11,
      slots: [1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18, 21, 22, 23, 24, 25, 26, 27, 28, 31, 32, 33, 34, 35, 36, 37, 38] },
    // HX Effects (2026-11-16, on the unit): 1..8 path A, 9 looper, 10 split, 11 merge, path B from 12, 21 output;
    // reading blocks and setting a knob checked, saving not yet.
    { vendorId: 0x0E41, productId: 0x4245, name: "HX Effects", family: "helix", bStart: 12, saveUntested: true,
      slots: [1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 17, 18, 19, 20] },
    { vendorId: 0x0E41, productId: 0x4246, name: "HX Stomp", family: "helix", bStart: 11, untested: true,
      slots: [1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18] },
    { vendorId: 0x0E41, productId: 0x4253, name: "HX Stomp XL", family: "helix", bStart: 11, untested: true,
      slots: [1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18] }
  ];
  var RX_BUF = 0x1000, HB_MS = 1000;
  var F_SYN = 0x01, F_FIN = 0x02, F_DATA = 0x04, F_WIN = 0x08, F_HB = 0x10, F_HBREQ = 0x20;
  var EDITOR = { local: 0x1000, remote: 0x03ED, svc: 6 },
      LIBRARIAN = { local: 0x1001, remote: 0x03EF, svc: 2 },
      NOTIFY = { local: 0x1002, remote: 0x03F0, svc: 4 };
  var K = { SEQ: 0x66, CMD: 0x64, PARAMS: 0x65, STATUS: 0x67, RESULT: 0x68, ERR: 0x6F,
            SETLIST: 0x6B, PRESET: 0x6C, NAME: 0x6D, PBLOB: 0x6E };
  // SAVE_AS 0x46: save the edit buffer to {0x6b setlist, 0x6c slot, 0x6d name} (0x45 keeps the slot's name);
  // the unit's own save path, so snapshots 5 and 6 in the buffer are written too (docs/research/COMPANION_APP.md).
  var CMD = { LOAD: 0x14, SET_EDITBUF: 0x15, GET_EDITBUF: 0x16, CURRENT: 0x17, SAVE_AS: 0x46, LIB_LIST: 0x01,
              SET_PARAM: 0x1e, OBJECT_INFO: 0x2d };
  // SET_PARAM {0x62 grid position, 0x1d true (a model parameter), 0x1a 0, 0x1c parameter index, 0x77 float32}:
  // POD Go Edit's setObjectParam; the unit echoes each change on the notify stream as {0x69: 0x1e, 0x6a: {...,
  // 0x6a: the same params}}. OBJECT_INFO {0x62 pos} -> {13 pos, 24 {19 kind (6 = a block), 20 {9 category,
  // 10 on, 25 model (the place in POD Go Edit's model list), 11 {4 values in index order}}}} (2026-11-15).
  var APP = { 0x7a: 1 };   // the six-snapshot firmware's marker: the read carries key 14 (snapshots 5 and 6)

  function F32(v) { this.v = v; }    // a number sent as float32 even when whole (0 and 1 knob values)
  var PENDING = { pending: true };   // a request the unit accepted and completes later (status 1)
  function fail(text, code) { var e = new Error(text); e.code = code || "usb"; return e; }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function concat(parts) {
    var n = 0; parts.forEach(function (p) { n += p.length; });
    var out = new Uint8Array(n), o = 0;
    parts.forEach(function (p) { out.set(p, o); o += p.length; });
    return out;
  }
  function u32s(list) {
    var b = new Uint8Array(4 * list.length), v = new DataView(b.buffer);
    list.forEach(function (w, i) { v.setUint32(4 * i, w >>> 0, true); });
    return b;
  }
  function pad4(b) { return b.length % 4 ? concat([b, new Uint8Array(4 - b.length % 4)]) : b; }
  function text(b) { var s = ""; for (var i = 0; i < b.length && b[i]; i++) s += String.fromCharCode(b[i]); return s; }

  // ---- MessagePack (what the unit sends and accepts; strings and buffers decode as Uint8Array)
  var MP = {
    encode: function (v) { var out = []; enc(v, out); return concat(out); },
    // typed: floats come back as F32 objects, so a float 0.0 stays distinguishable from an integer 0
    decode: function (b, typed) { typedFloats = !!typed; try { return dec(b, 0)[0]; } finally { typedFloats = false; } },
    decodeAt: dec
  };
  function enc(v, out) {
    if (v === null || v === undefined) { out.push(Uint8Array.of(0xc0)); return; }
    if (v === true || v === false) { out.push(Uint8Array.of(v ? 0xc3 : 0xc2)); return; }
    if (v instanceof F32) { var g = new Uint8Array(5); g[0] = 0xca; new DataView(g.buffer).setFloat32(1, v.v); out.push(g); return; }
    if (typeof v === "number") {
      if (Number.isInteger(v)) {
        if (v >= 0 && v < 128) out.push(Uint8Array.of(v));
        else if (v < 0 && v >= -32) out.push(Uint8Array.of(v & 0xff));
        else if (v >= 0 && v < 256) out.push(Uint8Array.of(0xcc, v));
        else if (v >= 0 && v < 65536) out.push(Uint8Array.of(0xcd, v >> 8, v & 0xff));
        else if (v >= 0 && v < 4294967296) { var b = new Uint8Array(5); b[0] = 0xce; new DataView(b.buffer).setUint32(1, v); out.push(b); }
        else if (v >= -128 && v < 0) out.push(Uint8Array.of(0xd0, v & 0xff));
        else if (v >= -32768 && v < 0) { var c = new Uint8Array(3); c[0] = 0xd1; new DataView(c.buffer).setInt16(1, v); out.push(c); }
        else { var d = new Uint8Array(5); d[0] = 0xd2; new DataView(d.buffer).setInt32(1, v); out.push(d); }
      } else { var f = new Uint8Array(5); f[0] = 0xca; new DataView(f.buffer).setFloat32(1, v); out.push(f); }
      return;
    }
    if (v instanceof Uint8Array) {      // as POD Go Edit packs buffers: MessagePack str
      var n = v.length;
      if (n < 32) out.push(Uint8Array.of(0xa0 | n));
      else if (n < 256) out.push(Uint8Array.of(0xd9, n));
      else if (n < 65536) out.push(Uint8Array.of(0xda, n >> 8, n & 0xff));
      else { var h = new Uint8Array(5); h[0] = 0xdb; new DataView(h.buffer).setUint32(1, n); out.push(h); }
      out.push(v); return;
    }
    if (typeof v === "string") { enc(new TextEncoder().encode(v), out); return; }
    if (Array.isArray(v)) {
      var m = v.length;
      out.push(m < 16 ? Uint8Array.of(0x90 | m) : Uint8Array.of(0xdc, m >> 8, m & 0xff));
      v.forEach(function (x) { enc(x, out); }); return;
    }
    if (v instanceof Map) {
      out.push(v.size < 16 ? Uint8Array.of(0x80 | v.size) : Uint8Array.of(0xde, v.size >> 8, v.size & 0xff));
      v.forEach(function (x, k) { enc(k, out); enc(x, out); }); return;
    }
    var keys = Object.keys(v);
    out.push(keys.length < 16 ? Uint8Array.of(0x80 | keys.length) : Uint8Array.of(0xde, keys.length >> 8, keys.length & 0xff));
    keys.forEach(function (k) { enc(/^-?\d+$/.test(k) ? Number(k) : k, out); enc(v[k], out); });
  }
  var typedFloats = false;            // only ever set for the length of one synchronous decode
  function dec(b, p) {
    var t = b[p], dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    if (t === undefined) throw fail("MessagePack: truncated");
    if (t < 0x80) return [t, p + 1];
    if (t >= 0xe0) return [t - 256, p + 1];
    if ((t & 0xf0) === 0x80) return map(t & 15, p + 1);
    if ((t & 0xf0) === 0x90) return arr(t & 15, p + 1);
    if ((t & 0xe0) === 0xa0) return raw(t & 31, p + 1);
    switch (t) {
      case 0xc0: return [null, p + 1];
      case 0xc2: return [false, p + 1];
      case 0xc3: return [true, p + 1];
      case 0xc4: case 0xd9: return raw(b[p + 1], p + 2);
      case 0xc5: case 0xda: return raw(dv.getUint16(p + 1), p + 3);
      case 0xc6: case 0xdb: return raw(dv.getUint32(p + 1), p + 5);
      case 0xca: var f4 = dv.getFloat32(p + 1); return [typedFloats ? new F32(f4) : f4, p + 5];
      case 0xcb: var f8 = dv.getFloat64(p + 1); return [typedFloats ? new F32(f8) : f8, p + 9];
      case 0xcc: return [b[p + 1], p + 2];
      case 0xcd: return [dv.getUint16(p + 1), p + 3];
      case 0xce: return [dv.getUint32(p + 1), p + 5];
      case 0xcf: return [Number(dv.getBigUint64(p + 1)), p + 9];
      case 0xd0: return [dv.getInt8(p + 1), p + 2];
      case 0xd1: return [dv.getInt16(p + 1), p + 3];
      case 0xd2: return [dv.getInt32(p + 1), p + 5];
      case 0xd3: return [Number(dv.getBigInt64(p + 1)), p + 9];
      case 0xdc: return arr(dv.getUint16(p + 1), p + 3);
      case 0xdd: return arr(dv.getUint32(p + 1), p + 5);
      case 0xde: return map(dv.getUint16(p + 1), p + 3);
      case 0xdf: return map(dv.getUint32(p + 1), p + 5);
    }
    throw fail("MessagePack: type 0x" + t.toString(16) + " at " + p);
    function raw(n, q) { if (q + n > b.length) throw fail("MessagePack: truncated"); return [b.slice(q, q + n), q + n]; }
    function arr(n, q) { var a = []; for (var i = 0; i < n; i++) { var r = dec(b, q); a.push(r[0]); q = r[1]; } return [a, q]; }
    function map(n, q) {      // string keys (the backup file's) come back as JavaScript strings; values stay bytes
      var m = new Map();
      for (var i = 0; i < n; i++) {
        var k = dec(b, q), v = dec(b, k[1]);
        m.set(k[0] instanceof Uint8Array ? new TextDecoder().decode(k[0]) : k[0], v[0]);
        q = v[1];
      }
      return [m, q];
    }
  }

  // ---- the USB link: one IN reader, messages routed to their stream
  function Link(dev, epOut, epIn, mtu, log) {
    this.dev = dev; this.epOut = epOut; this.epIn = epIn; this.mtu = mtu; this.log = log || function () {};
    this.streams = []; this.closed = false; this.error = null;
  }
  Link.prototype.start = function () {
    var self = this;
    (function next() {
      if (self.closed) return;
      self.dev.transferIn(self.epIn, self.mtu).then(function (r) {
        if (r.data && r.data.byteLength) self.route(new Uint8Array(r.data.buffer, r.data.byteOffset, r.data.byteLength).slice());
        next();
      }, function (e) { if (!self.closed) { self.error = fail("The POD Go stopped answering (" + e.message + ")."); self.wake(); } });
    })();
    this.hb = setInterval(function () {
      var now = Date.now();
      self.streams.forEach(function (s) {
        if (s.rxSeq !== null && now - s.lastTx >= HB_MS) s.send(F_HB).catch(function () {});
      });
    }, 250);
  };
  Link.prototype.route = function (buf) {
    var off = 0, v = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
    while (off + 8 <= buf.length) {
      var w0 = v.getUint32(off, true), w1 = v.getUint32(off + 4, true), type = w0 >>> 28, len = w0 & 0xFFFF;
      if (off + 8 + len > buf.length) { this.log("truncated message from the unit"); return; }
      var m = { type: type, src: w1 & 0xFFFF, dst: w1 >>> 16, flags: null }, p = off + 8;
      if (type === 2) { m.mtu = v.getUint32(p, true) >>> 16; p += 4; }
      if (off + 8 + len - p >= 8) {
        var s0 = v.getUint32(p, true);
        m.flags = s0 >>> 24; m.seq = (s0 >>> 8) & 0xFF; m.window = v.getUint32(p + 4, true);
        m.data = buf.slice(p + 8, off + 8 + len);
      }
      for (var i = 0; i < this.streams.length; i++) {
        var s = this.streams[i];
        if (m.flags !== null && (m.src & 0xFF) === (s.remote & 0xFF) && m.dst === s.local) { s.handle(m); break; }
      }
      off += (8 + len + 3) & ~3;
    }
    this.wake();
  };
  Link.prototype.wake = function () { this.streams.forEach(function (s) { if (s.waiter) { var w = s.waiter; s.waiter = null; w(); } }); };
  Link.prototype.write = function (b) { return this.dev.transferOut(this.epOut, b); };
  Link.prototype.close = async function () {
    clearInterval(this.hb);
    this.closed = true;
    try { await this.dev.releaseInterface(0); } catch (e) { /* gone */ }
    try { await this.dev.close(); } catch (e) { /* gone */ }
  };

  // ---- a stream (hx_dfu_reboot.Stream)
  function Stream(link, local, remote) {
    this.link = link; this.local = local; this.remote = remote;
    this.txSeq = 1; this.rxSeq = null; this.consumed = 0; this.sent = 0; this.peerWindow = 0; this.peerMtu = 0;
    this.rx = new Uint8Array(0); this.waiter = null; this.lastTx = Date.now(); this.error = null;
    link.streams.push(this);
  }
  Stream.prototype.handle = function (m) {
    var f = m.flags;
    if (f & F_SYN) {
      if (this.rxSeq !== null) { this.error = fail("unexpected SYN from the unit"); return; }
      this.rxSeq = m.seq; this.peerMtu = m.mtu || 0; this.peerWindow = m.window; return;
    }
    if (this.rxSeq === null) { this.error = fail("the unit sent data before connecting"); return; }
    if (((m.seq - this.rxSeq) & 0xFF) !== 1) { this.error = fail("sequence gap from the unit"); return; }
    this.rxSeq = m.seq;
    if (f & (F_DATA | F_WIN)) {
      this.peerWindow = m.window;
      if (f & F_DATA && m.data.length) this.rx = concat([this.rx, m.data]);
    }
    if (f & F_FIN) this.error = fail("the unit closed the connection");
  };
  Stream.prototype.send = function (flags, data) {
    data = data || new Uint8Array(0);
    var sh = u32s([(flags << 24) | (this.txSeq << 8), RX_BUF + this.consumed]), body, type;
    if (flags & F_SYN) { body = concat([u32s([(this.link.mtu & 0xFFFF) << 16]), sh, data]); type = 2; }
    else { body = concat([sh, data]); type = 1; }
    var msg = pad4(concat([u32s([(type << 28) | (2 << 26) | body.length, this.local | ((this.remote & 0x3FF) << 16)]), body]));
    this.txSeq = (this.txSeq + 1) & 0xFF;
    this.sent += data.length;
    this.lastTx = Date.now();
    return this.link.write(msg);
  };
  Stream.prototype.wait = function (ms) {
    var self = this;
    return new Promise(function (resolve) {
      var t = setTimeout(function () { self.waiter = null; resolve(); }, ms);
      self.waiter = function () { clearTimeout(t); resolve(); };
    });
  };
  Stream.prototype.check = function () {
    if (this.error) throw this.error;
    if (this.link.error) throw this.link.error;
  };
  Stream.prototype.connect = async function (ms) {
    await this.send(F_SYN | F_HBREQ);
    var end = Date.now() + ms;
    while (this.rxSeq === null) {
      this.check();
      if (Date.now() > end) throw fail("The POD Go didn't answer. Quit POD Go Edit and try again.", "busy");
      await this.wait(100);
    }
  };
  Stream.prototype.write = async function (data, ms) {
    var end = Date.now() + ms;
    while (this.sent + data.length > this.peerWindow) {
      this.check();
      if (Date.now() > end) throw fail("the unit's receive window stayed closed");
      await this.wait(100);
    }
    await this.send(F_DATA, data);
  };
  Stream.prototype.read = async function (n, ms) {
    var end = Date.now() + ms;
    while (this.rx.length < n) {
      this.check();
      if (Date.now() > end) throw fail("timed out waiting for the POD Go");
      await this.wait(100);
    }
    var out = this.rx.slice(0, n);
    this.rx = this.rx.slice(n);
    this.consumed += n;
    return out;
  };
  Stream.prototype.windowUpdate = function () { return this.send(F_WIN); };
  Stream.prototype.fin = function () { return this.send(F_FIN).catch(function () {}); };

  // ---- a service channel (hx_ctl.Channel)
  function Channel(link, cfg) { this.st = new Stream(link, cfg.local, cfg.remote); this.svc = cfg.svc; this.seq = 0; }
  Channel.prototype.open = async function (ms) {
    await this.st.connect(ms);
    await this.writeMsg(Uint8Array.of(1, 0, this.svc, 0, 1, 0, 0, 0, this.svc), ms);
    var r = await this.readMsg(ms);
    if (r.body.length !== 1 || r.body[0] !== this.svc) throw fail("service " + this.svc + ": unexpected reply");
  };
  Channel.prototype.writeMsg = async function (data, ms) {
    var mx = (this.st.peerMtu || 512) - 16;
    for (var i = 0; i < data.length; i += mx) await this.st.write(data.slice(i, i + mx), ms);
  };
  Channel.prototype.readMsg = async function (ms) {
    var h = await this.st.read(8, ms), v = new DataView(h.buffer);
    var len = v.getUint32(4, true), body = new Uint8Array(0);
    while (body.length < len) {
      body = concat([body, await this.st.read(Math.min(len - body.length, 0x400), ms)]);
      await this.st.windowUpdate();
    }
    if (!len) await this.st.windowUpdate();
    return { a: v.getUint16(0, true), svc: v.getUint16(2, true), body: body };
  };
  Channel.prototype.request = async function (cmd, params, ms, typed) {
    ms = ms || 5000;
    this.seq = (this.seq + 1) & 0xFFFF;
    var req = new Map([[K.SEQ, this.seq], [K.CMD, cmd], [K.PARAMS, params === undefined ? null : params]]);
    var body = MP.encode(req), hdr = new Uint8Array(8), v = new DataView(hdr.buffer);
    v.setUint16(0, 1, true); v.setUint16(2, this.svc, true); v.setUint32(4, body.length, true);
    await this.writeMsg(concat([hdr, body]), ms);
    var rep = MP.decode((await this.readMsg(ms)).body, typed);
    if (rep.get(K.STATUS) === 1) return PENDING;   // accepted, completes later (announced on the notify stream)
    if (rep.get(K.STATUS) !== 0) {
      var res = rep.get(K.RESULT), err = res instanceof Map ? res.get(K.ERR) : null;
      throw fail("command 0x" + cmd.toString(16) + " refused (status " + rep.get(K.STATUS) + ", error " + err + ")");
    }
    return rep.get(K.RESULT);
  };
  // the notify stream: read all the time (unread, its messages pile up and the unit hangs), each message
  // handed to the listeners. A preset load ends with event 4 ({0x69: 4, ...}), about 0.3-0.4 s after the request.
  Channel.prototype.pump = function (onMsg) {
    var self = this;
    (async function () {
      while (!self.st.link.closed && !self.st.error) {
        if (self.st.rx.length < 8) { await self.st.wait(100); continue; }
        try {
          var m = await self.readMsg(5000), v = null;
          try { v = MP.decode(m.body); } catch (e) { /* not MessagePack */ }
          onMsg(v);
        } catch (e) { return; }
      }
    })();
  };

  // ---- the POD Go session
  function PodGo(link) { this.link = link; }
  PodGo.prototype.open = async function () {
    this.ed = new Channel(this.link, EDITOR); await this.ed.open(4000);
    // POD Go Edit keeps the notify stream open and read: unread, its messages pile up and the unit hangs
    // after some 30 preset loads (hx_ctl.py, 2026-11-01).
    this.nf = new Channel(this.link, NOTIFY); await this.nf.open(4000);
    var self = this;
    this.waiters = []; this.listeners = [];
    this.nf.pump(function (m) {
      var ev = m instanceof Map ? m.get(0x69) : null;
      self.listeners.forEach(function (fn) { try { fn(m); } catch (e) { /* a listener's own problem */ } });
      self.waiters = self.waiters.filter(function (w) { if (w.ev === ev) { w.done(); return false; } return true; });
    });
    this.lib = new Channel(this.link, LIBRARIAN); await this.lib.open(4000);
  };
  PodGo.prototype.event = function (ev, ms) {       // resolves on that notify event, or after ms
    var self = this, w = { ev: ev };
    var p = new Promise(function (resolve) {
      var t = setTimeout(function () { self.waiters = self.waiters.filter(function (x) { return x !== w; }); resolve(false); }, ms);
      w.done = function () { clearTimeout(t); resolve(true); };
    });
    this.waiters.push(w);
    return p;
  };
  PodGo.prototype.settle = function (ms) { return sleep(ms); };
  PodGo.prototype.current = async function () {
    var r = await this.ed.request(CMD.CURRENT);
    return { setlist: r.get(K.SETLIST), preset: r.get(K.PRESET), name: text(r.get(K.NAME) || new Uint8Array(0)) };
  };
  PodGo.prototype.presetList = async function (setlist) {
    var r = await this.lib.request(CMD.LIB_LIST, new Map([[K.SETLIST, setlist]]), 8000);
    // POD Go: [{slot: {0x6d: name}}]. Helix family: [{number: name}], the number counted across all setlists
    // (setlist 5 starts at 640), so the slot is the number less the list's first one (2026-11-16, Helix Floor).
    var base = null;
    return r.map(function (m) {
      var idx = m.keys().next().value, info = m.get(idx);
      if (info instanceof Map) return { index: idx, name: text(info.get(K.NAME) || new Uint8Array(0)) };
      if (base === null) base = idx;
      return { index: idx - base, name: info instanceof Uint8Array ? text(info) : String(info == null ? "" : info) };
    });
  };
  PodGo.prototype.select = async function (preset, setlist) {
    if (setlist === undefined) setlist = (await this.current()).setlist;
    var loaded = this.event(4, 4000);                // "preset loaded"
    await this.ed.request(CMD.LOAD, new Map([[K.SETLIST, setlist], [K.PRESET, preset]]), 10000);
    if (!(await loaded)) await this.settle(500);     // no event seen: give it a moment anyway
  };
  PodGo.prototype.readPreset = async function (withSnap56) {
    var r = await this.ed.request(CMD.GET_EDITBUF, withSnap56 ? new Map([[0x7a, 1]]) : null, 8000);
    if (!(r instanceof Uint8Array)) throw fail("the unit didn't send a preset");
    return r;
  };
  PodGo.prototype.writeEditBuffer = async function (blob) {
    if (text(blob.slice(1, 9)) !== "l6-helix") throw fail("that isn't a POD Go preset");
    var done = this.event(20, 4000);                 // the request's completion, if it completes later
    if (await this.ed.request(CMD.SET_EDITBUF, new Map([[K.PBLOB, blob]]), 10000) === PENDING) await done;
    await this.settle(150);
  };
  PodGo.prototype.saveAs = async function (slot, name, setlist) {
    if (setlist === undefined) setlist = (await this.current()).setlist;
    var nm = new TextEncoder().encode(String(name).slice(0, 16));
    var done = this.event(20, 6000);
    if (await this.ed.request(CMD.SAVE_AS, new Map([[K.SETLIST, setlist], [K.PRESET, slot], [K.NAME, concat([nm, Uint8Array.of(0)])]]), 15000) === PENDING) await done;
    await this.settle(150);
  };
  PodGo.prototype.restore = async function (slot, blob, name, setlist) {
    if (setlist === undefined) setlist = (await this.current()).setlist;
    await this.select(slot, setlist);                // the slot being restored is the current preset
    await this.writeEditBuffer(blob);
    await this.saveAs(slot, name, setlist);
  };
  PodGo.prototype.onNotify = function (fn) { this.listeners.push(fn); };
  PodGo.prototype.slotInfo = async function (pos) {
    var r = await this.ed.request(CMD.OBJECT_INFO, new Map([[0x62, pos]]), 5000, true);
    if (!(r instanceof Map) || !(r.get(24) instanceof Map) || !(r.get(24).get(20) instanceof Map)) return null;
    var o = r.get(24), b = o.get(20), ids = b.get(24), vals = b.get(11);
    var raw = vals instanceof Map && Array.isArray(vals.get(4)) ? vals.get(4) : [];
    // types[k]: "float" (knobs, dB, Hz), "int" (selectors), "bool" (switches), as the unit holds them
    return { pos: pos, kind: o.get(19), category: b.get(9), on: b.get(10),
             model: ids instanceof Map ? ids.get(25) : null,
             values: raw.map(function (v) { return v instanceof F32 ? v.v : v; }),
             types: raw.map(function (v) { return v instanceof F32 ? "float" : typeof v === "boolean" ? "bool" : typeof v === "number" ? "int" : "other"; }) };
  };
  // value: a number goes as float32 (knobs, dB, Hz), unless asInt (selectors: an integer); a boolean as a boolean
  PodGo.prototype.setParam = function (pos, index, value, asInt) {
    var v = typeof value === "boolean" ? value : asInt ? Math.round(value) : new F32(value);
    return this.ed.request(CMD.SET_PARAM, new Map([[0x62, pos], [0x1d, true], [0x1a, 0], [0x1c, index], [0x77, v]]));
  };
  // Several knob changes in one go: write every request, then read the replies in order. In a browser each USB
  // transfer costs a millisecond or two, so not waiting between requests saves most of the time. Checked on a
  // Helix Floor (2026-11-16): up to 8 outstanding, every reply in order and status 0. items: [[pos, index, value, asInt]].
  PodGo.prototype.setParams = async function (items) {
    var ch = this.ed, ms = 5000;
    for (var i = 0; i < items.length; i++) {
      var it = items[i], value = it[2];
      var v = typeof value === "boolean" ? value : it[3] ? Math.round(value) : new F32(value);
      ch.seq = (ch.seq + 1) & 0xFFFF;
      var req = new Map([[K.SEQ, ch.seq], [K.CMD, CMD.SET_PARAM],
        [K.PARAMS, new Map([[0x62, it[0]], [0x1d, true], [0x1a, 0], [0x1c, it[1]], [0x77, v]])]]);
      var body = MP.encode(req), hdr = new Uint8Array(8), dv = new DataView(hdr.buffer);
      dv.setUint16(0, 1, true); dv.setUint16(2, ch.svc, true); dv.setUint32(4, body.length, true);
      await ch.writeMsg(concat([hdr, body]), ms);
    }
    for (var j = 0; j < items.length; j++) {
      var rep = MP.decode((await ch.readMsg(ms)).body);
      var st = rep.get(K.STATUS);
      if (st !== 0 && st !== 1) throw fail("command 0x1e refused (status " + st + ")");
    }
  };
  PodGo.prototype.close = async function () {
    for (var c of [this.lib, this.nf, this.ed]) if (c) await c.st.fin();
    await sleep(200);
    await this.link.close();
  };

  // key 14 in a preset read with the marker: { holder, mask, records: [{ snapshot, name, colour }] } or null
  var RECSZ = 0x28c, NAME = 0x27e, COLOR = 0x27c;
  function snapshots56(blob) {
    for (var k = 0; k + 3 < blob.length; k++) {
      if (blob[k] === 0x87 && blob[k + 1] === 0x0e && blob[k + 2] === 0xc5) {
        var holder = blob[k + 5], mask = blob[k + 6], recs = [], j = 0;
        for (var i = 0; i < 3; i++) if (mask >> i & 1) {
          var r = blob.subarray(k + 9 + j * RECSZ, k + 9 + (j + 1) * RECSZ); j++;
          recs.push({ snapshot: i + 4, name: text(r.subarray(NAME, NAME + 11)), colour: r[COLOR] });
        }
        return { at: k, holder: holder + 1, mask: mask, records: recs };
      }
    }
    return null;
  }

  // ---- snapshot names and LED colours (1 to 6), edited in place in a preset blob
  // Stock section (key 10 of the preset): {..., 10: [4 x {4: name str, 12: colour, ...}]}; entries 0-2 are
  // snapshots 1-3, entry 3 is whichever of 4-6 the unit holds in its fourth slot (key 14's holder, else 4).
  // Key 14 (six-snapshot firmware, read with the app marker) holds the records of the other two: name at
  // +0x27e (11 bytes, NUL-padded), colour at +0x27c. Only bytes inside section 10 change; the offset table's
  // end entries follow a length change, so the unit's own bytes stay as they were everywhere else.
  var COLOURS = ["Auto", "White", "Red", "Dark Orange", "Light Orange", "Yellow", "Green", "Turquoise", "Blue", "Violet", "Pink", "Off"];
  var NAME_MAX = 10;
  function mapEntries(b, p) {       // [{k, ks, vs, ve}] of the map at p, and where it ends
    var t = b[p], n, q, dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    if ((t & 0xf0) === 0x80) { n = t & 15; q = p + 1; }
    else if (t === 0xde) { n = dv.getUint16(p + 1); q = p + 3; }
    else throw fail("preset: a map was expected");
    var out = [];
    for (var i = 0; i < n; i++) { var k = dec(b, q), v = dec(b, k[1]); out.push({ k: k[0], ks: q, vs: k[1], ve: v[1] }); q = v[1]; }
    return { entries: out, end: q };
  }
  function arrayItems(b, p) {
    var t = b[p], n, q, dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    if ((t & 0xf0) === 0x90) { n = t & 15; q = p + 1; }
    else if (t === 0xdc) { n = dv.getUint16(p + 1); q = p + 3; }
    else throw fail("preset: an array was expected");
    var out = [];
    for (var i = 0; i < n; i++) { var e = dec(b, q)[1]; out.push({ s: q, e: e }); q = e; }
    return out;
  }
  function layout(blob) {           // where everything editable is
    if (text(blob.slice(1, 9)) !== "l6-helix") throw fail("that isn't a POD Go preset");
    var p = dec(blob, 0)[1], tableAt = p, root = dec(blob, p)[1];
    var top = mapEntries(blob, root), s10 = top.entries.find(function (e) { return e.k === 10; });
    if (!s10) throw fail("preset: no snapshot section");
    var sec = mapEntries(blob, s10.vs), list = sec.entries.find(function (e) { return e.k === 10; });
    var stock = arrayItems(blob, list.vs).map(function (it) {
      var m = mapEntries(blob, it.s), nm = m.entries.find(function (e) { return e.k === 4; }), col = m.entries.find(function (e) { return e.k === 12; });
      return { name: nm, colour: col };
    });
    var s56 = snapshots56(blob), recs = [];
    if (s56) {
      var j = 0;
      for (var i = 0; i < 3; i++) if (s56.mask >> i & 1) { recs.push({ snapshot: i + 4, at: s56.at + 9 + j * RECSZ }); j++; }
    }
    return { tableAt: tableAt, stock: stock, holder: s56 ? s56.holder : 4, recs: recs, has56: !!s56 };
  }
  function snapshotList(blob) {     // [{ snapshot, name, colour, where }] for 1-6 (5 and 6 only when the preset carries them)
    var L = layout(blob), out = [];
    L.stock.forEach(function (st, i) {
      var nm = dec(blob, st.name.vs)[0], col = st.colour ? dec(blob, st.colour.vs)[0] : 0;
      out.push({ snapshot: i < 3 ? i + 1 : L.holder, name: text(nm), colour: col, where: { stock: i } });
    });
    L.recs.forEach(function (r) {
      out.push({ snapshot: r.snapshot, name: text(blob.subarray(r.at + NAME, r.at + NAME + 11)), colour: blob[r.at + COLOR], where: { rec: r.snapshot } });
    });
    out.sort(function (a, b) { return a.snapshot - b.snapshot; });
    return { snapshots: out, has56: L.has56 };
  }
  function cleanName(name) {
    var s = String(name).replace(/[^\x20-\x7e]/g, "").slice(0, NAME_MAX);
    return new TextEncoder().encode(s);
  }
  function setSnapshot(blob, snapshot, name, colour) {   // a new blob with that snapshot's name and/or colour changed
    var L = layout(blob), b = blob.slice();
    var rec = L.recs.find(function (r) { return r.snapshot === snapshot; });
    var si = snapshot <= 3 ? snapshot - 1 : (snapshot === L.holder ? 3 : -1);
    if (rec) {
      if (name !== null && name !== undefined) { var n = cleanName(name), f = new Uint8Array(11); f.set(n); b.set(f, rec.at + NAME); }
      if (colour !== null && colour !== undefined) b[rec.at + COLOR] = colour;
      return b;
    }
    if (si < 0) throw fail("snapshot " + snapshot + " isn't in this preset");
    var st = L.stock[si];
    if (colour !== null && colour !== undefined) {
      if (!st.colour) throw fail("preset: snapshot " + snapshot + " has no colour entry");
      if (st.colour.ve - st.colour.vs !== 1 || b[st.colour.vs] > 0x7f) throw fail("preset: unexpected colour encoding");
      b[st.colour.vs] = colour;
    }
    if (name !== null && name !== undefined) {
      var nb = concat([cleanName(name), Uint8Array.of(0)]);         // as the unit writes it: text and a NUL
      var enc = concat([nb.length < 32 ? Uint8Array.of(0xa0 | nb.length) : Uint8Array.of(0xd9, nb.length), nb]);
      var delta = enc.length - (st.name.ve - st.name.vs);
      b = concat([b.subarray(0, st.name.vs), enc, b.subarray(st.name.ve)]);
      if (delta) {                                  // section 10 is the last: only the table's end entries move
        var tv = new DataView(b.buffer, b.byteOffset + L.tableAt + 3, 48);
        for (var w = 10; w < 12; w++) tv.setUint32(4 * w, tv.getUint32(4 * w, true) + delta, true);
      }
    }
    return b;
  }

  async function connect(usb, opts) {
    opts = opts || {};
    if (!usb) throw fail("This browser has no WebUSB: use Chrome or Edge on a computer.", "nousb");
    var kinds = opts.devices || [DEVICES[0]];
    var match = function (d) { return kinds.find(function (k) { return d.vendorId === k.vendorId && d.productId === k.productId; }); };
    var dev = (await usb.getDevices()).find(match);
    if (!dev) dev = await usb.requestDevice({ filters: kinds.map(function (k) { return { vendorId: k.vendorId, productId: k.productId }; }) });
    var kind = match(dev) || DEVICES[0];
    await dev.open();
    if (dev.configuration === null) await dev.selectConfiguration(1);
    try { await dev.claimInterface(0); }
    catch (e) { try { await dev.close(); } catch (x) { /* */ } throw fail("Another program has the " + kind.name + ": quit POD Go Edit, HX Edit and Line 6 Updater, then try again.", "busy"); }
    var alt = dev.configuration.interfaces[0].alternate, epIn = null, epOut = null, mtu = 512;
    alt.endpoints.forEach(function (e) {
      if (e.type !== "bulk") return;
      if (e.direction === "in") { epIn = e.endpointNumber; mtu = e.packetSize; } else epOut = e.endpointNumber;
    });
    if (epIn === null || epOut === null) throw fail("the POD Go's USB interface isn't the one expected");
    var link = new Link(dev, epOut, epIn, mtu, opts.log);
    link.start();
    await sleep(500);                                   // stale inbound data goes to no stream
    var pg = new PodGo(link);
    pg.device = kind;
    try { await pg.open(); } catch (e) { await link.close(); throw e; }
    return pg;
  }

  root.PODGOUSB = { connect: connect, DEVICES: DEVICES, MP: MP, snapshots56: snapshots56, snapshotList: snapshotList, setSnapshot: setSnapshot,
                    COLOURS: COLOURS, NAME_MAX: NAME_MAX, text: text, CMD: CMD, K: K, APP: APP };
})(typeof self !== "undefined" ? self : this);
