from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dev_cli.context.file_ops import FileOpKind, FileOpIntent, detect_file_op
from dev_cli.context.file_reader import FileContext, FileContextReader
from dev_cli.context.file_writer import (
    DetectedFile,
    FileAction,
    apply_patch,
    parse_files,
)


# ---------------------------------------------------------------------------
# FileContext
# ---------------------------------------------------------------------------

class TestFileContext:
    def test_add_file_returns_true(self):
        ctx = FileContext()
        assert ctx.add("foo.py", "print('hello')") is True
        assert "foo.py" in ctx.files

    def test_add_duplicate_path_is_allowed(self):
        ctx = FileContext()
        ctx.add("foo.py", "a")
        ctx.add("foo.py", "b")
        # Second add overwrites; no duplicate tracking enforced — just two adds
        assert ctx.files["foo.py"] == "b"

    def test_file_count_limit(self):
        ctx = FileContext()
        for i in range(20):
            ctx.add(f"file{i}.py", "x")
        result = ctx.add("overflow.py", "x")
        assert result is False
        assert "overflow.py" not in ctx.files

    def test_total_bytes_limit(self):
        # Use chunks smaller than the 10 MB per-file cap so they aren't truncated.
        # 6 × 9 MB = 54 MB which exceeds the 50 MB total limit.
        ctx = FileContext()
        chunk = "x" * (9 * 1024 * 1024)  # 9 MB — under per-file limit
        for i in range(5):
            ctx.add(f"file{i}.py", chunk)   # 5 × 9 MB = 45 MB
        result = ctx.add("overflow.py", chunk)  # would push to 54 MB
        assert result is False

    def test_to_prompt_block_empty(self):
        ctx = FileContext()
        assert ctx.to_prompt_block() == ""

    def test_to_prompt_block_contains_path_and_content(self):
        ctx = FileContext()
        ctx.add("src/main.py", "print('hi')")
        block = ctx.to_prompt_block()
        assert "src/main.py" in block
        assert "print('hi')" in block

    def test_summary_empty(self):
        ctx = FileContext()
        assert ctx.summary == "no files"

    def test_summary_with_files(self):
        ctx = FileContext()
        ctx.add("a.py", "")
        ctx.add("b.py", "")
        assert "2 file(s)" in ctx.summary
        assert "a.py" in ctx.summary


# ---------------------------------------------------------------------------
# FileContextReader
# ---------------------------------------------------------------------------

