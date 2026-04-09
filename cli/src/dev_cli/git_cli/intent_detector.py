"""Map natural-language git requests to git commands."""
from __future__ import annotations

import re

# (pattern, command_template)
# {branch}, {file}, {commit}, {message}, {remote} are placeholders the manager
# resolves interactively when needed.
_INTENT_MAP: list[tuple[re.Pattern, str]] = [
    # ── Status / info ──────────────────────────────────────────────────
    (re.compile(r"\b(what.s changed|show changes|git status|current status)\b", re.I),
     "git status"),
    (re.compile(r"\b(show|view|list).{0,15}(recent |last )?(commit|log|history)\b", re.I),
     "git log --oneline -15"),
    (re.compile(r"\bfull log\b", re.I),
     "git log --oneline -30"),
    (re.compile(r"\b(show|view).{0,10}last commit\b", re.I),
     "git show --stat HEAD"),
    (re.compile(r"\b(diff|what.s different|what changed)\b", re.I),
     "git diff"),
    (re.compile(r"\b(staged|what.s staged|diff.{0,10}staged)\b", re.I),
     "git diff --staged"),
    (re.compile(r"\b(list|show).{0,10}branch(es)?\b", re.I),
     "git branch -a"),
    (re.compile(r"\b(list|show).{0,10}tag(s)?\b", re.I),
     "git tag -l"),
    (re.compile(r"\bshow.{0,10}remote(s)?\b", re.I),
     "git remote -v"),
    (re.compile(r"\breflog\b", re.I),
     "git reflog --oneline -20"),
    (re.compile(r"\bshow.{0,10}stash(es)?\b", re.I),
     "git stash list"),

    # ── Undo / reset ───────────────────────────────────────────────────
    (re.compile(r"\bundo.{0,20}last commit.{0,20}keep.{0,10}(change|file|work)\b", re.I),
     "git reset --soft HEAD~1"),
    (re.compile(r"\bundo.{0,20}last commit\b", re.I),
     "git reset --soft HEAD~1"),
    (re.compile(r"\bdiscard.{0,20}last commit\b", re.I),
     "git reset --hard HEAD~1"),
    (re.compile(r"\b(revert|undo).{0,20}commit\b", re.I),
     "git revert HEAD --no-edit"),
    (re.compile(r"\bunstage.{0,20}(all|everything|file)?\b", re.I),
     "git reset HEAD"),
    (re.compile(r"\bdiscard.{0,20}(all )?(local |unstaged )?change(s)?\b", re.I),
     "git checkout -- ."),
    (re.compile(r"\bclean.{0,20}untracked\b", re.I),
     "git clean -fd"),

    # ── Stage / commit ─────────────────────────────────────────────────
    (re.compile(r"\bstage.{0,20}(all|everything)\b", re.I),
     "git add -A"),
    (re.compile(r"\b(commit|save).{0,20}change(s)?\b", re.I),
     'git commit -m "{message}"'),
    (re.compile(r"\bamend.{0,20}(last )?commit\b", re.I),
     "git commit --amend --no-edit"),
    (re.compile(r"\bamend.{0,20}message\b", re.I),
     'git commit --amend -m "{message}"'),

    # ── Branches ───────────────────────────────────────────────────────
    (re.compile(r"\b(create|new).{0,15}branch\b", re.I),
     "git checkout -b {branch}"),
    (re.compile(r"\b(switch|checkout|go to).{0,15}branch\b", re.I),
     "git checkout {branch}"),
    (re.compile(r"\bdelete.{0,15}branch\b", re.I),
     "git branch -d {branch}"),
    (re.compile(r"\bforce.{0,10}delete.{0,15}branch\b", re.I),
     "git branch -D {branch}"),
    (re.compile(r"\brename.{0,15}branch\b", re.I),
     "git branch -m {branch}"),

    # ── Merge / rebase / cherry-pick ───────────────────────────────────
    (re.compile(r"\bmerge.{0,15}branch\b", re.I),
     "git merge {branch}"),
    (re.compile(r"\brebase.{0,15}(onto|on)?.{0,15}(main|master|{branch})\b", re.I),
     "git rebase {branch}"),
    (re.compile(r"\bcherry.pick.{0,20}(last |latest )?commit\b", re.I),
     "git cherry-pick HEAD"),
    (re.compile(r"\bcherry.pick\b", re.I),
     "git cherry-pick {commit}"),

    # ── Push / pull / fetch ────────────────────────────────────────────
    (re.compile(r"\bpush.{0,20}force\b", re.I),
     "git push --force-with-lease"),
    (re.compile(r"\b(push|publish).{0,20}(branch|changes|code)?\b", re.I),
     "git push"),
    (re.compile(r"\bpull.{0,20}(latest|changes|update)?\b", re.I),
     "git pull"),
    (re.compile(r"\bfetch\b", re.I),
     "git fetch --all"),

    # ── Stash ──────────────────────────────────────────────────────────
    (re.compile(r"\bstash.{0,20}(my |the )?(change|work)\b", re.I),
     "git stash"),
    (re.compile(r"\b(pop|apply|restore).{0,15}stash\b", re.I),
     "git stash pop"),
    (re.compile(r"\bdrop.{0,15}stash\b", re.I),
     "git stash drop"),

    # ── Tags ───────────────────────────────────────────────────────────
    (re.compile(r"\b(create|add).{0,15}tag\b", re.I),
     "git tag {tag}"),
    (re.compile(r"\bpush.{0,15}tag(s)?\b", re.I),
     "git push --tags"),
]


def detect_git_intent(message: str) -> str | None:
    """Return a git command template if the message expresses a git intent."""
    for pattern, template in _INTENT_MAP:
        if pattern.search(message):
            return template
    return None


def is_git_related(message: str) -> bool:
    keywords = re.compile(
        r"\b(git|commit|branch|merge|rebase|cherry.pick|stash|push|pull|"
        r"checkout|diff|log|reset|revert|tag|reflog|remote|fetch|undo.{0,10}commit)\b",
        re.I,
    )
    return bool(keywords.search(message))
