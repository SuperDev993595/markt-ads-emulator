import base64
import errno
import os
import socket
import subprocess
import threading
from urllib.parse import unquote, urlparse

# ===== YOUR PROXY CONFIG =====

PROXY_HOST = "ultra.marsproxies.com"
PROXY_PORT = 44443
USERNAME = "mr841096rRD"
PASSWORD = "daniel123_country-de_session-ydisdfqc_lifetime-59m"

# Local listener: bind all interfaces so the Android emulator can reach this process from the host.
# Chrome on this PC: use http://127.0.0.1:LOCAL_PORT (not "localhost" if you hit IPv6 issues).
LISTEN_HOST = "0.0.0.0"
LOCAL_PORT = 8888

# How the Android device reaches this PC's proxy (see set_adb_proxy()).
# "reverse" = adb reverse tcp:PORT tcp:PORT then device uses 127.0.0.1:PORT (recommended for LDPlayer / most emulators).
# "host_alias" = device uses 10.0.2.2:PORT (AVD-style; often broken on LDPlayer).
# "lan" = set MARKT_ADB_PROXY_HOST to your PC LAN IP (e.g. 192.168.1.5).
ADB_PROXY_MODE = os.environ.get("MARKT_ADB_PROXY_MODE", "reverse").strip().lower()
ADB_PROXY_HOST = os.environ.get("MARKT_ADB_PROXY_HOST", "").strip()
ADB_SERIAL = os.environ.get("MARKT_ADB_SERIAL", "").strip()


def _adb_exe() -> str:
    if os.environ.get("MARKT_ADB", "").strip():
        return os.environ["MARKT_ADB"].strip()
    try:
        import config

        p = getattr(config, "ADB_PATH", None)
        if isinstance(p, str) and p.strip():
            return p.strip()
    except ImportError:
        pass
    return "adb"


# Filled by set_adb_proxy() for accurate startup hints.
_last_device_proxy_host: str | None = None

# Background server (used by begin_proxy_session / end_proxy_session).
_proxy_stop = threading.Event()
_proxy_server_thread: threading.Thread | None = None
_proxy_server_sock: socket.socket | None = None
_proxy_session_active = False

# Timeouts (seconds) — short upstream connect often fixes Chrome ERR_TIMED_OUT when IPv6/DNS misbehaves.
UPSTREAM_CONNECT_TIMEOUT = float(os.environ.get("MARKT_UPSTREAM_CONNECT_TIMEOUT", "25"))
HEADER_READ_TIMEOUT = float(os.environ.get("MARKT_HEADER_READ_TIMEOUT", "90"))

# Set by _apply_upstream() / start_proxy(); used by handle_client / inject_proxy_auth.
_UPSTREAM_HOST: str = PROXY_HOST
_UPSTREAM_PORT: int = PROXY_PORT
_UPSTREAM_AUTH: str = ""


def _resolve_proxy(proxy_url: str | None) -> tuple[str, int, str, str]:
    """
    Parse a proxy URL like:
    http://user:password@ultra.marsproxies.com:44443
    Returns (host, port, username, password). If proxy_url is None/empty, uses module defaults.
    """
    if not (proxy_url and proxy_url.strip()):
        return PROXY_HOST, PROXY_PORT, USERNAME, PASSWORD
    p = urlparse(proxy_url.strip())
    if not p.hostname:
        raise ValueError(f"Invalid proxy URL (missing host): {proxy_url!r}")
    port = p.port
    if port is None:
        port = 443 if (p.scheme or "").lower() == "https" else 80
    user = unquote(p.username) if p.username else ""
    password = unquote(p.password) if p.password else ""
    return p.hostname, port, user, password


def _apply_upstream(host: str, port: int, user: str, password: str) -> None:
    global _UPSTREAM_HOST, _UPSTREAM_PORT, _UPSTREAM_AUTH
    _UPSTREAM_HOST = host
    _UPSTREAM_PORT = port
    if user or password:
        _UPSTREAM_AUTH = base64.b64encode(f"{user}:{password}".encode()).decode()
    else:
        _UPSTREAM_AUTH = ""


