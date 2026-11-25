"""gimera outdated: compare the pinned sha of each repo with its branch head.

Read-only on purpose: the branch head comes from `git ls-remote` against the
url in gimera.yml, so neither the golden cache, nor the working tree, nor
gimera.yml is touched. A pin that is only behind because nobody bumped it
(e.g. a shared ansible role pinned in many project repos) shows up here
without running `gimera apply --update` first.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from .consts import gitcmd as git
from .consts import REPO_TYPE_SUB

CURRENT = "current"
OUTDATED = "outdated"
UNKNOWN = "unknown"
FROZEN = "frozen"
DISABLED = "disabled"

TIMEOUT_ENV = "GIMERA_LS_REMOTE_TIMEOUT"
DEFAULT_TIMEOUT = 30

EXIT_OUTDATED = 1
EXIT_UNKNOWN = 2


@dataclass
class PinState:
    path: str
    type: str
    branch: str
    pinned: Optional[str]
    head: Optional[str]
    status: str
    reason: str = ""


class RemoteError(Exception):
    pass


def _timeout():
    value = os.environ.get(TIMEOUT_ENV)
    if not value:
        return DEFAULT_TIMEOUT
    try:
        return float(value)
    except ValueError:
        raise RemoteError(f"{TIMEOUT_ENV} must be a number of seconds, got {value!r}")


def _git_env():
    env = dict(os.environ)
    # Never hang on a password prompt or an unknown host key - an
    # unreachable remote is a result here, not a reason to wait.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def ls_remote_head(url, branch):
    """Sha the branch (or tag) points to on the remote.

    Raises RemoteError with a readable reason instead of letting a
    CalledProcessError or a timeout escape.
    """
    refs = [f"refs/heads/{branch}", f"refs/tags/{branch}", f"refs/tags/{branch}^{{}}"]
    timeout = _timeout()
    try:
        proc = subprocess.run(
            git + ["ls-remote", url] + refs,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_git_env(),
        )
    except subprocess.TimeoutExpired:
        raise RemoteError(f"remote did not answer within {timeout:g}s")
    except OSError as ex:
        raise RemoteError(f"could not run git: {ex}")
    if proc.returncode:
        lines = [x.strip() for x in (proc.stderr or "").splitlines() if x.strip()]
        raise RemoteError(lines[-1] if lines else f"git ls-remote exited with {proc.returncode}")

    found = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            found[parts[1]] = parts[0]
    # A branch wins over a tag of the same name; an annotated tag is
    # compared by the commit it points to (the peeled ^{} entry).
    for ref in (refs[0], refs[2], refs[1]):
        if ref in found:
            return found[ref]
    raise RemoteError(f"branch '{branch}' not found on remote")


def _gitlink_sha(main_repo, path):
    """Sha the parent repo records for a submodule, without touching it."""
    try:
        proc = subprocess.run(
            git + ["ls-tree", "HEAD", "--", str(path)],
            capture_output=True,
            text=True,
            cwd=main_repo,
        )
    except OSError:
        return None
    parts = proc.stdout.split()
    if proc.returncode == 0 and len(parts) >= 3 and parts[1] == "commit":
        return parts[2]
    return None


def check_repo(repo, main_repo=None, ls_remote=ls_remote_head):
    """PinState for one Config.RepoItem."""
    pinned = repo.sha
    if not pinned and repo.type == REPO_TYPE_SUB and main_repo is not None:
        pinned = _gitlink_sha(main_repo, repo.path)
    state = PinState(
        path=str(repo.path),
        type=repo.type,
        branch=str(repo.branch),
        pinned=pinned or None,
        head=None,
        status=UNKNOWN,
    )
    if not repo.enabled:
        state.status = DISABLED
        state.reason = "enabled: false"
        return state

    try:
        state.head = ls_remote(repo.url, repo.branch)
    except RemoteError as ex:
        state.reason = str(ex)
        if repo.freeze_sha:
            # Frozen on purpose - the remote does not decide anything here.
            state.status = FROZEN
            state.reason = f"freeze_sha; {ex}"
        return state

    if repo.freeze_sha:
        state.status = FROZEN
        state.reason = "freeze_sha"
    elif not state.pinned:
        state.reason = "no sha pinned in gimera.yml"
    elif state.pinned == state.head:
        state.status = CURRENT
    else:
        state.status = OUTDATED
    return state


def exit_code(states):
    statuses = {x.status for x in states}
    if OUTDATED in statuses:
        return EXIT_OUTDATED
    if UNKNOWN in statuses:
        return EXIT_UNKNOWN
    return 0
