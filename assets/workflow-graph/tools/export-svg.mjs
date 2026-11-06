// Trigger the viewer's canonical SVG export in headless Chrome and capture it.
// Usage: node assets/archify/tools/export-svg.mjs <file.html> <downloadDir>
import { spawn } from "node:child_process";
import os from "node:os";
import { mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";

const [, , file, downloadDir] = process.argv;
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
rmSync(downloadDir, { recursive: true, force: true });
mkdirSync(downloadDir, { recursive: true });

const proc = spawn(
  chrome,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-crash-reporter",
    "--no-first-run",
    "--remote-debugging-port=9334",
    `--user-data-dir=${os.tmpdir()}/archify-export-profile`,
    "--window-size=1440,900",
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "ignore"] },
);

const sleep = (ms) => delay(ms);
let target = null;
for (let i = 0; i < 80 && !target; i += 1) {
  try {
    const res = await fetch("http://127.0.0.1:9334/json/list");
    const list = await res.json();
    target = list.find((t) => t.type === "page") || null;
  } catch {}
  if (!target) await sleep(100);
}
if (!target) throw new Error("chrome devtools not reachable");

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.onopen = resolve;
  ws.onerror = reject;
});
let seq = 0;
const pending = new Map();
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  }
};
function send(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

await send("Page.enable");
await send("Runtime.enable");
await send("Browser.setDownloadBehavior", {
  behavior: "allow",
  downloadPath: downloadDir,
});
await send("Page.navigate", { url: `file://${file}` });
await sleep(1500);
const evalRes = await send("Runtime.evaluate", {
  returnByValue: true,
  awaitPromise: true,
  expression: `(async () => {
    if (!window.Archify || !Archify.exportMenu) return 'no-export-api';
    try { await Archify.exportMenu.run('svg'); return 'ok'; } catch (e) { return 'error: ' + (e && e.message); }
  })()`,
});
console.log("run:", evalRes.result.value);

let found = null;
for (let i = 0; i < 100 && !found; i += 1) {
  const files = readdirSync(downloadDir).filter((f) => f.endsWith(".svg"));
  if (files.length) {
    found = files[0];
    if (statSync(`${downloadDir}/${found}`).size > 1000) break;
  }
  await sleep(100);
}
console.log("file:", found ? `${downloadDir}/${found}` : "not found");

ws.close();
proc.kill("SIGKILL");
process.exit(found ? 0 : 1);
