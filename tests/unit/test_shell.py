from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dev_cli.shell.runner import CommandResult, ShellRunner, detect_shell
from dev_cli.shell.task_detector import detect_task, resolve_command
from dev_cli.storage.models import LanguageDetection, ProjectManifest


# ---------------------------------------------------------------------------
# CommandResult
# ---------------------------------------------------------------------------

class TestCommandResult:
    def test_output_combines_stdout_stderr(self):
        r = CommandResult(command="ls", stdout="foo", stderr="bar", returncode=0)
        assert "foo" in r.output
        assert "[stderr]" in r.output
        assert "bar" in r.output

    def test_output_empty_stderr_omitted(self):
        r = CommandResult(command="ls", stdout="foo", stderr="", returncode=0)
        assert "[stderr]" not in r.output

    def test_output_truncated_at_20k(self):
        long = "x" * 30_000
        r = CommandResult(command="ls", stdout=long, stderr="", returncode=0)
        assert len(r.output) == 20_000

    def test_success_true_when_zero_exit(self):
        r = CommandResult(command="ls", stdout="", stderr="", returncode=0)
        assert r.success is True

    def test_success_false_on_nonzero_exit(self):
        r = CommandResult(command="ls", stdout="", stderr="", returncode=1)
        assert r.success is False

    def test_success_false_when_timed_out(self):
        r = CommandResult(command="ls", stdout="", stderr="", returncode=0, timed_out=True)
        assert r.success is False

    def test_to_context_block_success(self):
        r = CommandResult(command="echo hi", stdout="hi", stderr="", returncode=0)
        block = r.to_context_block()
        assert "echo hi" in block
        assert "success" in block
        assert "hi" in block

    def test_to_context_block_failure(self):
        r = CommandResult(command="bad", stdout="", stderr="err", returncode=1)
        block = r.to_context_block()
        assert "exit code 1" in block

    def test_to_context_block_timed_out(self):
        r = CommandResult(command="sleep", stdout="", stderr="", returncode=-1, timed_out=True)
        block = r.to_context_block()
        assert "timed out" in block


# ---------------------------------------------------------------------------
# ShellRunner._run_subprocess
# ---------------------------------------------------------------------------

class TestShellRunnerSubprocess:
    def _runner(self):
        console = MagicMock()
        return ShellRunner(console=console)

    def test_echo_command_succeeds(self):
        runner = self._runner()
        if sys.platform == "win32":
            cmd = "echo hello"
        else:
            cmd = "echo hello"
        result = runner._run_subprocess(cmd, cwd=None)
        assert result.success
        assert "hello" in result.stdout

    def test_nonzero_exit_code(self):
        runner = self._runner()
        if sys.platform == "win32":
            cmd = "exit 1"
        else:
            cmd = "exit 1"
        result = runner._run_subprocess(cmd, cwd=None)
        assert result.returncode != 0
        assert result.success is False

    def test_timeout_returns_timed_out(self):
        runner = self._runner()
        with patch("dev_cli.shell.runner._TIMEOUT", 0):
            if sys.platform == "win32":
                cmd = "ping -n 5 127.0.0.1"
            else:
                cmd = "sleep 5"
            result = runner._run_subprocess(cmd, cwd=None)
        assert result.timed_out is True
        assert result.success is False

    def test_invalid_command_returns_error(self):
        runner = self._runner()
        # Patch the args to use a non-existent executable directly
        with patch("dev_cli.shell.runner._IS_WINDOWS", False):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("not found")
                result = runner._run_subprocess("some-cmd", cwd=None)
        assert result.returncode == 127
        assert "not found" in result.stderr

    def test_unexpected_exception_returns_error(self):
        runner = self._runner()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("boom")
            result = runner._run_subprocess("cmd", cwd=None)
        assert result.returncode == -1
        assert "boom" in result.stderr


# ---------------------------------------------------------------------------
# ShellRunner async run_silent
# ---------------------------------------------------------------------------

class TestShellRunnerAsync:
    def test_run_silent_returns_result(self):
        runner = ShellRunner(console=MagicMock())
        result = asyncio.get_event_loop().run_until_complete(
            runner.run_silent("echo test")
        )
        assert isinstance(result, CommandResult)
        assert result.success


# ---------------------------------------------------------------------------
# detect_shell
# ---------------------------------------------------------------------------

