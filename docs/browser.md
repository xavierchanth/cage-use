# Browser access

`cage-web` lets you view and control apps owned by a persistent Cage session
service, including signing in yourself before handing an app back to the agent.
The Node gateway serves a packaged noVNC web client and bridges its WebSocket
connection to the app’s existing WayVNC server. Frames update as the app changes;
mouse and keyboard input travel over the same persistent connection. Browser
assets are served locally, with no CDN or client installation. The complete Nix
package includes Node, `ws`, and noVNC. MCP keeps its screenshot-based interface.

## Connect to the agent's apps

Start a [persistent session service](mcp.md#persistent-sessions) and configure
the agent to use `cage-mcp --connect SOCKET`. On the Cage host, run:

```sh
cage-web --connect /run/user/UID/cage-use/worker.sock
```

Use the same socket as the agent. The command prints a private link like
`http://127.0.0.1:6080/#TOKEN`. Open that link in your browser and select an app.
Apps launched by the agent appear automatically. Plain stdio-owned apps and
standalone `cage-session` apps are not part of this service.

Click inside the app to focus your keyboard. You can click, drag, right-click,
scroll, type, and send shortcuts. Paste local clipboard text into **Send text**,
then select **Send**. The buttons above the app
send common keys. The **Send text** field hides its contents and sends them to
the app's focused field; **Enter** submits a form when the app accepts it.
noVNC scales the display and translates pointer coordinates to the app’s pixels.
The **Reconnect** button starts a new connection without restarting the app.

Browser mouse and keyboard input go directly to WayVNC and do not capture a
screenshot after every action. **Send text** uses the session service’s Unicode
typing operation without taking a screenshot. Both the agent and viewer can
send input concurrently, so ask the agent to wait while you sign in and tell it
when you finish.
Screenshots and any active recordings include the app during sign-in.

Closing the browser or stopping `cage-web` leaves the apps running. The agent
can resume through its existing MCP connection. App lifetime belongs to the
session service, which closes its apps when stopped.

## Remote hosts

### Tailscale

If the Cage host and your browser's machine are connected to your tailnet, run
this on the Cage host:

```sh
cage-web --connect /run/user/UID/cage-use/worker.sock --tailscale
```

The viewer uses `tailscale ip -4` to find this host's address and prints a
private link such as `http://100.x.y.z:6080/#TOKEN`. Open the link directly
from your other tailnet device. No SSH tunnel is needed. The listener binds
only that Tailscale address. The access token is still required, and your
tailnet's access rules must permit the connection to the chosen port.
Tailscale encrypts the network traffic; the viewer itself serves HTTP.

The host must already have the `tailscale` CLI on its PATH and be connected
using native Tailscale networking. The viewer does not install Tailscale,
change tailnet configuration, or publish the port through Funnel. Use the
printed IP link, or provide `--hostname NAME` to allow and print a specific
MagicDNS hostname. This changes the access link, not the listener address.

### HTTPS

noVNC expects a secure browser context. Loopback URLs (including SSH forwarding)
provide one. Basic display and keyboard/mouse control also work on the Tailscale
HTTP URL with the current unauthenticated, loopback-only WayVNC backend, but
noVNC reports a secure-context warning. For remote use, configure HTTPS with an
existing certificate and key, for example a Tailscale certificate for the host:

```sh
cage-web --connect /run/user/UID/cage-use/worker.sock --tailscale \
  --hostname HOST.TAILNET.ts.net --tls-cert /path/to/cert.crt --tls-key /path/to/cert.key
```

The command prints an `https://` link and the browser uses `wss://` for the live
stream. The certificate must match the hostname and be trusted by your browser.
The viewer does not obtain or renew certificates. The listener still binds only
the selected Tailscale address.

### SSH forwarding

Run `cage-web` on the remote host, then forward its loopback port from your
local machine:

```sh
ssh -N -L 6080:127.0.0.1:6080 HOST
```

Open the printed private link in your local browser. The app and its browser
profile remain on the Cage host. The SSH tunnel carries viewer traffic.

Use `cage-web --connect SOCKET --port 6081` to change the remote port, or
`--port 0` to pick a free port and print it. If the local port is occupied,
forward another one (`-L 6082:127.0.0.1:6080`) and change the port in the
printed link to `6082`, preserving its `#TOKEN` fragment.

By default the listener binds `127.0.0.1`; `--tailscale` selects the host's
tailnet IPv4 address instead. Each viewer process creates a random
access token that authorizes viewing and input for all apps in its connected
service. It prints the token only in the link's fragment; the page removes that
fragment and keeps the token in the current tab's session storage for reloads.
API calls require the token. WebSocket connections authenticate in their first
message, keeping the token out of request URLs. Both transports reject other
website origins and hostnames other than loopback, the selected Tailscale
address, or an explicitly configured `--hostname`. The browser can attach only
to live apps owned by the connected service; it cannot choose an arbitrary VNC
host or port. Keep the link private. Restarting `cage-web` replaces the token;
open the newly printed link to reconnect.

The viewer does not launch or close apps, download files, or transfer a remote
clipboard back to the local machine. Local clipboard text can be pasted into
the app. For composition input or mobile keyboards, use **Send text**.

## Validation

`web/test.mjs` exercises HTTP and WebSocket authentication, host/origin checks,
locally served assets, app discovery, bidirectional binary streaming, input
validation, and service ownership across viewer shutdown. `tests/cage-web.py`
checks that VNC endpoints belong to live owned apps and Unicode input does not
capture a screenshot. Both run as Nix checks.

For development, run `bun install` in `web/`, then
`node web/server.mjs --connect SOCKET` from the repository root. Run gateway
tests with `node --test web/test.mjs`. Restart an older session service before
using the streaming viewer: it needs the new `vnc_endpoint` and `send_text`
operations.
