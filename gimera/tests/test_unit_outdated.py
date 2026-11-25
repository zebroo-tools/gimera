"""Tests for `gimera outdated`.

Uses local bare repos as remotes, so git ls-remote runs for real but
without network.
"""
import subprocess

import pytest
import yaml
from click.testing import CliRunner

from ..consts import gitcmd as git
from ..gimera import cli


def _git(cwd, *args):
    return subprocess.check_output(git + list(args), cwd=cwd, text=True).strip()


def _init(path):
    path.mkdir(parents=True)
    _git(path, "init", "-q", "--initial-branch=main")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "commit.gpgsign", "false")


def _commit(path, name):
    (path / name).write_text(name)
    _git(path, "add", name)
    _git(path, "commit", "-q", "-m", name)
    return _git(path, "rev-parse", "HEAD")


@pytest.fixture
def upstream(tmp_path):
    """Bare remote with two commits on main; returns (url, old_sha, head_sha)."""
    work = tmp_path / "upstream_work"
    _init(work)
    old = _commit(work, "one")
    head = _commit(work, "two")
    bare = tmp_path / "upstream.git"
    subprocess.check_call(git + ["clone", "-q", "--bare", str(work), str(bare)])
    return str(bare), old, head


class _Project:
    """The project path plus a helper that writes and commits gimera.yml."""

    def __init__(self, path, write):
        self.path = path
        self.write = write

    def __truediv__(self, other):
        return self.path / other


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path / "project"
    _init(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIMERA_EXCEPTION_THAN_SYSEXIT", "1")
    monkeypatch.setenv("GIMERA_NON_INTERACTIVE", "1")

    def write(repos):
        (repo / "gimera.yml").write_text(yaml.dump({"repos": repos}))
        _git(repo, "add", "gimera.yml")
        _git(repo, "commit", "-q", "-m", "gimera")

    return _Project(repo, write)


def _entry(path, url, sha, **kw):
    res = {"url": url, "branch": "main", "path": path, "type": "integrated", "sha": sha}
    res.update(kw)
    return res


def _run(*args):
    return CliRunner().invoke(cli, ["outdated"] + list(args))


def _line(output, path):
    return next(x for x in output.splitlines() if f" {path} " in x)


def test_current_pin_exits_zero(project, upstream):
    url, old, head = upstream
    project.write([_entry("vendor/a", url, head)])
    result = _run()
    assert result.exit_code == 0, result.output
    line = _line(result.output, "vendor/a")
    assert "current" in line
    assert head[:12] in line


def test_outdated_pin_exits_nonzero(project, upstream):
    url, old, head = upstream
    project.write([_entry("vendor/a", url, old), _entry("vendor/b", url, head)])
    result = _run()
    assert result.exit_code == 1, result.output
    line = _line(result.output, "vendor/a")
    assert "outdated" in line
    assert old[:12] in line and head[:12] in line
    assert "current" in _line(result.output, "vendor/b")


def test_unreachable_remote_is_unknown_not_traceback(project, tmp_path, upstream):
    url, old, head = upstream
    project.write([_entry("vendor/x", str(tmp_path / "does-not-exist.git"), old)])
    result = _run()
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 2, result.output
    line = _line(result.output, "vendor/x")
    assert "unknown (" in line
    assert "Traceback" not in result.output


def test_missing_branch_is_unknown_with_reason(project, upstream):
    url, old, head = upstream
    project.write([_entry("vendor/a", url, old, branch="nope")])
    result = _run()
    assert result.exit_code == 2, result.output
    assert "branch 'nope' not found on remote" in _line(result.output, "vendor/a")


def test_frozen_and_disabled_are_not_outdated(project, tmp_path, upstream):
    url, old, head = upstream
    project.write(
        [
            _entry("vendor/frozen", url, old, freeze_sha=True),
            _entry("vendor/off", str(tmp_path / "gone.git"), old, enabled=False),
            _entry("vendor/frozen_gone", str(tmp_path / "gone.git"), old, freeze_sha=True),
        ]
    )
    result = _run()
    assert result.exit_code == 0, result.output
    assert "frozen (freeze_sha)" in _line(result.output, "vendor/frozen")
    assert "disabled" in _line(result.output, "vendor/off")
    assert "frozen" in _line(result.output, "vendor/frozen_gone")


def test_outdated_wins_over_unknown(project, tmp_path, upstream):
    url, old, head = upstream
    project.write(
        [
            _entry("vendor/a", url, old),
            _entry("vendor/x", str(tmp_path / "gone.git"), old),
        ]
    )
    assert _run().exit_code == 1


def test_restrict_to_repos(project, upstream):
    url, old, head = upstream
    project.write([_entry("vendor/a", url, old), _entry("vendor/b", url, head)])
    result = _run("vendor/b/")
    assert result.exit_code == 0, result.output
    assert "vendor/a" not in result.output


def test_unknown_repo_argument_is_rejected(project, upstream):
    url, old, head = upstream
    project.write([_entry("vendor/a", url, head)])
    result = _run("vendor/zzz")
    assert result.exit_code != 0
    assert "vendor/zzz" in str(result.exception) + result.output


def test_submodule_without_sha_uses_gitlink(project, upstream):
    url, old, head = upstream
    _git(project.path, "-c", "protocol.file.allow=always", "submodule", "add", "-q", url, "vendor/s")
    _git(project / "vendor/s", "checkout", "-q", old)
    _git(project.path, "add", "vendor/s")
    project.write([_entry("vendor/s", url, None, type="submodule")])
    result = _run()
    assert result.exit_code == 1, result.output
    assert old[:12] in _line(result.output, "vendor/s")


def test_command_is_read_only(project, upstream):
    url, old, head = upstream
    project.write([_entry("vendor/a", url, old)])
    before = (project / "gimera.yml").read_bytes()
    _run()
    assert (project / "gimera.yml").read_bytes() == before
    assert _git(project.path, "status", "--porcelain") == ""
    assert not (project / "vendor").exists()
