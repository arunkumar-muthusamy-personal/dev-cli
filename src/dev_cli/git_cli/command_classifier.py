"""Classify git commands by risk level."""
from __future__ import annotations

from enum import StrEnum


class GitRisk(StrEnum):
    READ        = "read"         # safe — no confirmation
    MODIFY      = "modify"       # one confirmation
    DESTRUCTIVE = "destructive"  # double confirmation — can lose work


_READ_SUBCOMMANDS = frozenset({
    "log", "status", "diff", "show", "branch", "tag",
    "stash", "remote", "shortlog", "describe", "ls-files",
    "ls-tree", "rev-parse", "reflog",
})

_MODIFY_SUBCOMMANDS = frozenset({
    "add", "commit", "push", "merge", "rebase", "cherry-pick",
    "checkout", "switch", "restore", "stash", "tag", "fetch",
    "pull", "mv", "rm", "config", "submodule", "worktree",
    "revert",
})

_DESTRUCTIVE_FLAGS = frozenset({
    "--hard", "--force", "-f", "--force-with-lease",
    "-D",  # branch -D
})

_DESTRUCTIVE_SUBCOMMANDS = frozenset({
    "clean",
})


def classify(command: str) -> GitRisk:
    tokens = command.strip().split()
    # Strip leading 'git'
    if tokens and tokens[0].lower() == "git":
        tokens = tokens[1:]
    if not tokens:
        return GitRisk.MODIFY

    sub = tokens[0].lower()
    # Preserve case: git flags like -D (force-delete branch) are case-sensitive
    flags = set(tokens[1:])

    if sub in _DESTRUCTIVE_SUBCOMMANDS:
        return GitRisk.DESTRUCTIVE
    if flags & _DESTRUCTIVE_FLAGS:
        return GitRisk.DESTRUCTIVE
    if sub == "reset":
        # reset --soft / --mixed is recoverable; --hard is destructive
        if "--hard" in flags:
            return GitRisk.DESTRUCTIVE
        return GitRisk.MODIFY
    if sub in _READ_SUBCOMMANDS and not (flags & _DESTRUCTIVE_FLAGS):
        return GitRisk.READ
    if sub in _MODIFY_SUBCOMMANDS:
        return GitRisk.MODIFY

    return GitRisk.MODIFY
