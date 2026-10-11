import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { readFile, lstat } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { WebSocketServer, createWebSocketStream } from 'ws';

const root = path.dirname(fileURLToPath(import.meta.url));
export async function serviceCall(socketPath, operation, ...args) {
  for (const [name, isSocket] of [[path.dirname(socketPath), false], [socketPath, true]]) {
    const info = await lstat(name);
    if (info.uid !== process.getuid() || (info.mode & 0o077) ||
        !(isSocket ? info.isSocket() : info.isDirectory())) {
      throw new Error('The service socket and its parent must be owned and private.');
    }
  }
  return new Promise((resolve, reject) => {
    const socket = net.createConnection(socketPath);
    let data = Buffer.alloc(0);
    const fail = error => { socket.destroy(); reject(error); };
    socket.setTimeout(60000, () => fail(new Error('Session service timed out. Inspect the app before retrying.')));
    socket.on('error', fail);
    socket.on('connect', () => socket.write(JSON.stringify({ operation, args }) + '\n'));
    socket.on('data', chunk => {
      data = Buffer.concat([data, chunk]);
      if (data.length > 1024 * 1024) return fail(new Error('Oversized service response.'));
      const end = data.indexOf(10);
      if (end < 0) return;
      try {
        const response = JSON.parse(data.subarray(0, end).toString());
        if (response.error) throw new Error(response.error);
        resolve(response.result);
        socket.destroy();
      } catch (error) { fail(error); }
    });
    socket.on('end', () => fail(new Error('Session service disconnected.')));
  });
}

export function tailscaleAddress() {
  const address = execFileSync('tailscale', ['ip', '-4'], { encoding: 'utf8', timeout: 10000 }).trim();
  const octets = address.split('.').map(Number);
  if (!/^100\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(address) ||
      octets.some(n => n > 255) || octets[1] < 64 || octets[1] > 127) {
    throw new Error('Cannot find a Tailscale IPv4 address. Connect this host to your tailnet first.');
  }
  return address;
}

