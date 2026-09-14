"""RFC 6455 framing, with no I/O in it so it can be tested on plain bytes.

Only what this backend needs: text and binary data frames, fragmentation, the
three control frames, and the close handshake. No extensions are negotiated, so
any RSV bit set is a protocol error.
"""
import os
import struct

CONT, TEXT, BINARY, CLOSE, PING, PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
DATA_OPCODES = (TEXT, BINARY)
CONTROL_OPCODES = (CLOSE, PING, PONG)
OPCODES = (CONT, TEXT, BINARY, CLOSE, PING, PONG)

# Close codes used here.
CLOSE_NORMAL = 1000
CLOSE_GOING_AWAY = 1001
CLOSE_PROTOCOL_ERROR = 1002
CLOSE_INVALID_PAYLOAD = 1007
CLOSE_POLICY = 1008
CLOSE_TOO_BIG = 1009
CLOSE_INTERNAL = 1011

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WSProtocolError(Exception):
    """Fatal for the connection: carries the close code to send back."""

    def __init__(self, reason, code=CLOSE_PROTOCOL_ERROR):
        super().__init__(reason)
        self.reason = reason
        self.code = code


class Frame:
    __slots__ = ("fin", "opcode", "payload")

    def __init__(self, fin, opcode, payload):
        self.fin, self.opcode, self.payload = fin, opcode, payload

    def __repr__(self):
        return f"Frame(fin={self.fin}, opcode={self.opcode:#x}, len={len(self.payload)})"


def mask(payload, key):
    """XOR a payload with a 4-byte masking key. Symmetric: masks and unmasks."""
    return bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def encode(opcode, payload=b"", *, fin=True, masked=False):
    """Serialise one frame. Servers send unmasked; clients must mask."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    n = len(payload)
    head = bytearray([(0x80 if fin else 0x00) | opcode])
    flag = 0x80 if masked else 0x00
    if n < 126:
        head.append(flag | n)
    elif n < 1 << 16:
        head.append(flag | 126)
        head += struct.pack("!H", n)
    else:
        head.append(flag | 127)
        head += struct.pack("!Q", n)
    if masked:
        key = os.urandom(4)
        return bytes(head) + key + mask(payload, key)
    return bytes(head) + payload


def encode_close(code=CLOSE_NORMAL, reason="", *, masked=False):
    body = struct.pack("!H", code) + reason.encode("utf-8")[:123]
    return encode(CLOSE, body, masked=masked)


def parse_close(payload):
    """(code, reason) from a close frame body. Empty body means 'no status'."""
    if not payload:
        return CLOSE_NORMAL, ""
    if len(payload) == 1:
        raise WSProtocolError("close payload of one byte")
    code = struct.unpack("!H", payload[:2])[0]
    try:
        reason = payload[2:].decode("utf-8")
    except UnicodeDecodeError:
        raise WSProtocolError("close reason is not utf-8", CLOSE_INVALID_PAYLOAD)
    return code, reason


class FrameParser:
    """Incremental frame decoder. Feed it bytes, get whole frames back."""

    def __init__(self, *, max_frame_bytes, require_mask=True):
        self.max_frame_bytes = max_frame_bytes
        self.require_mask = require_mask
        self._buf = bytearray()

    def feed(self, data):
        self._buf += data
        out = []
        while True:
            frame = self._take()
            if frame is None:
                return out
            out.append(frame)

    def _take(self):
        buf = self._buf
        if len(buf) < 2:
            return None
        b0, b1 = buf[0], buf[1]
        if b0 & 0x70:
            raise WSProtocolError("reserved bit set but no extension negotiated")
        opcode, fin = b0 & 0x0F, bool(b0 & 0x80)
        if opcode not in OPCODES:
            raise WSProtocolError(f"unknown opcode {opcode:#x}")
        masked, n = bool(b1 & 0x80), b1 & 0x7F
        if masked != self.require_mask:
            raise WSProtocolError("masked frame from server" if masked else "unmasked frame from client")

        offset = 2
        if n == 126:
            if len(buf) < offset + 2:
                return None
            n = struct.unpack_from("!H", buf, offset)[0]
            offset += 2
        elif n == 127:
            if len(buf) < offset + 8:
                return None
            n = struct.unpack_from("!Q", buf, offset)[0]
            if n >> 63:
                raise WSProtocolError("payload length has the high bit set")
            offset += 8

        if opcode in CONTROL_OPCODES:
            if not fin:
                raise WSProtocolError("fragmented control frame")
            if n > 125:
                raise WSProtocolError("control frame payload over 125 bytes")
        elif n > self.max_frame_bytes:
            # Refuse before buffering it: the length is in the header.
            raise WSProtocolError(f"frame of {n} bytes over the {self.max_frame_bytes} limit",
                                  CLOSE_TOO_BIG)

        key = b""
        if masked:
            if len(buf) < offset + 4:
                return None
            key = bytes(buf[offset:offset + 4])
            offset += 4
        if len(buf) < offset + n:
            return None

        payload = bytes(buf[offset:offset + n])
        del buf[:offset + n]
        return Frame(fin, opcode, mask(payload, key) if masked else payload)


class MessageAssembler:
    """Joins fragments into whole messages and validates text as UTF-8."""

    def __init__(self, *, max_message_bytes):
        self.max_message_bytes = max_message_bytes
        self._opcode = None
        self._parts = bytearray()

    def push(self, frame):
        """Returns (opcode, payload) once a message completes, else None."""
        if frame.opcode in CONTROL_OPCODES:
            raise ValueError("control frames are handled by the caller")
        if frame.opcode == CONT:
            if self._opcode is None:
                raise WSProtocolError("continuation frame with nothing to continue")
        else:
            if self._opcode is not None:
                raise WSProtocolError("new data frame inside a fragmented message")
            self._opcode = frame.opcode

        self._parts += frame.payload
        if len(self._parts) > self.max_message_bytes:
            raise WSProtocolError(
                f"message over the {self.max_message_bytes} byte limit", CLOSE_TOO_BIG)
        if not frame.fin:
            return None

        opcode, data = self._opcode, bytes(self._parts)
        self._opcode, self._parts = None, bytearray()
        if opcode == TEXT:
            try:
                return TEXT, data.decode("utf-8")
            except UnicodeDecodeError:
                raise WSProtocolError("text message is not valid utf-8", CLOSE_INVALID_PAYLOAD)
        return opcode, data
