"""Classify AWS CLI commands as read / modify / delete.

This determines how much confirmation to ask from the user before running.
"""
from __future__ import annotations

from enum import StrEnum


class CommandRisk(StrEnum):
    READ = "read"       # safe — no confirmation needed
    MODIFY = "modify"   # requires one confirmation
    DELETE = "delete"   # requires double confirmation


# Sub-commands that are read-only
_READ_VERBS = frozenset({
    "describe", "list", "get", "tail", "head", "show",
    "lookup", "scan", "query", "check", "view", "info",
    "search", "filter", "ls",
})

# Sub-commands that modify state
_MODIFY_VERBS = frozenset({
    "update", "put", "create", "attach", "detach", "modify",
    "start", "stop", "reboot", "invoke", "publish", "deploy",
    "add", "set", "enable", "disable", "associate", "disassociate",
    "tag", "untag",
})

# Sub-commands that destroy state
_DELETE_VERBS = frozenset({
    "delete", "remove", "terminate", "deregister", "purge",
    "destroy", "cancel", "revoke", "reset",
})


def classify(command: str) -> CommandRisk:
    """Classify an AWS CLI command string by its risk level."""
    # Strip leading 'aws' token if present
    tokens = command.strip().split()
    if tokens and tokens[0].lower() == "aws":
        tokens = tokens[1:]

    # Look for the sub-command verb (usually the second token after the service)
    # e.g. "logs tail ..." → verb="tail", "lambda update-function-configuration" → verb="update"
    for token in tokens:
        # handle hyphenated verbs like "update-function-configuration"
        verb = token.lower().split("-")[0]
        if verb in _DELETE_VERBS:
            return CommandRisk.DELETE
        if verb in _MODIFY_VERBS:
            return CommandRisk.MODIFY
        if verb in _READ_VERBS:
            return CommandRisk.READ

    # Default to modify if unknown (safer than assuming read)
    return CommandRisk.MODIFY