export function createViewer({ socketPath, host = '127.0.0.1', hostname, tlsCert, tlsKey }) {
  const scheme = tlsCert ? 'https' : 'http';
  const token = randomBytes(32).toString('base64url');
  const hosts = new Set(['localhost', '127.0.0.1', '[::1]', host, ...(hostname ? [hostname] : [])]);
  const authorized = supplied => typeof supplied === 'string' &&
    Buffer.byteLength(supplied) === Buffer.byteLength(token) &&
    timingSafeEqual(Buffer.from(supplied), Buffer.from(token));
  const trusted = request => {
    try {
      const url = new URL('http://' + request.headers.host);
      return hosts.has(url.hostname) && url.host === request.headers.host && !url.username && !url.password;
    } catch { return false; }
  };
  const sameOrigin = request => !request.headers.origin || request.headers.origin === scheme + '://' + request.headers.host;
  const respond = (response, status, data, type = 'application/json') => {
    const body = Buffer.isBuffer(data) ? data : Buffer.from(JSON.stringify(data));
    response.writeHead(status, {
      'Content-Type': type, 'Content-Length': body.length, 'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    });
    response.end(body);
  };
  const handler = async (request, response) => {
    if (!trusted(request) || !sameOrigin(request)) return respond(response, 403, { error: 'Invalid viewer host or origin.' });
    try {
      if (request.method === 'GET') {
        let asset;
        if (request.url === '/') asset = path.join(root, 'viewer.html');
        else if (request.url === '/viewer.js') asset = path.join(root, 'viewer.js');
        else if (/^\/novnc\/(core|vendor)\/[a-zA-Z0-9_./-]+\.js$/.test(request.url) && !request.url.includes('..')) {
          asset = path.join(root, 'node_modules/@novnc/novnc', request.url.slice(7));
        }
        if (!asset) return respond(response, 404, { error: 'Not found.' });
        return respond(response, 200, await readFile(asset), asset.endsWith('.html') ? 'text/html; charset=utf-8' : 'text/javascript; charset=utf-8');
      }
      if (request.method !== 'POST' || !['/api/apps', '/api/text'].includes(request.url)) return respond(response, 404, { error: 'Not found.' });
      if (!authorized(request.headers.authorization?.replace(/^Bearer /, ''))) return respond(response, 401, { error: 'Open the private viewer link.' });
      if (request.headers['content-type'] !== 'application/json') return respond(response, 400, { error: 'Expected application/json.' });
      const chunks = [];
      let length = 0;
      for await (const chunk of request) {
        length += chunk.length;
        if (length > 65536) return respond(response, 413, { error: 'Request too large.' });
        chunks.push(chunk);
      }
      let input;
      try { input = JSON.parse(Buffer.concat(chunks).toString()); } catch { return respond(response, 400, { error: 'Invalid JSON.' }); }
      if (!input || typeof input !== 'object' || Array.isArray(input)) return respond(response, 400, { error: 'Expected an object.' });
      if (request.url === '/api/apps') return respond(response, 200, await serviceCall(socketPath, 'list_apps'));
      if (typeof input.app !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(input.app) ||
          typeof input.text !== 'string' || input.text.length > 10000 || input.text.includes('\0')) {
        return respond(response, 400, { error: 'Invalid app or text.' });
      }
      respond(response, 200, await serviceCall(socketPath, 'send_text', input.app, input.text));
    } catch (error) {
      respond(response, error.code === 'ENOENT' && request.method === 'GET' ? 404 : 503, { error: error.message });
    }
  };
  const server = tlsCert
    ? https.createServer({ cert: readFileSync(tlsCert), key: readFileSync(tlsKey) }, handler)
    : http.createServer(handler);
  server.requestTimeout = 15000;
  const wss = new WebSocketServer({ noServer: true, maxPayload: 1024 * 1024, perMessageDeflate: false });
  server.on('upgrade', (request, socket, head) => {
    if (!trusted(request) || request.headers.origin !== scheme + '://' + request.headers.host || request.url !== '/stream') {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
      return;
    }
    wss.handleUpgrade(request, socket, head, ws => {
      // Authenticate in the first frame, keeping the token out of URLs and logs.
      const timer = setTimeout(() => ws.terminate(), 5000);
      ws.once('close', () => clearTimeout(timer));
      ws.once('error', () => ws.terminate());
      ws.once('message', async (data, binary) => {
        ws.pause();
        let target;
        try {
          const auth = JSON.parse(data.toString());
          if (binary || !authorized(auth.token) || typeof auth.app !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(auth.app)) throw new Error('Unauthorized.');
          target = await serviceCall(socketPath, 'vnc_endpoint', auth.app);
          if (target.host !== '127.0.0.1' || !Number.isInteger(target.port) || target.port < 1 || target.port > 65535) throw new Error('Invalid owned app endpoint.');
        } catch { clearTimeout(timer); ws.resume(); ws.close(1008, 'Cannot attach to this app.'); return; }
        if (ws.readyState !== ws.OPEN) return;
        const tcp = net.createConnection({ host: target.host, port: target.port });
        ws.once('close', () => tcp.destroy());
        tcp.once('error', () => { ws.resume(); ws.close(1011, 'App connection lost.'); });
        tcp.setTimeout(5000, () => tcp.destroy(new Error('App connection timed out.')));
        tcp.once('connect', () => {
          clearTimeout(timer);
          tcp.setTimeout(0);
          if (ws.readyState !== ws.OPEN) { tcp.destroy(); return; }
          ws.send(JSON.stringify({ ready: true }));
          const stream = createWebSocketStream(ws, { encoding: null });
          stream.on('error', () => tcp.destroy());
          tcp.once('close', () => ws.close());
          // Stream piping applies backpressure in both directions.
          stream.pipe(tcp).pipe(stream);
          ws.resume();
        });
      });
    });
  });
  return {
    server, token,
    async close() {
      for (const ws of wss.clients) ws.terminate();
      wss.close();
      server.closeAllConnections();
      await new Promise(resolve => server.close(resolve));
    },
  };
}

export function parseOptions(args) {
  const options = { host: '127.0.0.1', port: 6080 };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--connect') {
      const value = args[++i];
      if (!value || value.startsWith('--')) throw new Error('Provide --connect SOCKET.');
      options.socketPath = path.resolve(value);
    }
    else if (args[i] === '--port') {
      const value = args[++i];
      if (!/^\d+$/.test(value ?? '')) throw new Error('Invalid port.');
      options.port = Number(value);
    } else if (['--tls-cert', '--tls-key', '--hostname'].includes(args[i])) {
      const flag = args[i], value = args[++i];
      if (!value || value.startsWith('--')) throw new Error('Missing value for ' + flag);
      options[{ '--tls-cert': 'tlsCert', '--tls-key': 'tlsKey', '--hostname': 'hostname' }[flag]] = value;
    } else if (args[i] === '--tailscale') options.host = tailscaleAddress();
    else if (args[i] === '--help' || args[i] === '-h') return null;
    else throw new Error('Unknown option: ' + args[i]);
  }
  if (!options.socketPath || !Number.isInteger(options.port) || options.port > 65535) throw new Error('Provide --connect SOCKET and a port from 0 to 65535.');
  if (!!options.tlsCert !== !!options.tlsKey) throw new Error('Provide both --tls-cert and --tls-key.');
  if (options.hostname && !/^[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$/.test(options.hostname)) throw new Error('Invalid hostname.');
  return options;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const options = parseOptions(process.argv.slice(2));
    if (!options) console.log('Usage: cage-web --connect SOCKET [--port PORT] [--tailscale] [--tls-cert CERT --tls-key KEY] [--hostname NAME]');
    else {
      await serviceCall(options.socketPath, 'list_apps');
      const viewer = createViewer(options);
      viewer.server.on('error', error => { console.error(error.message); process.exitCode = 1; });
      viewer.server.listen(options.port, options.host, () => {
        console.log(`Cage browser access: ${options.tlsCert ? 'https' : 'http'}://${options.hostname || options.host}:${viewer.server.address().port}/#${viewer.token}`);
      });
      const stop = () => viewer.close();
      process.once('SIGTERM', stop);
      process.once('SIGINT', stop);
    }
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
