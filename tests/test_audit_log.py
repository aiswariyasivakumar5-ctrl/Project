import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentinel.audit_log import AuditLog, _secure_chmod, verify_audit_log


class AuditLogTests(unittest.TestCase):
    def test_invalid_existing_log_and_oversized_records_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            with self.assertRaisesRegex(ValueError, "at least 1024"):
                AuditLog(path, max_bytes=1)

            path.write_text("{bad json\n", encoding="utf-8")
            self.assertFalse(verify_audit_log(path)[0])
            with self.assertRaisesRegex(ValueError, "invalid hash chain"):
                AuditLog(path)

            path.unlink()
            sink = AuditLog(path, max_bytes=1024)
            with self.assertRaisesRegex(ValueError, "exceeds configured"):
                sink.append({"payload": "x" * 2048})
            with self.assertRaises(ValueError):
                sink.append({"not_json": float("nan")})

    def test_empty_log_is_genesis_but_nonempty_partial_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.write_bytes(b"")
            sink = AuditLog(path)
            self.assertEqual(sink._previous_hash, "0" * 64)

            path.write_bytes(b"{")
            with self.assertRaisesRegex(ValueError, "invalid hash chain"):
                AuditLog(path)

    def test_verifier_rejects_non_object_and_broken_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.write_text("[]\n", encoding="utf-8")
            valid, reason = verify_audit_log(path)
            self.assertFalse(valid)
            self.assertIn("not an object", reason)

            path.write_text('{"previous_hash":"wrong","record_hash":"x"}\n', encoding="utf-8")
            valid, reason = verify_audit_log(path)
            self.assertFalse(valid)
            self.assertIn("broken hash link", reason)

            path.write_text("{bad json\n", encoding="utf-8")
            valid, reason = verify_audit_log(path)
            self.assertFalse(valid)
            self.assertIn("cannot verify", reason)

            valid, reason = verify_audit_log(path / "missing")
            self.assertFalse(valid)
            self.assertIn("cannot verify", reason)

    def test_hash_chain_verifies_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            sink = AuditLog(path)
            sink.append({"decision": "forward", "request_id": 1})
            sink.append({"decision": "isolate", "request_id": 2})
            valid, _ = verify_audit_log(path)
            self.assertTrue(valid)
            path.write_text(path.read_text().replace('"forward"', '"changed"'))
            valid, reason = verify_audit_log(path)
            self.assertFalse(valid)
            self.assertIn("hash", reason)

    def test_verifier_canonicalizes_keys_and_rejects_missing_hash_and_nan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            sink = AuditLog(path)
            sink.append({"alpha": 1, "label": "café 🛰", "omega": 2})
            item = json.loads(path.read_text(encoding="utf-8"))
            reordered = dict(reversed(list(item.items())))
            path.write_text(
                json.dumps(reordered, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            self.assertTrue(verify_audit_log(path)[0])

            path.write_text('{"previous_hash":"' + "0" * 64 + '"}\n', encoding="utf-8")
            valid, _ = verify_audit_log(path)
            self.assertFalse(valid)

            unsigned = {"payload": float("nan"), "previous_hash": "0" * 64}
            canonical = json.dumps(
                unsigned, sort_keys=True, separators=(",", ":"), allow_nan=True
            )
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            nonstandard = dict(unsigned, record_hash=digest)
            path.write_text(json.dumps(nonstandard, allow_nan=True) + "\n", encoding="utf-8")
            valid, _ = verify_audit_log(path)
            self.assertFalse(valid)

    def test_size_rotation_keeps_verifiable_active_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            sink = AuditLog(path, max_bytes=1024)
            for index in range(12):
                sink.append({"index": index, "details": "x" * 120})
            self.assertTrue(path.with_name("audit.jsonl.1").exists())
            self.assertTrue(verify_audit_log(path)[0])
            self.assertTrue(verify_audit_log(path.with_name("audit.jsonl.1"))[0])

    @unittest.skipIf(os.name == "nt", "POSIX file permission mode bits not supported on Windows")
    def test_file_permissions_on_creation_and_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            sink = AuditLog(path, max_bytes=1024)
            sink.append({"first": "entry"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for index in range(12):
                sink.append({"index": index, "details": "x" * 120})
            rotated = path.with_name("audit.jsonl.1")
            self.assertTrue(rotated.exists())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(rotated.stat().st_mode & 0o777, 0o600)
            self.assertTrue(verify_audit_log(path)[0])
            self.assertTrue(verify_audit_log(rotated)[0])

    @unittest.skipIf(os.name == "nt", "POSIX file permission mode bits not supported on Windows")
    def test_preexisting_looser_permissions_tightened_and_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            sink1 = AuditLog(path)
            sink1.append({"key": "val"})
            os.chmod(path, 0o644)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            with self.assertLogs("sentinel.audit_log", level="WARNING") as captured:
                sink2 = AuditLog(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(
                any("tightened_audit_permissions" in entry for entry in captured.output)
            )
            sink2.append({"key": "val2"})
            self.assertTrue(verify_audit_log(path)[0])

    def test_reopening_existing_valid_log_loads_previous_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            sink1 = AuditLog(path)
            sink1.append({"msg": "first"})
            sink2 = AuditLog(path)
            self.assertEqual(sink2._previous_hash, sink1._previous_hash)
            sink2.append({"msg": "second"})
            self.assertTrue(verify_audit_log(path)[0])

    def test_secure_chmod_logic_and_warning_events(self):
        mock_path = unittest.mock.Mock()
        mock_path.exists.return_value = False
        self.assertFalse(_secure_chmod(mock_path))

        mock_path.exists.return_value = True
        if os.name == "nt":
            self.assertFalse(_secure_chmod(mock_path))

        mock_path.stat.return_value.st_mode = 0o100644
        with (
            patch("sentinel.audit_log.os.name", "posix"),
            patch("sentinel.audit_log.os.chmod") as mock_chmod,
        ):
            self.assertTrue(_secure_chmod(mock_path))
            mock_chmod.assert_called_once_with(mock_path, 0o600)

        mock_path.stat.return_value.st_mode = 0o100600
        with patch("sentinel.audit_log.os.name", "posix"):
            self.assertFalse(_secure_chmod(mock_path))

        mock_path.stat.return_value.st_mode = 0o100644
        with (
            patch("sentinel.audit_log.os.name", "posix"),
            patch("sentinel.audit_log.os.chmod", side_effect=OSError),
        ):
            self.assertFalse(_secure_chmod(mock_path))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            sink0 = AuditLog(path)
            sink0.append({"init": "ok"})
            rotated = path.with_name("audit.jsonl.1")
            rotated.touch()
            with patch("sentinel.audit_log._secure_chmod", return_value=True):
                with self.assertLogs("sentinel.audit_log", level="WARNING") as captured:
                    AuditLog(path)
                self.assertEqual(len(captured.output), 2)
                self.assertTrue(
                    all("tightened_audit_permissions" in msg for msg in captured.output)
                )

            with (
                patch("sentinel.audit_log.os.name", "posix"),
                patch("sentinel.audit_log.os.chmod", side_effect=OSError),
            ):
                sink0.append({"posix": "err"})
            with (
                patch("sentinel.audit_log.os.name", "posix"),
                patch("sentinel.audit_log.os.chmod") as mock_chmod,
            ):
                sink0.append({"posix": "ok"})
                mock_chmod.assert_called_with(path, 0o600)


if __name__ == "__main__":
    unittest.main()
