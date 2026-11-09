// firmware-worker.js (POD Go) - podgo/build_podgo.py in the browser: the stock POD Go 2.50 .hxf in, the
// .hxf with NAM A2 Lite out. Pyodide runs the repository's own Python tools: the kernel (nam_multi.py,
// without --check: the simulator run takes minutes here), build_podgo.make_image (the same function the
// desktop build calls), l6ia_verify.py and hxf.py pack. The result's MD5 is compared with the build the
// project tested (build_podgo.BUILT_MD5): a match means these are the very bytes that ran on a POD Go.
//
// Messages in:  { stock: ArrayBuffer, edition: bool, names: bool }   (names: the Model knob shows the IR's name, podgo/model_names.py)
//   (edition: the NAM A2 Edition boot screens, art/nam-a2-edition/,
//                                                       drawn over the boot screens of the user's own file)
// Messages out: { type: "progress", step, of, text } | { type: "log", text }
//               { type: "done", file, bytes: ArrayBuffer, md5, pinned } | { type: "error", text }
"use strict";

var PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

// tests/test_podgo_build.py keeps these equal to podgo/build_podgo.py.
var STOCK_MD5 = "e0ea3e1ed32f0f353b79f6ad39631838";
var BUILT_MD5 = "61920a6cdb5342cecffcd968e1ae6ad1";
var KERNEL_ARGS = ["--mid-sweep", "--podgo", "--plexi", "--static-sdram", "--block32"];
var OUT_NAME = "POD_Go_v2.50.0_NAM_A2_Lite.hxf";
var BUILT_MD5_EDITION = "70cfd341bb4bf00422f7ea19c5b49e95";
var OUT_NAME_EDITION = "POD_Go_v2.50.0_NAM_A2_Lite_Edition.hxf";
var BUILT_MD5_NAMES = "2cb121444bfe5e4a9259903b7ea2dc83";
var BUILT_MD5_EDITION_NAMES = "0b27b025a84fc4a6d7af77f72f85d5ea";
var EDITION_SOURCES = ["podgo/splash.py", "art/nam-a2-edition/wired.png", "art/nam-a2-edition/wireless.png"];

// What the build needs, relative to the repository root.
var SOURCES = [
  "tools/hxf.py",
  "tools/l6ia.py",
  "tools/l6ia_verify.py",
  "tools/patch_amp.py",
  "tools/effects.py",
  "tools/kit_patch_amp.py",
  "tools/sharc/entry4_blob.py",
  "tools/sharc/nam_lite.py",
  "tools/sharc/nam_multi.py",
  "tools/sharc/nam_multi_kernel.asm",
  "tools/sharc/nam_pack.py",
  "tools/sharc/recips_table.json",
  "tools/sharc/sasm.py",
  "tools/sharc/ssim.py",
  "podgo/build_podgo.py",
  "podgo/podgo_model.py",
  "podgo/podgo_e2.py",
  "podgo/model_names.py",
];

var DRIVER = [
  "import contextlib, io, os, runpy, sys",
  "os.chdir('/repo')",
  "sys.path[:0] = ['/repo/podgo', '/repo/tools', '/repo/tools/sharc']",
  "def run(argv):",
  "    out = io.StringIO()",
  "    sys.argv = list(argv)",
  "    try:",
  "        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):",
  "            runpy.run_path(argv[0], run_name='__main__')",
  "    except SystemExit as e:",
  "        if e.code not in (None, 0):",
  "            raise RuntimeError(out.getvalue() + str(e.code))",
  "    return out.getvalue()",
  "def make(edition=False, names=False):",
  "    import build_podgo, patch_amp",
  "    out = io.StringIO()",
  "    with contextlib.redirect_stdout(out):",
  "        data, _ = patch_amp.load_l6ia_from_any('/repo/build/stock.hxf')",
  "        image = build_podgo.make_image(data, open('/repo/build/nam_lite.asm').read(),",
  "                                       splashes=build_podgo.EDITION if edition else None, model_names=names)",
  "    open('/repo/build/nam_lite.l6ia', 'wb').write(image)",
  "    return out.getvalue()",
].join("\n");

var py = null, editionLoaded = false;

function post(msg, transfer) { self.postMessage(msg, transfer || []); }
function progress(step, of, text) { post({ type: "progress", step: step, of: of, text: text }); }

