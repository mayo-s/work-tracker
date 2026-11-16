// Measures page loads of the Work Tracker in headless Chrome over the DevTools protocol (no packages: Node's own
// WebSocket): every request of dashboard, week, month and year, until the network is idle (README, "Measuring response
// times").
//
//   WT_LOGIN=… WT_PASSWORD=… node deploy/measure/pageload.mjs BASE_URL [ROUNDS] [IDLE_SECONDS]
//
// Logs in (an account without two-factor login) in a new browser context with an empty cache and loads the four pages
// ROUNDS times (default 3; round 1 is the first visit of each page). With IDLE_SECONDS it waits that long after the
// login, so the app's instances go away (e.g. 1200). Prints each load with its document and API calls (when sent, how
// long, and what the app says it took on a stage with WORK_TRACKER_TIMING=on), then the median per page.
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [BASE, ROUNDS = '3', IDLE = '0'] = process.argv.slice(2);
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = Number(process.env.CDP_PORT ?? 9334);
const PAGES = { dashboard: '/', week: '/week', month: '/month', year: '/year' };
const HEADER_CALLS = ['/api/auth/status', '/api/review/counts', '/api/audits'];  // not the page's own data
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'wt-pageload-'))}`, '--window-size=1280,900', '--no-first-run',
  '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
let version;
for (let i = 0; i < 50 && !version; i++) {
  try { version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); } catch { await sleep(200); }
}
if (!version) throw new Error(`Chrome did not start (CHROME=${CHROME})`);
const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((resolve) => ws.addEventListener('open', resolve));
let nextId = 0;
const pending = new Map();
let onEvent = () => undefined;
ws.addEventListener('message', ({ data }) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
  } else {
    onEvent(message);
  }
});
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const id = ++nextId;
  pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params, sessionId }));
});

const { browserContextId } = await send('Target.createBrowserContext');
const { targetId } = await send('Target.createTarget', { url: 'about:blank', browserContextId });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
await send('Network.enable', {}, sessionId);
await send('Page.enable', {}, sessionId);
await send('Runtime.enable', {}, sessionId);

/** The `Server-Timing` of a response, e.g. `app 84 ms, DynamoDB 51 ms (12 calls, 2293 items)`, with `first request of
 * the instance, 0.4 s after its start` where it is one: right after the start, this request had to wait for the
 * instance; long after, the instance was kept warm. */
function serverTiming(headers) {
  const header = Object.entries(headers).find(([name]) => name.toLowerCase() === 'server-timing')?.[1] ?? '';
  const metric = (name) => header.match(new RegExp(`${name};dur=([\\d.]+)(?:;desc="([^"]*)")?`));
  const [app, db, first] = [metric('app'), metric('db'), metric('first')];
  return [
    app ? `app ${Math.round(app[1])} ms` : '',
    db ? `DynamoDB ${Math.round(db[1])} ms (${db[2]})` : '',
    first ? `first request of the instance, ${(first[1] / 1000).toFixed(1)} s after its start` : '',
  ].filter(Boolean).join(', ');
}

/** Opens the page and answers its requests once the network was idle for 1.5 s (times in ms since the navigation). */
async function load(path) {
  const requests = new Map();
  let first = null;
  let open = 0;
  let lastChange = Date.now();
  onEvent = ({ method, params }) => {
    if (method === 'Network.requestWillBeSent') {
      first ??= params.timestamp;
      if (!requests.has(params.requestId)) open += 1;  // a redirect reuses the id
      requests.set(params.requestId, { url: params.request.url.replace(BASE, ''), start: params.timestamp });
    } else if (method === 'Network.responseReceived' && requests.has(params.requestId)) {
      Object.assign(requests.get(params.requestId), { status: params.response.status,
        timing: serverTiming(params.response.headers) });
    } else if ((method === 'Network.loadingFinished' || method === 'Network.loadingFailed') && requests.has(params.requestId)) {
      const request = requests.get(params.requestId);
      if (request.end === undefined) open -= 1;
      request.end = params.timestamp;
    } else {
      return;
    }
    lastChange = Date.now();
  };
  await send('Page.navigate', { url: BASE + path }, sessionId);
  const started = Date.now();
  while (Date.now() - started < 90_000 && (open > 0 || Date.now() - lastChange < 1500)) await sleep(50);
  onEvent = () => undefined;
  const ms = (time) => Math.round(((time ?? first) - first) * 1000);
  return [...requests.values()].map((request) => ({ ...request, start: ms(request.start), end: ms(request.end) }));
}

const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true },
  sessionId)).result.value;
const last = (requests) => Math.max(0, ...requests.map((request) => request.end));
const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

/** One page load: when the page's own data was there, when the network was idle, and each document and API call. */
function report(round, page, requests) {
  const api = requests.filter((request) => request.url.startsWith('/api/'));
  const files = requests.filter((request) => request.url.startsWith('/static/'));
  const data = last(api.filter((request) => !HEADER_CALLS.some((call) => request.url.startsWith(call))));
  console.log(`round ${round} ${page}: data after ${data} ms, idle after ${last(requests)} ms; ${files.length} static files, `
    + `the last after ${last(files)} ms`);
  for (const request of [requests[0], ...api]) {
    console.log(`    ${request.url.padEnd(44)} sent at ${String(request.start).padStart(5)}  took `
      + `${String(request.end - request.start).padStart(5)} ms  ${request.status}  ${request.timing ?? ''}`);
  }
  return { page, data, idle: last(requests) };
}

const loads = [];
try {
  await load('/login');
  const status = await evaluate(`fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(${JSON.stringify({ login: process.env.WT_LOGIN, password: process.env.WT_PASSWORD, code: null,
    remember: false })}) }).then((r) => r.status)`);
  if (status !== 200) throw new Error(`login: HTTP ${status}`);
  if (Number(IDLE)) await sleep(Number(IDLE) * 1000);
  for (let round = 1; round <= Number(ROUNDS); round++) {
    for (const [page, path] of Object.entries(PAGES)) {
      loads.push(report(round, page, await load(path)));
      if (/Loading…|could not be loaded/.test(await evaluate('document.querySelector("#app").innerText'))) {
        console.log('    the page did not show its data');
      }
    }
  }
  console.log('median');
  for (const page of Object.keys(PAGES)) {
    const own = loads.filter((item) => item.page === page);
    console.log(`  ${page.padEnd(9)} data after ${median(own.map((item) => item.data))} ms, idle after `
      + `${median(own.map((item) => item.idle))} ms`);
  }
} finally {
  chrome.kill();
}
process.exit(0);
