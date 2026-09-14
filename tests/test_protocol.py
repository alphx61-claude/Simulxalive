"""Command validation: a wrong parameter must be named, not guessed at."""
import json
import unittest

from server import protocol
from server.config import Config
from server.corpus import Corpus
from server.errors import ProtocolError, UnknownAxis, UnknownCommand, UnknownSource


class TestParse(unittest.TestCase):
    def test_well_formed_command(self):
        text = json.dumps({"type": "ping", "id": "a1", "params": {}})
        self.assertEqual(protocol.parse(text), ("ping", "a1", {}))

    def test_missing_params_is_fine(self):
        self.assertEqual(protocol.parse('{"type":"hello"}'), ("hello", None, {}))

    def test_not_json(self):
        with self.assertRaises(ProtocolError):
            protocol.parse("{nope")

    def test_not_an_object(self):
        with self.assertRaises(ProtocolError):
            protocol.parse("[1,2,3]")

    def test_unknown_command_lists_the_known_ones(self):
        with self.assertRaises(UnknownCommand) as ctx:
            protocol.parse('{"type":"pull.everything"}')
        self.assertIn("pull.start", ctx.exception.payload()["detail"]["known"])

    def test_params_must_be_an_object(self):
        with self.assertRaises(ProtocolError):
            protocol.parse('{"type":"ping","params":[]}')


class TestValidatePull(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.corpus = Corpus.load(self.cfg.data_dir)

    def check(self, params):
        return protocol.validate_pull(params, self.cfg, self.corpus)

    def test_defaults_are_filled_in(self):
        got = self.check({"axis": "anchoring"})
        self.assertEqual(got["source"], "openalex")
        self.assertEqual(got["limit"], self.cfg.default_results)
        self.assertFalse(got["include_known"])

    def test_per_page_never_exceeds_limit(self):
        self.assertEqual(self.check({"query": "framing", "limit": 5, "per_page": 100})["per_page"], 5)

    def test_axis_or_query_is_required(self):
        with self.assertRaises(ProtocolError):
            self.check({})

    def test_unknown_axis_lists_the_real_ones(self):
        with self.assertRaises(UnknownAxis) as ctx:
            self.check({"axis": "telepathy"})
        self.assertIn("anchoring", ctx.exception.payload()["detail"]["axes"])

    def test_unknown_source(self):
        with self.assertRaises(UnknownSource):
            self.check({"query": "x", "source": "scholar"})

    def test_unknown_parameter_is_refused(self):
        with self.assertRaises(ProtocolError) as ctx:
            self.check({"query": "x", "pages": 3})
        self.assertIn("pages", str(ctx.exception))

    def test_limit_over_the_cap(self):
        with self.assertRaises(ProtocolError):
            self.check({"query": "x", "limit": self.cfg.max_results + 1})

    def test_reversed_years(self):
        with self.assertRaises(ProtocolError):
            self.check({"query": "x", "from_year": 2020, "to_year": 2015})

    def test_booleans_must_be_booleans(self):
        with self.assertRaises(ProtocolError):
            self.check({"query": "x", "include_known": "yes"})

    def test_limit_must_not_be_a_bool(self):
        with self.assertRaises(ProtocolError):
            self.check({"query": "x", "limit": True})

    def test_side_is_constrained(self):
        with self.assertRaises(ProtocolError):
            self.check({"axis": "anchoring", "side": "sideways"})


class TestHello(unittest.TestCase):
    def test_hello_describes_the_server(self):
        cfg = Config()
        doc = protocol.hello(cfg, Corpus.load(cfg.data_dir), "9.9.9")
        self.assertEqual(doc["version"], "9.9.9")
        self.assertEqual(doc["corpus"]["axes"], 28)
        self.assertIn("openalex", [s["name"] for s in doc["sources"]])


if __name__ == "__main__":
    unittest.main()
