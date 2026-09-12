from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_ellis_zipapp as builder  # noqa: E402


class EllisPortableReadIdentityTests(unittest.TestCase):
    def test_path_replacement_between_admission_and_open_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            admitted = root / "portable-input.bin"
            replacement = root / "replacement.bin"
            admitted.write_bytes(b"trusted bytes\n")
            replacement.write_bytes(b"substitute bytes\n")

            real_lstat = Path.lstat
            swapped = False

            def admit_then_replace(path: Path, *args: object, **kwargs: object):
                nonlocal swapped
                observed = real_lstat(path, *args, **kwargs)
                if path == admitted and not swapped:
                    os.replace(replacement, admitted)
                    swapped = True
                return observed

            with mock.patch.object(Path, "lstat", autospec=True, side_effect=admit_then_replace):
                with self.assertRaisesRegex(builder.PortableError, "changed before open"):
                    builder._read_regular(admitted)

            self.assertTrue(swapped)
            self.assertEqual(admitted.read_bytes(), b"substitute bytes\n")


if __name__ == "__main__":
    unittest.main()
