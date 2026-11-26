"""Test helpers: a tiny pom builder, an in-memory state builder and a fake GitLab client."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cartograf.gitlab_client import NotFound  # noqa: E402
from cartograf.pom_parser import PomParseError, parse_pom  # noqa: E402

NS = 'xmlns="http://maven.apache.org/POM/4.0.0"'


def _coord(spec: str, tag: str) -> str:
    parts = spec.split(":")
    names = ["groupId", "artifactId", "version", "scope", "type"]
    inner = "".join(f"<{n}>{v}</{n}>" for n, v in zip(names, parts) if v)
    return f"<{tag}>{inner}</{tag}>"


def pom(
    a: str,
    g: str | None = None,
    v: str | None = None,
    parent: str | None = None,
    relative_path: str | None = None,
    props: dict | None = None,
    deps: tuple = (),
    dm: tuple = (),
    plugins: tuple = (),
    plugin_mgmt: tuple = (),
    modules: tuple = (),
    packaging: str | None = None,
    extra: str = "",
) -> str:
    """Build pom XML. Coordinates are 'group:artifact[:version[:scope[:type]]]'."""
    out = [f"<project {NS}>", "<modelVersion>4.0.0</modelVersion>"]
    if parent:
        pg, pa, pv = (parent.split(":") + [None, None])[:3]
        rp = "" if relative_path is None else f"<relativePath>{relative_path}</relativePath>"
        out.append(f"<parent><groupId>{pg}</groupId><artifactId>{pa}</artifactId>"
                   f"<version>{pv}</version>{rp}</parent>")
    if g:
        out.append(f"<groupId>{g}</groupId>")
    out.append(f"<artifactId>{a}</artifactId>")
    if v:
        out.append(f"<version>{v}</version>")
    if packaging:
        out.append(f"<packaging>{packaging}</packaging>")
    if modules:
        out.append("<modules>" + "".join(f"<module>{m}</module>" for m in modules) + "</modules>")
    if props:
        out.append("<properties>" + "".join(f"<{k}>{val}</{k}>" for k, val in props.items()) + "</properties>")
    if dm:
        out.append("<dependencyManagement><dependencies>"
                   + "".join(_coord(d, "dependency") for d in dm)
                   + "</dependencies></dependencyManagement>")
    if deps:
        out.append("<dependencies>" + "".join(_coord(d, "dependency") for d in deps) + "</dependencies>")
    if plugins or plugin_mgmt:
        out.append("<build>")
        if plugin_mgmt:
            out.append("<pluginManagement><plugins>"
                       + "".join(_coord(p, "plugin") for p in plugin_mgmt)
                       + "</plugins></pluginManagement>")
        if plugins:
            out.append("<plugins>" + "".join(_coord(p, "plugin") for p in plugins) + "</plugins>")
        out.append("</build>")
    out.append(extra)
    out.append("</project>")
    return "\n".join(out)


def make_state(repos: dict, suffix: str = "-framework", pid_start: int = 100) -> dict:
    """repos: {path: {branch: {pom_path: xml}}}; first branch listed is the default.

    A branch mapped to None is a non-Maven checkout.
    """
    out = {}
    for i, (path, branches) in enumerate(repos.items()):
        entry = {"project_id": pid_start + i, "name": path.rsplit("/", 1)[-1], "status": "active",
                 "branches": {}}
        for j, (bname, files) in enumerate(branches.items()):
            poms = []
            for p, xml in sorted((files or {}).items()):
                try:
                    poms.append(parse_pom(xml, p))
                except PomParseError as exc:
                    poms.append({"path": p, "error": str(exc)})
            entry["branches"][bname] = {"sha": f"sha-{path}-{bname}", "default": j == 0,
                                        "maven": bool(files), "poms": poms}
        out[path] = entry
    return {"meta": {"suffix": suffix}, "repos": out}


class FakeGitLab:
    """In-memory stand-in for GitLabClient. Records the calls that matter for incrementality."""

    def __init__(self):
        self.groups: dict[str, list[dict]] = {}
        self.branch_data: dict[int, list[dict]] = {}
        self.files: dict[tuple[int, str], dict[str, str]] = {}  # (pid, sha) -> {path: content}
        self.tag_data: dict[int, list[str]] = {}
        self.calls: list[tuple] = []
        self.request_count = 0

    def add_project(self, group: str, pid: int, path: str, branches: dict, default: str = "main",
                    tags: list[str] | None = None):
        """branches: {name: (sha, committed_date, {path: content})}"""
        self.groups.setdefault(group, []).append({
            "id": pid, "path_with_namespace": path, "name": path.rsplit("/", 1)[-1],
            "default_branch": default, "web_url": f"https://gitlab.test/{path}",
        })
        self.set_branches(pid, branches)
        if tags is not None:
            self.tag_data[pid] = tags

    def set_branches(self, pid: int, branches: dict):
        self.branch_data[pid] = [
            {"name": n, "commit": {"id": sha, "committed_date": date}} for n, (sha, date, _) in branches.items()
        ]
        for n, (sha, _, files) in branches.items():
            self.files[(pid, sha)] = files

    def current_user(self):
        return {"username": "tester"}

    def group_projects(self, g):
        if g not in self.groups:
            raise NotFound(f"group {g}", 404)
        return iter(self.groups[g])

    def branches(self, pid):
        return self.branch_data.get(pid, [])

    def tree(self, pid, ref):
        self.calls.append(("tree", pid, ref))
        return iter([{"type": "blob", "path": p} for p in self.files.get((pid, ref), {})]
                    + [{"type": "tree", "path": "src"}])

    def raw_file(self, pid, path, ref):
        self.calls.append(("raw", pid, path, ref))
        try:
            return self.files[(pid, ref)][path].encode()
        except KeyError:
            raise NotFound(path, 404) from None

    def tags(self, pid, limit=100):
        return [{"name": t} for t in self.tag_data.get(pid, [])]


@pytest.fixture
def fake_gitlab():
    return FakeGitLab()
