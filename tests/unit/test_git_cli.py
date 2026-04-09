from __future__ import annotations

import pytest

from dev_cli.git_cli.command_classifier import GitRisk, classify
from dev_cli.git_cli.intent_detector import detect_git_intent, is_git_related


# ---------------------------------------------------------------------------
# command_classifier
# ---------------------------------------------------------------------------

class TestGitCommandClassifier:
    def test_read_commands(self):
        assert classify("git log --oneline -15") == GitRisk.READ
        assert classify("git status") == GitRisk.READ
        assert classify("git diff") == GitRisk.READ
        assert classify("git show HEAD") == GitRisk.READ
        assert classify("git branch -a") == GitRisk.READ
        assert classify("git tag -l") == GitRisk.READ
        assert classify("git reflog --oneline") == GitRisk.READ
        assert classify("git stash list") == GitRisk.READ

    def test_modify_commands(self):
        assert classify("git add -A") == GitRisk.MODIFY
        assert classify("git commit -m 'fix'") == GitRisk.MODIFY
        assert classify("git push") == GitRisk.MODIFY
        assert classify("git merge main") == GitRisk.MODIFY
        assert classify("git rebase main") == GitRisk.MODIFY
        assert classify("git cherry-pick abc123") == GitRisk.MODIFY
        assert classify("git checkout -b feature") == GitRisk.MODIFY
        assert classify("git revert HEAD --no-edit") == GitRisk.MODIFY
        assert classify("git pull") == GitRisk.MODIFY

    def test_destructive_flags(self):
        assert classify("git reset --hard HEAD~1") == GitRisk.DESTRUCTIVE
        assert classify("git push --force") == GitRisk.DESTRUCTIVE
        assert classify("git push -f") == GitRisk.DESTRUCTIVE
        assert classify("git push --force-with-lease") == GitRisk.DESTRUCTIVE
        assert classify("git branch -D old-branch") == GitRisk.DESTRUCTIVE

    def test_destructive_subcommands(self):
        assert classify("git clean -fd") == GitRisk.DESTRUCTIVE

    def test_reset_variants(self):
        assert classify("git reset --soft HEAD~1") == GitRisk.MODIFY
        assert classify("git reset --mixed HEAD~1") == GitRisk.MODIFY
        assert classify("git reset --hard HEAD~1") == GitRisk.DESTRUCTIVE

    def test_strips_git_prefix(self):
        assert classify("git status") == classify("status")
        assert classify("git log") == classify("log")

    def test_empty_command(self):
        assert classify("git") == GitRisk.MODIFY

    def test_unknown_command_defaults_to_modify(self):
        assert classify("git unknowncmd") == GitRisk.MODIFY


# ---------------------------------------------------------------------------
# intent_detector
# ---------------------------------------------------------------------------

class TestGitIntentDetector:
    def test_undo_last_commit(self):
        result = detect_git_intent("undo my last commit")
        assert result is not None
        assert "reset" in result
        assert "--soft" in result

    def test_undo_last_commit_keep_changes(self):
        result = detect_git_intent("undo last commit keep changes")
        assert result is not None
        assert "--soft" in result

    def test_discard_last_commit(self):
        result = detect_git_intent("discard my last commit")
        assert result is not None
        assert "--hard" in result

    def test_show_log(self):
        result = detect_git_intent("show recent commits")
        assert result is not None
        assert "log" in result

    def test_git_status(self):
        result = detect_git_intent("what's changed")
        assert result is not None
        assert "status" in result

    def test_cherry_pick_last(self):
        result = detect_git_intent("cherry pick from last commit")
        assert result is not None
        assert "cherry-pick" in result
        assert "HEAD" in result

    def test_cherry_pick_specific(self):
        result = detect_git_intent("cherry pick commit abc123")
        assert result is not None
        assert "cherry-pick" in result

    def test_create_branch(self):
        result = detect_git_intent("create a new branch")
        assert result is not None
        assert "checkout -b" in result or "switch -c" in result

    def test_stash_changes(self):
        result = detect_git_intent("stash my changes")
        assert result is not None
        assert "stash" in result

    def test_pop_stash(self):
        result = detect_git_intent("pop the stash")
        assert result is not None
        assert "stash pop" in result

    def test_push(self):
        result = detect_git_intent("push my changes")
        assert result is not None
        assert "push" in result

    def test_pull(self):
        result = detect_git_intent("pull latest changes")
        assert result is not None
        assert "pull" in result

    def test_show_diff(self):
        result = detect_git_intent("what's different")
        assert result is not None
        assert "diff" in result

    def test_amend_commit(self):
        result = detect_git_intent("amend the last commit")
        assert result is not None
        assert "amend" in result

    def test_no_git_intent(self):
        assert detect_git_intent("can you create a terraform file") is None
        assert detect_git_intent("explain this python function") is None
        assert detect_git_intent("what is the weather") is None

    def test_case_insensitive(self):
        assert detect_git_intent("SHOW RECENT COMMITS") is not None
        assert detect_git_intent("Undo My Last Commit") is not None

    def test_is_git_related(self):
        assert is_git_related("undo my last commit") is True
        assert is_git_related("show git log") is True
        assert is_git_related("create a new branch") is True
        assert is_git_related("cherry-pick that fix") is True
        assert is_git_related("write a python function") is False
        assert is_git_related("deploy to AWS") is False