class TestFileContextReader:
    def test_explicit_file_in_message(self, tmp_path):
        (tmp_path / "auth.py").write_text("# auth")
        reader = FileContextReader(tmp_path)
        ctx = reader.build("look at auth.py please")
        assert "auth.py" in ctx.summary

    def test_intent_pattern_test(self, tmp_path):
        (tmp_path / "test_foo.py").write_text("# tests here")
        reader = FileContextReader(tmp_path)
        ctx = reader.build("can you fix the test")
        assert any("test" in k for k in ctx.files)

    def test_intent_pattern_config(self, tmp_path):
        (tmp_path / "config.yaml").write_text("key: val")
        reader = FileContextReader(tmp_path)
        ctx = reader.build("check the config settings")
        assert any("config" in k for k in ctx.files)

    def test_intent_pattern_docker(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.11")
        reader = FileContextReader(tmp_path)
        ctx = reader.build("update the docker setup")
        assert any("Dockerfile" in k for k in ctx.files)

    def test_intent_pattern_terraform(self, tmp_path):
        (tmp_path / "main.tf").write_text('resource "aws_lambda_function" "fn" {}')
        reader = FileContextReader(tmp_path)
        ctx = reader.build("update the terraform config")
        assert any(".tf" in k for k in ctx.files)

    def test_fallback_readme(self, tmp_path):
        (tmp_path / "README.md").write_text("# Project")
        reader = FileContextReader(tmp_path)
        ctx = reader.build("help me understand this project")
        assert any("README" in k for k in ctx.files)

    def test_read_explicit(self, tmp_path):
        (tmp_path / "settings.toml").write_text("[settings]\nkey=val")
        reader = FileContextReader(tmp_path)
        ctx = reader.read_explicit(["settings.toml"])
        assert "settings.toml" in ctx.files

    def test_non_code_file_excluded(self, tmp_path):
        (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02")
        reader = FileContextReader(tmp_path)
        ctx = reader.read_explicit(["data.bin"])
        assert ctx.files == {}

    def test_deduplication(self, tmp_path):
        (tmp_path / "app.py").write_text("# app")
        reader = FileContextReader(tmp_path)
        # app.py could match multiple patterns — should only appear once
        ctx = reader.build("look at app.py and look at app.py again")
        count = sum(1 for k in ctx.files if "app.py" in k)
        assert count == 1


# ---------------------------------------------------------------------------
# parse_files (file_writer)
# ---------------------------------------------------------------------------

class TestParseFiles:
    def test_pattern1_header_above_block(self):
        response = "### `main.tf`\n```hcl\nresource \"aws_lambda_function\" \"fn\" {}\n```"
        files = parse_files(response)
        assert len(files) == 1
        assert files[0].path == "main.tf"
        assert files[0].action == FileAction.CREATE

    def test_pattern2_comment_inside_block(self):
        response = "```python\n# src/handler.py\nimport json\n```"
        files = parse_files(response)
        assert len(files) == 1
        assert files[0].path == "src/handler.py"
        assert "import json" in files[0].content

    def test_pattern3_inline_path_after_lang(self):
        response = "```hcl main.tf\nresource \"aws_s3_bucket\" \"b\" {}\n```"
        files = parse_files(response)
        assert len(files) == 1
        assert files[0].path == "main.tf"

    def test_pattern4_diff_block(self):
        response = (
            "```diff\n"
            "--- a/main.tf\n"
            "+++ b/main.tf\n"
            "@@ -1,2 +1,3 @@\n"
            " resource {\n"
            "+  key = \"val\"\n"
            " }\n"
            "```"
        )
        files = parse_files(response)
        assert len(files) == 1
        assert files[0].action == FileAction.PATCH
        assert files[0].path == "main.tf"

    def test_no_filename_returns_empty(self):
        response = "```python\nprint('hello')\n```"
        files = parse_files(response)
        assert files == []

    def test_non_writable_extension_skipped(self):
        response = "### `image.png`\n```\nbinary data\n```"
        files = parse_files(response)
        assert files == []

    def test_multiple_files_in_response(self):
        response = (
            "### `a.py`\n```python\nprint('a')\n```\n\n"
            "### `b.tf`\n```hcl\nresource {}\n```"
        )
        files = parse_files(response)
        assert len(files) == 2
        paths = {f.path for f in files}
        assert "a.py" in paths
        assert "b.tf" in paths

    def test_replace_action_when_file_exists(self, tmp_path):
        (tmp_path / "existing.py").write_text("old content\n")
        response = "### `existing.py`\n```python\nnew content\n```"
        files = parse_files(response, project_root=tmp_path)
        assert files[0].action == FileAction.REPLACE
        assert files[0].diff_preview != ""

    def test_create_action_when_file_missing(self, tmp_path):
        response = "### `new_file.py`\n```python\nprint('new')\n```"
        files = parse_files(response, project_root=tmp_path)
        assert files[0].action == FileAction.CREATE

    def test_deduplication_same_path(self):
        response = (
            "### `foo.py`\n```python\nfirst\n```\n"
            "### `foo.py`\n```python\nsecond\n```"
        )
        files = parse_files(response)
        assert len(files) == 1


# ---------------------------------------------------------------------------
# apply_patch
# ---------------------------------------------------------------------------

class TestApplyPatch:
    def test_adds_line(self):
        original = "line1\nline2\nline3\n"
        diff = (
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            " line2\n"
            "+new line\n"
            " line3\n"
        )
        result = apply_patch(original, diff)
        assert result is not None
        assert "new line" in result

    def test_removes_line(self):
        original = "line1\nline2\nline3\n"
        diff = (
            "@@ -1,3 +1,2 @@\n"
            " line1\n"
            "-line2\n"
            " line3\n"
        )
        result = apply_patch(original, diff)
        assert result is not None
        assert "line2" not in result

    def test_no_hunks_returns_none(self):
        result = apply_patch("content\n", "no hunk markers here")
        assert result is None

    def test_empty_diff_returns_none(self):
        result = apply_patch("content\n", "")
        assert result is None


# ---------------------------------------------------------------------------
# detect_file_op
# ---------------------------------------------------------------------------

class TestDetectFileOp:
    def test_detect_delete(self):
        intent = detect_file_op("please delete old_script.py")
        assert intent is not None
        assert intent.kind == FileOpKind.DELETE
        assert "old_script.py" in intent.path

    def test_detect_remove(self):
        intent = detect_file_op("remove main.tf from the project")
        assert intent is not None
        assert intent.kind == FileOpKind.DELETE

    def test_detect_rename(self):
        intent = detect_file_op("rename handler.py to lambda_handler.py")
        assert intent is not None
        assert intent.kind == FileOpKind.RENAME
        assert "handler.py" in intent.path
        assert "lambda_handler.py" in intent.dest

    def test_detect_move(self):
        intent = detect_file_op("move config.yaml to settings.yaml")
        assert intent is not None
        assert intent.kind == FileOpKind.RENAME

    def test_no_intent_general_message(self):
        assert detect_file_op("explain this code") is None
        assert detect_file_op("run the tests") is None

    def test_non_operable_extension_ignored(self):
        # .png is not in _OPERABLE_EXTENSIONS
        intent = detect_file_op("delete photo.png")
        assert intent is None

    def test_rename_detected_before_delete(self):
        # "rename" message shouldn't be treated as delete
        intent = detect_file_op("rename old.py to new.py")
        assert intent is not None
        assert intent.kind == FileOpKind.RENAME