async function boot() {
  if (py) return py;
  importScripts(PYODIDE + "pyodide.js");
  var p = await loadPyodide({ indexURL: PYODIDE });
  await p.loadPackage("numpy");
  var root = new URL("../../", self.location.href).href;
  var files = await Promise.all(SOURCES.map(async function (path) {
    var r = await fetch(root + path, { cache: "no-cache" });
    if (!r.ok) throw new Error("Could not load " + path + " (" + r.status + ").");
    return [path, new Uint8Array(await r.arrayBuffer())];
  }));
  ["/repo", "/repo/tools", "/repo/tools/sharc", "/repo/podgo", "/repo/build", "/repo/art", "/repo/art/nam-a2-edition"].forEach(function (d) {
    try { p.FS.mkdir(d); } catch (e) { /* exists */ }
  });
  files.forEach(function (f) { p.FS.writeFile("/repo/" + f[0], f[1]); });
  p.runPython(DRIVER);
  py = p;
  return p;
}

async function loadEdition(p) {
  if (editionLoaded) return;
  await p.loadPackage("pillow");
  var root = new URL("../../", self.location.href).href;
  for (var i = 0; i < EDITION_SOURCES.length; i++) {
    var r = await fetch(root + EDITION_SOURCES[i], { cache: "no-cache" });
    if (!r.ok) throw new Error("Could not load " + EDITION_SOURCES[i] + " (" + r.status + ").");
    p.FS.writeFile("/repo/" + EDITION_SOURCES[i], new Uint8Array(await r.arrayBuffer()));
  }
  editionLoaded = true;
}

async function build(stock, edition, names) {
  var of = 6;
  var outName = edition ? OUT_NAME_EDITION : OUT_NAME;
  if (names) outName = outName.replace(".hxf", "_Names.hxf");
  var pinnedMd5 = names ? (edition ? BUILT_MD5_EDITION_NAMES : BUILT_MD5_NAMES) : (edition ? BUILT_MD5_EDITION : BUILT_MD5);
  progress(1, of, "Loading the build tools (about 15 MB, once)…");
  var p = await boot();
  if (edition) await loadEdition(p);

  progress(2, of, "Checking your firmware file…");
  p.FS.writeFile("/repo/build/stock.hxf", new Uint8Array(stock));
  stock = null;
  var md5 = p.runPython("import hashlib; hashlib.md5(open('/repo/build/stock.hxf','rb').read()).hexdigest()");
  if (md5 !== STOCK_MD5) {
    try { p.FS.unlink("/repo/build/stock.hxf"); } catch (e) { /* gone */ }
    throw new Error("WRONG_FILE " + md5);
  }
  post({ type: "log", text: "stock firmware: POD Go 2.50 (MD5 " + md5 + ")\n" });

  var run = p.globals.get("run"), make = p.globals.get("make");
  function step(n, text, argv) {
    progress(n, of, text);
    post({ type: "log", text: "$ " + argv.join(" ") + "\n" });
    var out = run(p.toPy(argv));
    post({ type: "log", text: out });
    return out;
  }
  try {
    step(3, "Building the NAM kernel…", ["tools/sharc/nam_multi.py"].concat(KERNEL_ARGS, ["-o", "build/nam_lite.asm"]));
    progress(4, of, "Adding NAM A2 Lite to the model list…");
    post({ type: "log", text: "$ build_podgo.make_image\n" });
    post({ type: "log", text: make(!!edition, !!names) });
    var report = step(5, "Checking every checksum…", ["tools/l6ia_verify.py", "build/nam_lite.l6ia"]);
    if (report.indexOf("ALL OK") < 0) throw new Error("The built image failed its checksum check.");
    step(6, "Packing the file…", ["tools/hxf.py", "pack", "build/nam_lite.l6ia", "build/" + outName, "--donor", "build/stock.hxf"]);
  } finally {
    run.destroy();
    make.destroy();
  }
  var bytes = p.FS.readFile("/repo/build/" + outName);
  var outMd5 = p.runPython("import hashlib; hashlib.md5(open('/repo/build/" + outName + "','rb').read()).hexdigest()");
  ["stock.hxf", "nam_lite.l6ia", "nam_lite.asm", outName].forEach(function (f) {
    try { p.FS.unlink("/repo/build/" + f); } catch (e) { /* gone */ }
  });
  var buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  post({ type: "done", file: outName, bytes: buf, md5: outMd5, pinned: outMd5 === pinnedMd5, edition: !!edition, names: !!names }, [buf]);
}

self.onmessage = function (e) {
  build(e.data.stock, e.data.edition, e.data.names).catch(function (err) {
    post({ type: "error", text: err && err.message ? err.message : String(err) });
  });
};
