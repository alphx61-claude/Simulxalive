"""The WebSocket endpoint: handshake, connection loops, heartbeat, close.

One asyncio task reads frames, one writes them, one keeps the connection warm
with pings. Outbound messages go through a bounded queue: a client that stops
reading slows the pull down rather than letting the server buffer without limit.
"""
import asyncio
import base64
import hashlib
import json
import logging
import urllib.parse

from . import wsframe as wf

log = logging.getLogger("simulxalive.ws")

MAX_HANDSHAKE_BYTES = 16 * 1024
HANDSHAKE_TIMEOUT = 10.0
MAX_INFLIGHT_COMMANDS = 16


class Handshake:
    """Parsed upgrade request: what the session needs to know about the client."""

    def __init__(self, path, query, headers):
        self.path, self.query, self.headers = path, query, headers

    @property
    def origin(self):
        return self.headers.get("origin")

    def token(self):
        return self.query.get("token", [None])[0]


class HandshakeError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


async def _read_handshake(reader):
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HANDSHAKE_TIMEOUT)
    except asyncio.IncompleteReadError:
        raise HandshakeError(400, "connection closed during handshake")
    except asyncio.TimeoutError:
        raise HandshakeError(408, "handshake took too long")
    except asyncio.LimitOverrunError:
        raise HandshakeError(431, "request headers too large")
    if len(raw) > MAX_HANDSHAKE_BYTES:
        raise HandshakeError(431, "request headers too large")

    lines = raw.decode("latin-1").split("\r\n")
    try:
        method, target, version = lines[0].split(" ", 2)
    except ValueError:
        raise HandshakeError(400, "malformed request line")
    if method != "GET":
        raise HandshakeError(405, "websocket upgrade must be a GET")
    if version.upper() not in ("HTTP/1.1", "HTTP/2"):
        raise HandshakeError(505, "http/1.1 required")

    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()

    parts = urllib.parse.urlsplit(target)
    return Handshake(parts.path, urllib.parse.parse_qs(parts.query), headers)


def _accept_key(key):
    return base64.b64encode(hashlib.sha1((key + wf.GUID).encode()).digest()).decode()


def check_upgrade(hs, cfg):
    """Validate the upgrade and the caller's right to it. Returns the accept key."""
    if hs.headers.get("upgrade", "").lower() != "websocket":
        raise HandshakeError(426, "expected a websocket upgrade")
    if "upgrade" not in [t.strip().lower() for t in hs.headers.get("connection", "").split(",")]:
        raise HandshakeError(400, "Connection: Upgrade missing")
    if hs.headers.get("sec-websocket-version") != "13":
        raise HandshakeError(400, "only websocket version 13 is supported")
    key = hs.headers.get("sec-websocket-key", "")
    try:
        if len(base64.b64decode(key, validate=True)) != 16:
            raise ValueError
    except Exception:
        raise HandshakeError(400, "bad Sec-WebSocket-Key")

    origin = hs.origin
    if origin and not cfg.allow_any_origin and origin not in cfg.allowed_origins:
        # A browser page cannot be stopped from opening a socket to localhost,
        # so an unknown Origin is refused rather than trusted.
        raise HandshakeError(403, f"origin {origin} is not allowed")
    if cfg.token and hs.token() != cfg.token:
        raise HandshakeError(401, "missing or wrong token")
    return _accept_key(key)


