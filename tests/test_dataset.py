import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sentinel.dataset import export_dataset
from sentinel.models import Interaction


class DatasetTests(unittest.TestCase):
    def test_reproducible_and_auditable(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            first = export_dataset(a, (7, 8), 12, 6, 6)
            second = export_dataset(b, (7, 8), 12, 6, 6)
            self.assertEqual(first, second)
            ids, sessions, total = set(), {}, 0
            for shard in first["shards"]:
                data = (a / shard["path"]).read_bytes()
                self.assertEqual(data, (b / shard["path"]).read_bytes())
                self.assertEqual(hashlib.sha256(data).hexdigest(), shard["gzip_sha256"])
                plain = gzip.decompress(data)
                self.assertEqual(hashlib.sha256(plain).hexdigest(), shard["jsonl_sha256"])
                rows = [json.loads(line) for line in plain.splitlines()]
                self.assertEqual(len(rows), shard["events"])
                self.assertEqual(sum(row["malicious"] for row in rows), shard["malicious"])
                for row in rows:
                    Interaction.from_dict(row["interaction"])
                    self.assertNotIn(row["event_id"], ids)
                    ids.add(row["event_id"])
                    sessions.setdefault(row["split"], set()).add(row["interaction"]["session_id"])
                    if row["split"] != "test":
                        self.assertFalse(row["malicious"])
                total += len(rows)
            self.assertEqual(total, first["total_events"])
            self.assertFalse(sessions["train"] & sessions["validation"])
            self.assertFalse(sessions["train"] & sessions["test"])
            self.assertFalse(sessions["validation"] & sessions["test"])

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                export_dataset(Path(tmp), (7,), 6, 6, 6)

    def test_invalid_configuration_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "bad"
            for seeds in ((), (7, 7), (-1,), (True,)):
                with self.assertRaises(ValueError):
                    export_dataset(dest, seeds, 6, 6, 6)
            self.assertFalse(dest.exists())
