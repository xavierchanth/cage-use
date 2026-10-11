import { test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import net from 'node:net';
import http from 'node:http';
import https from 'node:https';
import { execFileSync } from 'node:child_process';
import { mkdtemp, chmod, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import WebSocket from 'ws';
import { createViewer, parseOptions, serviceCall } from './server.mjs';

test('authenticated owned-app streaming and viewer cleanup', { timeout: 15000 }, async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cage-stream-test-'));
  await chmod(directory, 0o700);
  const socketPath = path.join(directory, 'worker.sock');
  const calls = [];
  const connections = new Set();
  const vnc = net.createServer(socket => {
    connections.add(socket);
    socket.once('close', () => connections.delete(socket));
    socket.write('RFB 003.008\n');
    socket.on('data', bytes => socket.write(bytes));
  });
  vnc.listen(0, '127.0.0.1');
  await once(vnc, 'listening');
  const service = net.createServer(socket => {
    let data = '';
    socket.on('data', chunk => {
      data += chunk;
      if (!data.endsWith('\n')) return;
      const { operation, args } = JSON.parse(data);
      calls.push({ operation, args });
      let result;
      if (operation === 'list_apps') result = [{ id: 'owned', displayName: 'firefox', isRunning: true }];
      else if (operation === 'vnc_endpoint' && args[0] === 'owned') result = { host: '127.0.0.1', port: vnc.address().port };
      else if (operation === 'send_text' && args[0] === 'owned') result = { sent: true };
      socket.end(JSON.stringify(result ? { result } : { error: 'Unknown app ID.' }) + '\n');
    });
  });
  service.listen(socketPath);
  await once(service, 'listening');
  await chmod(socketPath, 0o600);
  const viewer = createViewer({ socketPath });
  viewer.server.listen(0, '127.0.0.1');
  await once(viewer.server, 'listening');
  const base = `http://127.0.0.1:${viewer.server.address().port}`;
  const endpoint = base.replace('http:', 'ws:') + '/stream';
  t.after(async () => {
    await viewer.close();
    for (const socket of connections) socket.destroy();
    await Promise.all([new Promise(resolve => vnc.close(resolve)), new Promise(resolve => service.close(resolve))]);
    await rm(directory, { recursive: true, force: true });
  });
  const api = (url, body = {}, headers = {}) => fetch(base + url, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + viewer.token, ...headers }, body: JSON.stringify(body),
  });
  assert.equal((await fetch(base)).status, 200);
  assert.equal((await fetch(base + '/novnc/core/rfb.js')).status, 200);
  assert.equal((await fetch(base + '/novnc/core/missing.js')).status, 404);
  assert.equal((await api('/api/apps', {}, { Authorization: 'Bearer wrong' })).status, 401);
  assert.equal((await api('/api/apps', {}, { Origin: 'http://other.example' })).status, 403);
  const badHost = await new Promise(resolve => {
    const request = http.request(base + '/api/apps', { method: 'POST', headers: { Host: 'other.example' } }, response => {
      response.resume();
      resolve(response.statusCode);
    });
    request.end('{}');
  });
  assert.equal(badHost, 403);
  assert.equal(calls.length, 0);
  assert.equal((await (await api('/api/apps')).json())[0].id, 'owned');
  assert.equal((await api('/api/text', { app: 'owned', text: 'Unicode 🐦 $(literal)' })).status, 200);
  assert.deepEqual(calls.at(-1), { operation: 'send_text', args: ['owned', 'Unicode 🐦 $(literal)'] });
  assert.equal((await api('/api/text', { app: 'owned', text: '\0' })).status, 400);
  assert.equal((await api('/api/text', { app: 'owned', text: 'x'.repeat(10001) })).status, 400);
  const rejected = new WebSocket(endpoint, { origin: 'http://other.example' });
  rejected.on('error', () => {});
  const [, response] = await once(rejected, 'unexpected-response');
  assert.equal(response.statusCode, 403);
  rejected.terminate();
  for (const auth of [{ token: 'wrong', app: 'owned' }, { token: viewer.token, app: 'unknown' }]) {
    const socket = new WebSocket(endpoint, { origin: base });
    await once(socket, 'open');
    const closed = once(socket, 'close');
    socket.send(JSON.stringify(auth));
    assert.equal((await closed)[0], 1008);
  }
  assert.equal(connections.size, 0);
  const socket = new WebSocket(endpoint, { origin: base });
  await once(socket, 'open');
  const received = [];
  socket.on('message', (bytes, binary) => received.push({ bytes, binary }));
  const ready = once(socket, 'message');
  socket.send(JSON.stringify({ token: viewer.token, app: 'owned' }));
  assert.deepEqual(JSON.parse((await ready)[0]), { ready: true });
  while (received.length < 2) await once(socket, 'message');
  assert.equal(received[1].binary, true);
  assert.equal(received[1].bytes.toString(), 'RFB 003.008\n');
  const echoed = once(socket, 'message');
  const input = Buffer.from([0, 255, 17, 0, 127]);
  socket.send(input);
  assert.deepEqual((await echoed)[0], input);
  const closed = once(socket, 'close');
  await viewer.close();
  await closed;
  assert.equal((await serviceCall(socketPath, 'list_apps'))[0].id, 'owned');
  assert.ok(!calls.some(call => ['capture', 'interact', 'close'].includes(call.operation)));
});