class WSConnection:
    """A live client. Send JSON to it; it hands inbound JSON to the handler."""

    def __init__(self, reader, writer, cfg, handshake):
        self.reader, self.writer, self.cfg, self.handshake = reader, writer, cfg, handshake
        self.peer = writer.get_extra_info("peername")
        self.closed = asyncio.Event()
        self.sent = 0
        self.dropped = 0
        self._out = asyncio.Queue(maxsize=cfg.send_queue)
        self._pong = asyncio.Event()
        self._close_sent = False
        self._tasks = []

    # ------------------------------------------------------------- outbound
    async def send(self, message):
        """Enqueue a message, waiting for room. Backpressure reaches the caller."""
        if self.closed.is_set():
            return False
        await self._out.put(_dump(message))
        self.sent += 1
        return True

    def offer(self, message):
        """Enqueue only if there is room. For events that are safe to lose."""
        if self.closed.is_set():
            return False
        try:
            self._out.put_nowait(_dump(message))
        except asyncio.QueueFull:
            self.dropped += 1
            return False
        self.sent += 1
        return True

    def _control(self, frame):
        """Queue a control frame without waiting. False means the client is stuck."""
        try:
            self._out.put_nowait(frame)
            return True
        except asyncio.QueueFull:
            return False

    async def close(self, code=wf.CLOSE_NORMAL, reason=""):
        if not self._close_sent:
            self._close_sent = True
            try:
                self.writer.write(wf.encode_close(code, reason))
                await self.writer.drain()
            except (ConnectionError, RuntimeError):
                pass
        self.closed.set()

    # -------------------------------------------------------------- inbound
    async def run(self, handler):
        """Serve the connection until it closes. `handler(conn, text)` is a coroutine."""
        self._tasks = [asyncio.create_task(t) for t in (self._writer_loop(), self._heartbeat())]
        reading = asyncio.create_task(self._reader_loop(handler))
        stopping = asyncio.create_task(self.closed.wait())
        try:
            # Whichever happens first: the client goes away, or we close on it.
            # Without the second wait a peer that stops answering would hold the
            # read open forever after the heartbeat gave up on it.
            await asyncio.wait([reading, stopping], return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.closed.set()
            tasks = [*self._tasks, reading, stopping]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if reading.done() and not reading.cancelled() and reading.exception():
                log.error("reader loop for %s failed: %r", self.peer, reading.exception())
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except (ConnectionError, RuntimeError):
                pass

    async def _reader_loop(self, handler):
        parser = wf.FrameParser(max_frame_bytes=self.cfg.max_message_bytes)
        assembler = wf.MessageAssembler(max_message_bytes=self.cfg.max_message_bytes)
        inflight = set()
        try:
            while not self.closed.is_set():
                data = await self.reader.read(65536)
                if not data:
                    return
                for frame in parser.feed(data):
                    if frame.opcode == wf.CLOSE:
                        code, reason = wf.parse_close(frame.payload)
                        log.info("client closed: %s %s", code, reason)
                        await self.close(wf.CLOSE_NORMAL)
                        return
                    if frame.opcode == wf.PING:
                        self._control(wf.encode(wf.PONG, frame.payload))
                        continue
                    if frame.opcode == wf.PONG:
                        self._pong.set()
                        continue

                    got = assembler.push(frame)
                    if got is None:
                        continue
                    opcode, payload = got
                    if opcode != wf.TEXT:
                        await self.close(wf.CLOSE_PROTOCOL_ERROR, "this server speaks json text")
                        return
                    if len(inflight) >= MAX_INFLIGHT_COMMANDS:
                        await self.close(wf.CLOSE_POLICY, "too many commands in flight")
                        return
                    # Commands run off the read loop so a cancel is still heard
                    # while a pull is streaming.
                    task = asyncio.create_task(handler(self, payload))
                    inflight.add(task)
                    task.add_done_callback(inflight.discard)
        except wf.WSProtocolError as e:
            log.warning("protocol error from %s: %s", self.peer, e.reason)
            await self.close(e.code, e.reason)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            for task in list(inflight):
                task.cancel()

    async def _writer_loop(self):
        try:
            while True:
                payload = await self._out.get()
                frame = payload if isinstance(payload, bytes) else wf.encode(wf.TEXT, payload)
                self.writer.write(frame)
                await self.writer.drain()
        except (ConnectionError, RuntimeError):
            self.closed.set()
        except asyncio.CancelledError:
            raise

    async def _heartbeat(self):
        while True:
            await asyncio.sleep(self.cfg.ping_interval)
            if self.closed.is_set():
                return
            self._pong.clear()
            if not self._control(wf.encode(wf.PING)):
                # The queue is full because the client stopped reading: the
                # heartbeat would block here and never notice.
                log.info("%s is not draining its queue, dropping", self.peer)
                await self.close(wf.CLOSE_GOING_AWAY, "not reading")
                return
            try:
                await asyncio.wait_for(self._pong.wait(), self.cfg.ping_timeout)
            except asyncio.TimeoutError:
                log.info("no pong from %s, dropping", self.peer)
                await self.close(wf.CLOSE_GOING_AWAY, "no pong")
                return


def _dump(message):
    if isinstance(message, (str, bytes)):
        return message
    return json.dumps(message, separators=(",", ":"), ensure_ascii=False)


async def serve(cfg, session_factory, *, path="/ws"):
    """Start the server. `session_factory(conn)` returns an object with

    `async handle(conn, text)` and `async aclose()`.
    """
    async def client(reader, writer):
        try:
            hs = await _read_handshake(reader)
            if hs.path != path:
                raise HandshakeError(404, f"no endpoint at {hs.path}")
            accept = check_upgrade(hs, cfg)
        except HandshakeError as e:
            log.info("handshake refused: %s %s", e.status, e.message)
            _reject(writer, e)
            return
        except Exception:
            log.exception("handshake failed")
            writer.close()
            return

        writer.write(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + accept.encode() + b"\r\n\r\n")
        await writer.drain()

        conn = WSConnection(reader, writer, cfg, hs)
        session = session_factory(conn)
        log.info("client connected: %s", conn.peer)
        try:
            await conn.run(session.handle)
        finally:
            await session.aclose()
            log.info("client gone: %s (sent %d, dropped %d)", conn.peer, conn.sent, conn.dropped)

    return await asyncio.start_server(client, cfg.host, cfg.port)


def _reject(writer, e):
    body = e.message.encode()
    writer.write(
        f"HTTP/1.1 {e.status} {_REASONS.get(e.status, 'Error')}\r\n".encode()
        + b"Content-Type: text/plain; charset=utf-8\r\n"
        + f"Content-Length: {len(body)}\r\n".encode()
        + b"Connection: close\r\n\r\n" + body)
    writer.close()


_REASONS = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
            405: "Method Not Allowed", 408: "Request Timeout", 426: "Upgrade Required",
            431: "Headers Too Large",
            505: "HTTP Version Not Supported"}
