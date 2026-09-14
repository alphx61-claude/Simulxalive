"""A candidate must never assert something the upstream did not say."""
import unittest

from server.records import candidate, propose_id, surname

MAPPED = {
    "source_id": "W123",
    "title": "Anchoring effects in large language models",
    "authors": ["Ada Lovelace", "Alan Turing"],
    "year": 2024,
    "venue": "Journal of Nothing",
    "url": "https://example.org/paper",
    "doi": "https://doi.org/10.1/abc",
    "citations": 7,
    "citations_field": "openalex.cited_by_count",
    "type": "article",
    "references": ["W1", "W2"],
    "reference_count": 2,
}
QUERY = {"axes": ["anchoring"], "q": "anchoring on irrelevant numbers"}


def make(**kw):
    return candidate(MAPPED, source="openalex", query=QUERY, job_id="job_0001", **kw)


class TestSurname(unittest.TestCase):
    def test_given_then_family(self):
        self.assertEqual(surname(["Michal Kosinski"]), "kosinski")

    def test_family_first_with_comma(self):
        self.assertEqual(surname(["Kosinski, M."]), "kosinski")

    def test_dict_authors(self):
        self.assertEqual(surname([{"given": "Nunzio", "family": "Loré"}]), "lore")

    def test_no_authors(self):
        self.assertEqual(surname([]), "anon")


class TestProposedId(unittest.TestCase):
    def test_follows_the_seed_bibliography_style(self):
        self.assertEqual(propose_id(MAPPED, set()), "lovelace2024")

    def test_collision_borrows_a_title_word(self):
        self.assertEqual(propose_id(MAPPED, {"lovelace2024"}), "lovelace2024anchoring")

    def test_second_collision_falls_back_to_a_number(self):
        taken = {"lovelace2024", "lovelace2024anchoring"}
        self.assertEqual(propose_id(MAPPED, taken), "lovelace2024-2")


class TestCandidate(unittest.TestCase):
    def test_judgements_are_left_to_the_reviewer(self):
        review = make()["review"]
        self.assertEqual(review["status"], "pending")
        self.assertIsNone(review["domain"])
        self.assertIsNone(review["major"])
        self.assertIsNone(review["cluster"])
        self.assertEqual(review["proposed_axes"], ["anchoring"])

    def test_citations_carry_their_date_and_field(self):
        c = make(fetched_at="2026-01-02T03:04:05+00:00")["citations"]
        self.assertEqual(c, {"value": 7, "as_of": "2026-01-02",
                             "field": "openalex.cited_by_count"})

    def test_missing_citation_count_is_not_invented(self):
        c = candidate({**MAPPED, "citations": None}, source="openalex", query=QUERY,
                      job_id="job_0001")
        self.assertIsNone(c["citations"])

    def test_provenance_records_how_it_arrived_and_that_nobody_accepted_it(self):
        prov = make()["provenance"]
        self.assertEqual(prov["via"], "ingest")
        self.assertEqual(prov["source"], "openalex")
        self.assertEqual(prov["source_id"], "W123")
        self.assertEqual(prov["job"], "job_0001")
        self.assertIsNone(prov["accepted_by"])
        self.assertEqual(prov["query"], QUERY)

    def test_it_is_a_candidate_not_a_paper(self):
        c = make()
        self.assertEqual(c["kind"], "candidate")
        self.assertNotIn("id", c)
        self.assertIn("proposed_id", c)


if __name__ == "__main__":
    unittest.main()
