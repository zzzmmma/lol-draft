import errno
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from src import build_dataset as builder


class DatasetSavingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="csv 저장 테스트 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder_patch = patch.object(builder, "PROCESSED_DIR", self.root)
        self.folder_patch.start()
        self.addCleanup(self.folder_patch.stop)
        self.frame = pd.DataFrame({
            "champion": ["아리", "Varus"], "value": [None, 0.25],
            "state": ['["top", "bot"]', '줄1\n줄2,"인용"'],
        })

    def dataset(self):
        return {
            **{key: self.frame.copy() for key in (
                "games", "actions", "training", "champion_history",
                "champion_position_history", "role_mapping_failures",
            )},
            "role_qa": {"passed": True},
        }

    def test_csv_bytes_match_original_pandas_save_on_windows_paths(self):
        expected = self.root / "기존 저장.csv"
        target = self.root / "lck_training_samples_2026_only.csv"
        self.frame.to_csv(expected, index=False, encoding="utf-8-sig")
        target.write_bytes(b"old CSV")
        builder.write_processed_csv(self.frame, target)
        self.assertEqual(target.read_bytes(), expected.read_bytes())
        self.assertTrue(target.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_suffix_rejected_before_any_write(self):
        for suffix in ("2026_only\n", "2026_only\x00", "2026_only\u200b", "2026_only ", "2026_only.", "../escape", "x:y", "", None):
            with self.subTest(suffix=repr(suffix)):
                with self.assertRaisesRegex(ValueError, "output_suffix"):
                    builder.save_dataset(self.dataset(), suffix)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_filename_and_path_components(self):
        for name in ("a\x01.csv", "a\u200b.csv", "a?.csv", "a.csv ", "a.csv.", "NUL.csv", "COM1.csv", "../a.csv"):
            with self.subTest(name=repr(name)):
                with self.assertRaises(ValueError):
                    builder.processed_output_paths({"test": name})
        for name in ("processed ", "processed.", "bad\u200b"):
            with self.subTest(directory=repr(name)), patch.object(builder, "PROCESSED_DIR", self.root / name):
                with self.assertRaises(ValueError):
                    builder.processed_output_paths({"test": "valid.csv"})

    def test_directory_at_csv_target_is_found_before_writing_other_files(self):
        collision = self.root / "lck_training_samples_2026_only.csv"
        collision.mkdir()
        with self.assertRaisesRegex(IsADirectoryError, "lck_training_samples_2026_only.csv"):
            builder.save_dataset(self.dataset(), "2026_only")
        self.assertEqual(list(self.root.iterdir()), [collision])

    def test_duplicate_paths_and_non_directory_root(self):
        with self.assertRaisesRegex(ValueError, "중복"):
            builder.processed_output_paths({"a": "Same.csv", "b": "same.csv"})
        file = self.root / "ordinary_file"
        file.write_text("existing", encoding="utf-8")
        with patch.object(builder, "PROCESSED_DIR", file):
            with self.assertRaises(NotADirectoryError):
                builder.processed_output_paths({"test": "valid.csv"})

    def test_errno22_during_write_preserves_old_csv_and_reports_stage(self):
        target = self.root / "lck_draft_actions_2026_only.csv"
        target.write_bytes(b"existing data")

        def failed_write(frame, file, **kwargs):
            file.write("partial new data")
            raise OSError(errno.EINVAL, "Invalid argument")

        with patch.object(pd.DataFrame, "to_csv", autospec=True, side_effect=failed_write):
            with self.assertRaises(OSError) as caught:
                builder.write_processed_csv(self.frame, target)
        self.assertEqual(caught.exception.errno, errno.EINVAL)
        self.assertIn("CSV 쓰기/파일 닫기", str(caught.exception))
        self.assertIn(repr(str(target)), str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(target.read_bytes(), b"existing data")
        self.assertEqual(list(self.root.iterdir()), [target])

    def test_replace_failure_preserves_old_csv(self):
        target = self.root / "lck_training_samples_2026_only.csv"
        target.write_bytes(b"existing data")
        with patch.object(builder.os, "replace", side_effect=PermissionError(errno.EACCES, "locked")):
            with self.assertRaisesRegex(OSError, "기존 CSV 교체"):
                builder.write_processed_csv(self.frame, target)
        self.assertEqual(target.read_bytes(), b"existing data")
        self.assertEqual(list(self.root.iterdir()), [target])

    def test_both_suffixes_produce_expected_files_and_preserve_input(self):
        dataset = self.dataset()
        original = dataset["actions"].copy(deep=True)
        for suffix in ("2025_2026", "2026_only"):
            builder.save_dataset(dataset, suffix)
            self.assertTrue((self.root / f"lck_draft_actions_{suffix}.csv").is_file())
            self.assertTrue((self.root / f"lck_training_samples_{suffix}.csv").is_file())
        self.assertEqual(len(list(self.root.iterdir())), 14)
        pd.testing.assert_frame_equal(dataset["actions"], original)


if __name__ == "__main__":
    unittest.main()
