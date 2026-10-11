import RFB from '/novnc/core/rfb.js';

const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('cage-token') || '';
if (location.hash) {
  sessionStorage.setItem('cage-token', token);
  history.replaceState(null, '', location.pathname);
}
let selected = '', rfb = null, socket = null, generation = 0, listing = false;
function message(text, error = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}
async function api(endpoint, body) {
  const response = await fetch('/api/' + endpoint, {
    method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal: AbortSignal.timeout(65000),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed.');
  return result;
}
function connect(app) {
  const version = ++generation;
  rfb?.disconnect();
  socket?.close();
  rfb = null;
  selected = app;
  $('viewer').hidden = !app;
  $('empty').hidden = !!app;
  if (!app) { message('Waiting for an app'); return; }
  message('Connecting…');
  const channel = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/stream`);
  socket = channel;
  channel.binaryType = 'arraybuffer';
  channel.addEventListener('open', () => channel.send(JSON.stringify({ token, app })));
  channel.addEventListener('error', () => {
    if (version === generation) message('Connection failed. Use Reconnect to try again.', true);
  });
  channel.addEventListener('close', () => {
    if (version === generation) message('Disconnected. Use Reconnect to try again.', true);
  });
  channel.addEventListener('message', function ready(event) {
    if (version !== generation) { channel.close(); return; }
    try {
      if (typeof event.data !== 'string' || !JSON.parse(event.data).ready) throw new Error();
    } catch { channel.close(); message('Invalid viewer handshake.', true); return; }
    channel.removeEventListener('message', ready);
    const client = new RFB($('screen'), channel, { shared: true });
    rfb = client;
    client.scaleViewport = true;
    client.resizeSession = false;
    client.addEventListener('connect', () => {
      if (version === generation) message('Connected · live');
    });
    client.addEventListener('disconnect', () => {
      if (version === generation) { rfb = null; message('Disconnected. Use Reconnect to try again.', true); }
    });
    client.addEventListener('securityfailure', () => {
      if (version === generation) message('VNC security negotiation failed.', true);
    });
  });
}
async function listApps() {
  if (listing) return;
  listing = true;
  try {
    const apps = (await api('apps', {})).filter(app => app.isRunning);
    $('apps').replaceChildren(...apps.map(app => new Option(app.displayName + ' · ' + app.id.slice(0, 8), app.id)));
    if (!apps.length) $('apps').add(new Option('No running apps', ''));
    const next = apps.some(app => app.id === selected) ? selected : (apps[0]?.id || '');
    $('apps').value = next;
    if (next !== selected) connect(next);
    else if (!next) message('Waiting for an app');
  } catch (error) { message(error.message, true); }
  finally { listing = false; }
}
$('apps').addEventListener('change', () => connect($('apps').value));
$('refresh').addEventListener('click', () => connect(selected));
const keysyms = { Tab: 0xff09, 'shift+Tab': 0xff09, Return: 0xff0d, Escape: 0xff1b, 'ctrl+a': 0x61 };
document.querySelectorAll('[data-key]').forEach(button => button.addEventListener('click', () => {
  if (!rfb) return;
  const chord = button.dataset.key;
  const modifier = chord.startsWith('shift+') ? 0xffe1 : chord.startsWith('ctrl+') ? 0xffe3 : null;
  if (modifier) rfb.sendKey(modifier, '', true);
  rfb.sendKey(keysyms[chord], '', true);
  rfb.sendKey(keysyms[chord], '', false);
  if (modifier) rfb.sendKey(modifier, '', false);
  rfb.focus();
}));
let textPending = false;
async function sendText(text) {
  if (!selected || !rfb || textPending || !text) return;
  textPending = true;
  try { await api('text', { app: selected, text }); }
  catch (error) { message(error.message + ' Inspect the app before retrying.', true); }
  finally { textPending = false; }
}
$('send').addEventListener('submit', async event => {
  event.preventDefault();
  const text = $('text').value;
  $('text').value = '';
  await sendText(text);
  rfb?.focus();
});
$('screen').addEventListener('paste', event => {
  event.preventDefault();
  sendText(event.clipboardData.getData('text/plain'));
});
window.addEventListener('pagehide', () => { ++generation; rfb?.disconnect(); socket?.close(); });
listApps();
setInterval(() => { if (!document.hidden) listApps(); }, 3000);