test('CLI rejects invalid options', () => {
  assert.equal(parseOptions(['--connect', '/tmp/private/worker.sock', '--port', '0']).port, 0);
  for (const value of ['-1', '65536', '1.5', 'abc', '']) {
    assert.throws(() => parseOptions(['--connect', '/tmp/private/worker.sock', '--port', value]));
  }
  assert.throws(() => parseOptions([]));
  assert.throws(() => parseOptions(['--other']));
  assert.throws(() => parseOptions(['--connect']));
  assert.throws(() => parseOptions(['--connect', '/tmp/private/worker.sock', '--tls-cert', '/tmp/cert']));
  assert.throws(() => parseOptions(['--connect', '/tmp/private/worker.sock', '--hostname', 'bad/path']));
});

test('HTTPS assets and WSS origin enforcement', { timeout: 15000 }, async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cage-tls-test-'));
  const tlsCert = path.join(directory, 'cert.pem'), tlsKey = path.join(directory, 'key.pem');
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost',
    '-days', '1', '-keyout', tlsKey, '-out', tlsCert], { stdio: 'ignore' });
  const viewer = createViewer({ socketPath: '/unused', tlsCert, tlsKey, hostname: 'localhost' });
  viewer.server.listen(0, '127.0.0.1');
  await once(viewer.server, 'listening');
  t.after(async () => { await viewer.close(); await rm(directory, { recursive: true, force: true }); });
  const base = `https://localhost:${viewer.server.address().port}`;
  const status = await new Promise((resolve, reject) => {
    const request = https.get(base, { rejectUnauthorized: false }, response => {
      response.resume(); resolve(response.statusCode);
    });
    request.on('error', reject);
  });
  assert.equal(status, 200);
  const rejected = new WebSocket(base.replace('https:', 'wss:') + '/stream', { origin: base.replace('https:', 'http:'), rejectUnauthorized: false });
  rejected.on('error', () => {});
  const [, response] = await once(rejected, 'unexpected-response');
  assert.equal(response.statusCode, 403);
  rejected.terminate();
  const allowed = new WebSocket(base.replace('https:', 'wss:') + '/stream', { origin: base, rejectUnauthorized: false });
  await once(allowed, 'open');
  const closed = once(allowed, 'close');
  allowed.send(JSON.stringify({ token: 'wrong', app: 'owned' }));
  assert.equal((await closed)[0], 1008);
});
