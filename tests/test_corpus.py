"""Dedup decides whether a pull is useful or a pile of things we already have."""
import json
import pathlib
import tempfile
import unittest

from server.corpus import Corpus, DedupIndex, normalise_doi, normalise_title


class TestNormalisation(unittest.TestCase):
    def test_titles_ignore_case_punctuation_and_accents(self):
        self.assertEqual(normalise_title("Théorie of Mind: a Review!"), "theorie of mind a review")

    def test_doi_prefixes_are_stripped(self):
        for raw in ("https://doi.org/10.1/AB", "doi:10.1/ab", "10.1/ab", " 10.1/AB "):
            self.assertEqual(normalise_doi(raw), "10.1/ab")

    def test_empty_inputs(self):
        self.assertEqual(normalise_title(None), "")
        self.assertEqual(normalise_doi(None), "")


class TestDedup(unittest.TestCase):
    def setUp(self):
        self.corpus = Corpus.load(pathlib.Path(__file__).resolve().parent.parent / "data")
        self.index = DedupIndex.from_corpus(self.corpus)

    def test_seed_paper_is_recognised_through_punctuation(self):
        v = self.index.check(title="Evaluating Large Language Models in Theory of Mind Tasks!")
        self.assertEqual(v.status, "in_corpus")
        self.assertEqual((v.matched, v.reason), ("kosinski2024", "title"))

    def test_unseen_paper_is_new(self):
        self.assertTrue(self.index.check(title="A paper about nothing in particular").is_new)

    def test_doi_beats_title(self):
        self.index.add(ref="x1", origin="corpus", title="Something", doi="10.1/ab")
        v = self.index.check(title="Different title entirely", doi="https://doi.org/10.1/AB")
        self.assertEqual((v.status, v.reason), ("in_corpus", "doi"))

    def test_short_titles_never_match(self):
        self.index.add(ref="tiny", origin="corpus", title="Mind")
        self.assertTrue(self.index.check(title="Mind").is_new)

    def test_within_run_duplicates_are_reported_separately(self):
        self.index.add(ref="c1", origin="run", title="A brand new preprint on anchoring")
        v = self.index.check(title="A brand new preprint on anchoring")
        self.assertEqual(v.status, "duplicate_in_run")

    def test_staged_candidates_are_indexed_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "job_0001.jsonl"
            path.write_text(json.dumps({
                "proposed_id": "someone2025",
                "title": "Anchoring in language models under rewording",
                "doi": "10.5/zz",
                "provenance": {"source_id": "W1"},
            }) + "\n" + "\n")           # blank line: staging files are appended to live
            self.assertEqual(self.index.add_staged(tmp), 1)
        v = self.index.check(title="Anchoring in language models under rewording")
        self.assertEqual((v.status, v.matched), ("already_staged", "someone2025"))

    def test_missing_ingest_dir_is_not_an_error(self):
        self.assertEqual(self.index.add_staged("/nonexistent/ingest"), 0)

    def test_index_reports_its_size(self):
        self.assertEqual(len(self.index.refs), len(self.corpus.sources))


class TestCorpus(unittest.TestCase):
    def test_axes_are_addressable_by_id(self):
        corpus = Corpus.load(pathlib.Path(__file__).resolve().parent.parent / "data")
        self.assertEqual(corpus.axis("tom-false-belief")["family"], "social-cognition")
        self.assertIsNone(corpus.axis("nope"))


if __name__ == "__main__":
    unittest.main()
