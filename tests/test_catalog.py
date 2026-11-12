import tempfile
import unittest
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

from src.catalog.harvest import connect, ingest, parse
from src.catalog.release import normalize, normalized_doi, publish


FIXTURE = b'''<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<ListRecords><record><header><datestamp>2026-01-01</datestamp></header><metadata>
<arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>2601.00001</id><created>2026-01-01</created>
<title> A   title </title><abstract>Real abstract</abstract><categories>cs.AI stat.ML</categories>
<authors><author><keyname>Author</keyname></author></authors></arXiv>
</metadata></record><record><header status="deleted"/></record>
<resumptionToken>next-token</resumptionToken></ListRecords></OAI-PMH>'''


class CatalogTests(unittest.TestCase):
    def test_source_fields_and_deleted_record(self):
        records, token = parse(FIXTURE)
        self.assertEqual(token, 'next-token')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['title'], 'A title')
        self.assertEqual(records[0]['categories'], ['cs.AI', 'stat.ML'])
        self.assertIsNone(records[0]['version'])
        self.assertFalse(records[0]['pdf_downloaded'])

    def test_replay_deduplicates_and_cursor_commits(self):
        records, token = parse(FIXTURE)
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'catalog.sqlite')
            try:
                for _ in range(2):
                    ingest(db, records, 'cs', token, 'raw/a.xml.gz', 'abc')
                self.assertEqual(db.execute('SELECT count(*) FROM works').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM batches').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT token,done FROM checkpoints').fetchone(), ('next-token', 0))
                records[0]['title'] = 'Updated title'
                ingest(db, records, 'cs', None, 'raw/b.xml.gz', 'def')
                self.assertEqual(db.execute('SELECT title FROM works').fetchone()[0], 'Updated title')
                self.assertEqual(db.execute('SELECT done FROM checkpoints').fetchone()[0], 1)
            finally:
                db.close()

    def test_errors_are_not_empty_success(self):
        with self.assertRaises(ValueError):
            parse(b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><error code="badResumptionToken">expired</error></OAI-PMH>')
        self.assertEqual(parse(b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><error code="noRecordsMatch"/></OAI-PMH>'), ([], None))

    def test_crosslisted_topic_and_doi_group(self):
        record = parse(FIXTURE)[0][0]
        record['categories'] = ['hep-th', 'math.PR']
        record['doi'] = 'https://doi.org/10.1234/Example'
        output = normalize(record)
        self.assertEqual(output['primary_topic'], 'mathematics')
        self.assertEqual(output['primary_arxiv_category'], 'hep-th')
        self.assertEqual(output['publication_year'], 2026)
        self.assertEqual(output['canonical_group_id'], 'doi:10.1234/example')
        self.assertEqual(record['doi'], 'https://doi.org/10.1234/Example')
        self.assertIsNone(normalized_doi('not a DOI'))

    def test_full_release_requires_matching_raw_and_round_trips(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'harvest.lock').write_bytes(b'0')
            raw = root / 'raw.xml.gz'
            raw.write_bytes(gzip.compress(FIXTURE))
            db = connect(root / 'catalog.sqlite')
            records, token = parse(FIXTURE)
            ingest(db, records, 'cs', token, raw.name, hashlib.sha256(FIXTURE).hexdigest())
            # A corrupt source must not produce a successful release.
            raw.write_bytes(gzip.compress(b'corrupt'))
            db.close()
            with self.assertRaises(AssertionError):
                publish(root, minimum=1)
            self.assertFalse((root / 'v1').exists())
            raw.write_bytes(gzip.compress(FIXTURE))
            publish(root, minimum=1)
            manifest = json.loads((root / 'v1/manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['papers'], 1)
            for name, entry in manifest['files'].items():
                self.assertEqual(hashlib.sha256((root / 'v1' / name).read_bytes()).hexdigest(), entry['sha256'])
            db = sqlite3.connect(root / 'v1/catalog.sqlite')
            try:
                hits = db.execute("SELECT w.paper_id,w.title FROM search s JOIN works w ON w.paper_id=s.paper_id WHERE search MATCH 'abstract' LIMIT 10").fetchall()
                self.assertEqual(hits, [('arxiv:2601.00001', 'A title')])
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
