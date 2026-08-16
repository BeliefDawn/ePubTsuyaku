import json
import tempfile
import unittest
from pathlib import Path

from translator.progress import PROGRESS_VERSION, load_progress, save_progress
from translator.state import new_story_state


class ProgressPersistenceTests(unittest.TestCase):
    def test_load_progress_migrates_legacy_document_records(self):
        legacy_progress = {
            "version": 2,
            "input_path": "/tmp/input.epub",
            "output_path": "/tmp/output.epub",
            "source_language": "日语",
            "target_language": "中文",
            "book": {"title": "Book", "author": "Author"},
            "story_state": new_story_state({"title": "Book", "author": "Author"}),
            "documents": {
                "chapter1.xhtml": {
                    "file_name": "chapter1.xhtml",
                    "item_id": "chapter1",
                    "status": "done",
                    "source_hash": "hash-1",
                    "translated_html": "<html></html>",
                    "segment_count": 3,
                    "reviews": [],
                    "story_state_after": {},
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            progress_path = Path(tmp_dir) / "progress.json"
            progress_path.write_text(json.dumps(legacy_progress, ensure_ascii=False), encoding="utf-8")

            migrated = load_progress(progress_path)

        self.assertEqual(migrated["version"], PROGRESS_VERSION)
        self.assertFalse(migrated["reference_enabled"])
        self.assertEqual(migrated["reference_phase"]["status"], "disabled")
        self.assertIn("summary_phase", migrated)
        self.assertIn("translation_phase", migrated)
        self.assertIn("reference_phase", migrated)
        self.assertEqual(migrated["documents"]["chapter1.xhtml"]["translation_status"], "done")
        self.assertEqual(migrated["documents"]["chapter1.xhtml"]["summary_status"], "pending")

    def test_save_progress_omits_rebuildable_translated_html(self):
        progress = {
            "version": PROGRESS_VERSION,
            "input_path": "/tmp/input.epub",
            "output_path": "/tmp/output.epub",
            "source_language": "日语",
            "target_language": "中文",
            "book": {"title": "Book", "author": "Author"},
            "story_state": new_story_state({"title": "Book", "author": "Author"}),
            "documents": {
                "chapter1.xhtml": {
                    "file_name": "chapter1.xhtml",
                    "item_id": "chapter1",
                    "source_hash": "hash-1",
                    "segment_count": 2,
                    "batch_count": 2,
                    "summary_status": "done",
                    "summary_patch": {},
                    "translation_context_snapshot": {"events": ["事件"]},
                    "translation_status": "done",
                    "translated_html": "<html>large translated body</html>",
                    "translated_batches": {
                        "batch_0001": {
                            "batch_index": 1,
                            "translations": {"seg_0001": "译文一"},
                            "review": {},
                        },
                        "batch_0002": {
                            "batch_index": 2,
                            "translations": {"seg_0002": "译文二"},
                            "review": {},
                        },
                    },
                    "reviews": [],
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            progress_path = Path(tmp_dir) / "progress.json"
            save_progress(progress_path, progress)
            saved = json.loads(progress_path.read_text(encoding="utf-8"))

        saved_record = saved["documents"]["chapter1.xhtml"]
        self.assertEqual(saved_record["translation_status"], "done")
        self.assertEqual(saved_record["translated_html"], "")
        self.assertEqual(saved_record["translated_batches"]["batch_0001"]["translations"]["seg_0001"], "译文一")


if __name__ == "__main__":
    unittest.main()