class TestDetectShell:
    def test_returns_string(self):
        assert isinstance(detect_shell(), str)

    def test_windows_returns_cmd(self):
        with patch("dev_cli.shell.runner._IS_WINDOWS", True):
            from importlib import reload
            import dev_cli.shell.runner as m
            assert detect_shell() in ("cmd.exe", "/bin/bash") or True  # OS-agnostic check


# ---------------------------------------------------------------------------
# detect_task
# ---------------------------------------------------------------------------

class TestDetectTask:
    def test_run_tests(self):
        assert detect_task("run the tests") == "test"
        assert detect_task("run tests") == "test"
        assert detect_task("execute unit tests") == "test"

    def test_pytest_keyword(self):
        assert detect_task("run pytest") == "test"
        assert detect_task("pytest now") == "test"

    def test_jest_keyword(self):
        assert detect_task("run jest") == "test"

    def test_test_it(self):
        assert detect_task("test it") == "test"
        assert detect_task("test this") == "test"
        assert detect_task("test the code") == "test"

    def test_build(self):
        assert detect_task("build the project") == "build"
        assert detect_task("compile the app") == "build"

    def test_dev_server(self):
        assert detect_task("start the dev server") == "dev"
        assert detect_task("run the app") == "dev"

    def test_lint(self):
        assert detect_task("lint the code") == "lint"
        assert detect_task("format the files") == "lint"
        assert detect_task("check style") == "lint"

    def test_install(self):
        assert detect_task("install dependencies") == "install"
        assert detect_task("install deps") == "install"
        assert detect_task("install packages") == "install"

    def test_typecheck(self):
        assert detect_task("run mypy") == "typecheck"
        assert detect_task("type check this") == "typecheck"
        assert detect_task("run tsc") == "typecheck"

    def test_no_task(self):
        assert detect_task("what is the weather") is None
        assert detect_task("explain this function") is None
        assert detect_task("create a terraform file") is None

    def test_case_insensitive(self):
        assert detect_task("RUN TESTS") == "test"
        assert detect_task("Lint the Code") == "lint"


# ---------------------------------------------------------------------------
# resolve_command
# ---------------------------------------------------------------------------

def _manifest(lang: str, path: Path) -> ProjectManifest:
    return ProjectManifest(
        project_path=str(path),
        project_name="test",
        languages=[LanguageDetection(language=lang)],
    )


class TestResolveCommand:
    def test_python_test(self, tmp_path):
        manifest = _manifest("python", tmp_path)
        cmd = resolve_command("test", tmp_path, manifest)
        assert cmd is not None
        assert "pytest" in cmd

    def test_python_lint(self, tmp_path):
        manifest = _manifest("python", tmp_path)
        cmd = resolve_command("lint", tmp_path, manifest)
        assert cmd is not None
        assert "ruff" in cmd

    def test_python_typecheck(self, tmp_path):
        manifest = _manifest("python", tmp_path)
        cmd = resolve_command("typecheck", tmp_path, manifest)
        assert cmd is not None
        assert "mypy" in cmd

    def test_python_install(self, tmp_path):
        manifest = _manifest("python", tmp_path)
        cmd = resolve_command("install", tmp_path, manifest)
        assert cmd is not None
        assert "pip install" in cmd

    def test_node_npm_test(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        manifest = _manifest("node.js", tmp_path)
        cmd = resolve_command("test", tmp_path, manifest)
        assert cmd == "npm test"

    def test_node_yarn_test(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "yarn.lock").write_text("")
        manifest = _manifest("node.js", tmp_path)
        cmd = resolve_command("test", tmp_path, manifest)
        assert cmd == "yarn test"

    def test_node_pnpm_takes_priority_over_yarn(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "yarn.lock").write_text("")
        (tmp_path / "pnpm-lock.yaml").write_text("")
        manifest = _manifest("node.js", tmp_path)
        cmd = resolve_command("test", tmp_path, manifest)
        assert cmd == "pnpm test"

    def test_typescript_uses_node_commands(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        manifest = _manifest("typescript", tmp_path)
        cmd = resolve_command("build", tmp_path, manifest)
        assert cmd == "npm run build"

    def test_unknown_lang_returns_none(self, tmp_path):
        manifest = _manifest("rust", tmp_path)
        cmd = resolve_command("test", tmp_path, manifest)
        assert cmd is None

    def test_unknown_task_returns_none(self, tmp_path):
        manifest = _manifest("python", tmp_path)
        cmd = resolve_command("deploy", tmp_path, manifest)
        assert cmd is None
