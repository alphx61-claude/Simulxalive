"""Framing is the one place a bug is silent: a wrong length byte just hangs."""
import struct
import unittest

from server import wsframe as wf


def parser(**kw):
    return wf.FrameParser(**{"max_frame_bytes": 1024, "require_mask": True, **kw})


class TestEncoding(unittest.TestCase):
    def test_short_payload_header(self):
        frame = wf.encode(wf.TEXT, "hi")
        self.assertEqual(frame[:2], bytes([0x81, 2]))

    def test_medium_payload_uses_two_length_bytes(self):
        frame = wf.encode(wf.BINARY, b"x" * 200)
        self.assertEqual(frame[0], 0x82)
        self.assertEqual(frame[1], 126)
        self.assertEqual(struct.unpack("!H", frame[2:4])[0], 200)

    def test_long_payload_uses_eight_length_bytes(self):
        frame = wf.encode(wf.BINARY, b"x" * 70000)
        self.assertEqual(frame[1], 127)
        self.assertEqual(struct.unpack("!Q", frame[2:10])[0], 70000)

    def test_masking_round_trips(self):
        frame = wf.encode(wf.TEXT, "masked", masked=True)
        self.assertTrue(frame[1] & 0x80)
        self.assertEqual(parser().feed(frame)[0].payload, b"masked")

    def test_close_frame_carries_code_and_reason(self):
        code, reason = wf.parse_close(wf.encode_close(wf.CLOSE_POLICY, "nope")[2:])
        self.assertEqual((code, reason), (wf.CLOSE_POLICY, "nope"))


class TestParsing(unittest.TestCase):
    def test_frames_arriving_in_pieces(self):
        p = parser()
        frame = wf.encode(wf.TEXT, "split me", masked=True)
        self.assertEqual(p.feed(frame[:3]), [])
        self.assertEqual(p.feed(frame[3:])[0].payload, b"split me")

    def test_several_frames_in_one_read(self):
        p = parser()
        got = p.feed(wf.encode(wf.TEXT, "a", masked=True) + wf.encode(wf.TEXT, "b", masked=True))
        self.assertEqual([f.payload for f in got], [b"a", b"b"])

    def test_unmasked_client_frame_is_a_protocol_error(self):
        with self.assertRaises(wf.WSProtocolError) as ctx:
            parser().feed(wf.encode(wf.TEXT, "plain"))
        self.assertEqual(ctx.exception.code, wf.CLOSE_PROTOCOL_ERROR)

    def test_reserved_bit_is_refused(self):
        frame = bytearray(wf.encode(wf.TEXT, "x", masked=True))
        frame[0] |= 0x40
        with self.assertRaises(wf.WSProtocolError):
            parser().feed(bytes(frame))

    def test_unknown_opcode_is_refused(self):
        with self.assertRaises(wf.WSProtocolError):
            parser().feed(wf.encode(0x3, b"", masked=True))

    def test_fragmented_control_frame_is_refused(self):
        with self.assertRaises(wf.WSProtocolError):
            parser().feed(wf.encode(wf.PING, b"", fin=False, masked=True))

    def test_oversize_frame_is_refused_before_buffering(self):
        header = bytes([0x81, 0xFF]) + struct.pack("!Q", 1 << 30) + b"\x00\x00\x00\x00"
        with self.assertRaises(wf.WSProtocolError) as ctx:
            parser().feed(header)
        self.assertEqual(ctx.exception.code, wf.CLOSE_TOO_BIG)

    def test_high_bit_length_is_refused(self):
        header = bytes([0x81, 0xFF]) + struct.pack("!Q", 1 << 63) + b"\x00\x00\x00\x00"
        with self.assertRaises(wf.WSProtocolError):
            parser().feed(header)


class TestAssembly(unittest.TestCase):
    def assemble(self, frames, **kw):
        a = wf.MessageAssembler(**{"max_message_bytes": 1024, **kw})
        out = [a.push(f) for f in frames]
        return [m for m in out if m is not None]

    def test_fragments_join_into_one_message(self):
        frames = [wf.Frame(False, wf.TEXT, b"he"), wf.Frame(False, wf.CONT, b"ll"),
                  wf.Frame(True, wf.CONT, b"o")]
        self.assertEqual(self.assemble(frames), [(wf.TEXT, "hello")])

    def test_continuation_without_a_start_is_refused(self):
        with self.assertRaises(wf.WSProtocolError):
            self.assemble([wf.Frame(True, wf.CONT, b"orphan")])

    def test_new_message_inside_a_fragment_is_refused(self):
        with self.assertRaises(wf.WSProtocolError):
            self.assemble([wf.Frame(False, wf.TEXT, b"a"), wf.Frame(True, wf.TEXT, b"b")])

    def test_invalid_utf8_closes_with_1007(self):
        with self.assertRaises(wf.WSProtocolError) as ctx:
            self.assemble([wf.Frame(True, wf.TEXT, b"\xff\xfe")])
        self.assertEqual(ctx.exception.code, wf.CLOSE_INVALID_PAYLOAD)

    def test_message_over_the_cap_closes_with_1009(self):
        with self.assertRaises(wf.WSProtocolError) as ctx:
            self.assemble([wf.Frame(True, wf.BINARY, b"x" * 50)], max_message_bytes=10)
        self.assertEqual(ctx.exception.code, wf.CLOSE_TOO_BIG)

    def test_binary_message_comes_back_as_bytes(self):
        self.assertEqual(self.assemble([wf.Frame(True, wf.BINARY, b"\x00\x01")]),
                         [(wf.BINARY, b"\x00\x01")])


if __name__ == "__main__":
    unittest.main()
