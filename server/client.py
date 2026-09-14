"""A minimal WebSocket client for talking to this backend.

Used by tools/pull_papers.py and by the tests. It speaks only as much of the
protocol as this server does: masked text frames, pings answered, close handled.
"""
import asyncio
import base64
import json
import os

from . import wsframe as wf


class Client:
    def __init__(self, reader, writer, *, answer_pings=True):
        self.reader, self.writer = reader, writer
        self.answer_pings = answer_pings
        self._parser = wf.FrameParser(max_frame_bytes=1 << 22, require_mask=False)
        self._assembler = wf.MessageAssembler(max_message_bytes=1 << 22)
        self._pending = []

    @classmethod
    async def connect(cls, host, port, *, path="/ws", origin=None, token=None, timeout=5,
                      answer_pings=True):
        reader, writer = await asyncio.open_connection(host, port)
        target = f"{path}?token={token}" if token else path
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [f"GET {target} HTTP/1.1", f"Host: {host}:{port}",
                 "Upgrade: websocket", "Connection: Upgrade",
                 f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        if origin:
            lines.append(f"Origin: {origin}")
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
        await writer.drain()

        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
        status = int(head.split(b" ")[1])
        if status != 101:
            body = await reader.read(4096)
            writer.close()
            raise HandshakeRefused(status, body.decode(errors="replace"))
        return cls(reader, writer, answer_pings=answer_pings)

    async def send(self, message):
        self.writer.write(wf.encode(wf.TEXT, json.dumps(message), masked=True))
        await self.writer.drain()

    async def recv(self, timeout=5):
        while not self._pending:
            data = await asyncio.wait_for(self.reader.read(65536), timeout)
            if not data:
                raise ConnectionError("server closed the connection")
            for frame in self._parser.feed(data):
                if frame.opcode == wf.PING:
                    if self.answer_pings:
                        self.writer.write(wf.encode(wf.PONG, frame.payload, masked=True))
                        await self.writer.drain()
                elif frame.opcode == wf.CLOSE:
                    raise ConnectionError(f"server closed: {wf.parse_close(frame.payload)}")
                elif frame.opcode in (wf.TEXT, wf.CONT, wf.BINARY):
                    got = self._assembler.push(frame)
                    if got:
                        self._pending.append(json.loads(got[1]))
        return self._pending.pop(0)

    async def recv_until(self, type_, timeout=5, collect=()):
        """Read events until `type_` arrives; returns (event, collected)."""
        collected = []
        while True:
            ev = await self.recv(timeout)
            if ev["type"] in collect:
                collected.append(ev)
            if ev["type"] == type_:
                return ev, collected

    async def close(self):
        try:
            self.writer.write(wf.encode_close(masked=True))
            await self.writer.drain()
        except (ConnectionError, RuntimeError):
            pass
        self.writer.close()


class HandshakeRefused(Exception):
    def __init__(self, status, body):
        super().__init__(f"{status}: {body}")
        self.status, self.body = status, body