_apply_upstream(PROXY_HOST, PROXY_PORT, USERNAME, PASSWORD)


def _tune_socket(s: socket.socket) -> None:
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass


def connect_upstream(host: str, port: int, timeout: float) -> socket.socket:
    """
    Prefer IPv4 first — some networks stall or time out on IPv6 to proxy hosts, which shows as ERR_TIMED_OUT in Chrome.
    """
    last: OSError | None = None
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            infos = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
        except OSError as e:
            last = e
            continue
        for res in infos:
            af, socktype, proto, canonname, sa = res
            s = socket.socket(af, socktype, proto)
            s.settimeout(timeout)
            _tune_socket(s)
            try:
                s.connect(sa)
                return s
            except OSError as e:
                last = e
                s.close()
    if last is not None:
        raise last
    raise OSError(f"Could not resolve or connect to {host!r}:{port}")


def read_until_header_end(sock: socket.socket) -> bytes | None:
    """Read bytes until the first complete HTTP header block (\\r\\n\\r\\n)."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            return None if not buf else buf
        buf += chunk
        if len(buf) > 256 * 1024:
            raise OSError("HTTP headers too large")
    return buf


def inject_proxy_auth(header_bytes: bytes) -> bytes:
    if b"proxy-authorization:" in header_bytes.lower():
        return header_bytes
    if not _UPSTREAM_AUTH:
        return header_bytes
    if not header_bytes.endswith(b"\r\n\r\n"):
        return header_bytes
    without = header_bytes[:-4]
    auth_line = f"Proxy-Authorization: Basic {_UPSTREAM_AUTH}\r\n".encode()
    return without + b"\r\n" + auth_line + b"\r\n"


def relay_bidirectional(a: socket.socket, b: socket.socket) -> None:
    def forward(src: socket.socket, dst: socket.socket) -> None:
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    t1 = threading.Thread(target=forward, args=(a, b), daemon=True)
    t2 = threading.Thread(target=forward, args=(b, a), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def handle_client(client_socket: socket.socket) -> None:
    remote: socket.socket | None = None
    try:
        client_socket.settimeout(HEADER_READ_TIMEOUT)
        request = read_until_header_end(client_socket)
        if not request:
            return

        request = inject_proxy_auth(request)
        first_line = request.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")

        remote = connect_upstream(_UPSTREAM_HOST, _UPSTREAM_PORT, UPSTREAM_CONNECT_TIMEOUT)
        remote.settimeout(HEADER_READ_TIMEOUT)
        remote.sendall(request)

        if first_line.upper().startswith("CONNECT"):
            response = read_until_header_end(remote)
            if not response:
                print("[proxy] upstream closed before CONNECT response", flush=True)
                return
            status_line = response.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
            if b" 200 " not in response.split(b"\r\n", 1)[0]:
                print(f"[proxy] upstream CONNECT failed: {status_line!r}", flush=True)
            client_socket.sendall(response)
            if b" 200 " not in response.split(b"\r\n", 1)[0]:
                return
            remote.settimeout(None)
            client_socket.settimeout(None)
            relay_bidirectional(client_socket, remote)
        else:
            remote.settimeout(None)
            client_socket.settimeout(None)
            relay_bidirectional(client_socket, remote)
    except TimeoutError as e:
        print(f"[proxy] timed out (upstream or headers): {e}", flush=True)
    except OSError as e:
        print(f"[proxy] client/upstream error: {e}", flush=True)
    finally:
        try:
            client_socket.close()
        except OSError:
            pass
        if remote is not None:
            try:
                remote.close()
            except OSError:
                pass


def _create_listen_socket() -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((LISTEN_HOST, LOCAL_PORT))
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            print(
                f"Proxy: port {LOCAL_PORT} in use. Stop the other process or change LOCAL_PORT.",
                flush=True,
            )
        raise
    server.listen(128)
    _tune_socket(server)
    return server


def _proxy_accept_loop() -> None:
    global _proxy_server_sock
    srv = _proxy_server_sock
    if srv is None:
        return
    srv.settimeout(1.0)
    while not _proxy_stop.is_set():
        try:
            client_socket, _addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        _tune_socket(client_socket)
        threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()
    try:
        srv.close()
    except OSError:
        pass


def start_proxy_background(proxy_url: str | None = None) -> None:
    """
    Start the local forwarder on LISTEN_HOST:LOCAL_PORT without blocking the main thread.
    Call set_adb_proxy() after this so the device can reach the listener.
    """
    global _proxy_server_sock, _proxy_server_thread, _proxy_stop
    stop_proxy_background()
    host, port, user, pw = _resolve_proxy(proxy_url)
    _apply_upstream(host, port, user, pw)
    _proxy_stop.clear()
    _proxy_server_sock = _create_listen_socket()
    _proxy_server_thread = threading.Thread(target=_proxy_accept_loop, daemon=True)
    _proxy_server_thread.start()
    print(
        f"Proxy: listening {LISTEN_HOST}:{LOCAL_PORT} → upstream {_UPSTREAM_HOST}:{_UPSTREAM_PORT}",
        flush=True,
    )
    dh = _last_device_proxy_host
    if dh:
        print(
            f"  On emulator/device use host {dh!r}:{LOCAL_PORT} (after adb global http_proxy).",
            flush=True,
        )


def stop_proxy_background() -> None:
    """Stop the background forwarder thread and close the listen socket."""
    global _proxy_server_sock, _proxy_server_thread, _proxy_stop
    _proxy_stop.set()
    if _proxy_server_sock is not None:
        try:
            _proxy_server_sock.close()
        except OSError:
            pass
        _proxy_server_sock = None
    if _proxy_server_thread is not None:
        _proxy_server_thread.join(timeout=5.0)
        _proxy_server_thread = None


def clear_adb_proxy() -> None:
    """Clear device global HTTP proxy and remove tcp reverse (if that mode was used)."""
    adb = _adb_cmd()
    subprocess.run(
        f"{adb} shell settings put global http_proxy :0",
        shell=True,
        capture_output=True,
        text=True,
    )
    if ADB_PROXY_MODE == "reverse":
        subprocess.run(
            f"{adb} reverse --remove tcp:{LOCAL_PORT}",
            shell=True,
            capture_output=True,
            text=True,
        )
    print("Proxy: cleared ADB global http_proxy (and reverse rule if applicable).", flush=True)


def begin_proxy_session(proxy_url: str | None = None) -> None:
    """
    Probe upstream, start local forwarder, point the emulator at it via ADB.
    Pair with end_proxy_session() when done (e.g. after markt_ads_post.post_ads).
    """
    global _proxy_session_active
    if _proxy_session_active:
        raise RuntimeError("Proxy session already active; call end_proxy_session() first.")
    probe_upstream(proxy_url)
    try:
        start_proxy_background(proxy_url)
        set_adb_proxy()
    except Exception:
        stop_proxy_background()
        raise
    _proxy_session_active = True


def end_proxy_session() -> None:
    """Stop forwarder and clear device proxy settings."""
    global _proxy_session_active
    if not _proxy_session_active:
        return
    try:
        stop_proxy_background()
    finally:
        try:
            clear_adb_proxy()
        finally:
            _proxy_session_active = False


def probe_upstream(proxy_url: str | None = None) -> None:
    host, port, _, _ = _resolve_proxy(proxy_url)
    try:
        s = connect_upstream(host, port, min(UPSTREAM_CONNECT_TIMEOUT, 10.0))
        s.close()
        print(f"Upstream OK: TCP to {host}:{port}", flush=True)
    except OSError as e:
        print(
            f"Upstream FAILED ({e}). Fix network/credentials/firewall before Chrome will load pages.",
            flush=True,
        )


def start_proxy(proxy_url: str | None = None) -> None:
    """
    Start the local forwarding server (blocking). ``proxy_url`` is optional; when set, it is the full upstream
    URL, e.g. http://user:pass@ultra.marsproxies.com:44443 (same form as proxies.txt lines).
    When omitted, uses PROXY_HOST / PROXY_PORT / USERNAME / PASSWORD above.

    For automation, prefer begin_proxy_session() / end_proxy_session() from ``markt_ads_post.post_ads``.
    """
    host, port, user, pw = _resolve_proxy(proxy_url)
    _apply_upstream(host, port, user, pw)

    server = _create_listen_socket()

    print(
        f"Listening {LISTEN_HOST}:{LOCAL_PORT} → upstream {_UPSTREAM_HOST}:{_UPSTREAM_PORT}",
        flush=True,
    )
    print(
        f"  Chrome on this PC: 127.0.0.1:{LOCAL_PORT}",
        flush=True,
    )
    dh = _last_device_proxy_host
    if dh:
        print(
            f"  On emulator/device use host {dh!r}:{LOCAL_PORT} (see adb output above).",
            flush=True,
        )

    try:
        while True:
            client_socket, addr = server.accept()
            _tune_socket(client_socket)
            threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()
    finally:
        try:
            server.close()
        except OSError:
            pass


def _adb_cmd() -> str:
    exe = _adb_exe()
    if " " in exe and not (exe.startswith('"') or exe.startswith("'")):
        exe = f'"{exe}"'
    if ADB_SERIAL:
        return f'{exe} -s "{ADB_SERIAL}"'
    return exe


def set_adb_proxy() -> None:
    """
    Prefer adb reverse: device 127.0.0.1:PORT → host 127.0.0.1:PORT so Chrome does not rely on 10.0.2.2 (often fails on LDPlayer).
    """
    adb = _adb_cmd()
    if ADB_PROXY_MODE == "reverse":
        r = subprocess.run(
            f"{adb} reverse tcp:{LOCAL_PORT} tcp:{LOCAL_PORT}",
            shell=True,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(
                f"adb reverse failed ({r.stderr or r.stdout or r.returncode}). "
                "Using 10.0.2.2 (unreliable on some emulators). "
                "Fix: connect one device, set MARKT_ADB_SERIAL, or use MARKT_ADB_PROXY_MODE=lan + MARKT_ADB_PROXY_HOST.",
                flush=True,
            )
            target_host = "10.0.2.2"
        else:
            target_host = "127.0.0.1"
    elif ADB_PROXY_MODE == "host_alias":
        target_host = ADB_PROXY_HOST or "10.0.2.2"
    elif ADB_PROXY_MODE == "lan":
        if not ADB_PROXY_HOST:
            print(
                "MARKT_ADB_PROXY_MODE=lan requires MARKT_ADB_PROXY_HOST (your PC LAN IP).",
                flush=True,
            )
            return
        target_host = ADB_PROXY_HOST
    else:
        print(
            f"Unknown MARKT_ADB_PROXY_MODE={ADB_PROXY_MODE!r}; use reverse, host_alias, or lan.",
            flush=True,
        )
        return

    global _last_device_proxy_host
    target = f"{target_host}:{LOCAL_PORT}"
    _last_device_proxy_host = target_host
    print(f"Setting ADB global http_proxy to {target} (mode={ADB_PROXY_MODE}) ...", flush=True)
    subprocess.run(
        f"{adb} shell settings put global http_proxy {target}",
        shell=True,
    )


if __name__ == "__main__":
    import sys

    _url = os.environ.get("MARKT_PROXY_URL", "").strip() or (
        sys.argv[1].strip() if len(sys.argv) > 1 else ""
    )
    proxy_url: str | None = _url if _url else None

    probe_upstream(proxy_url)
    set_adb_proxy()
    start_proxy(proxy_url)
