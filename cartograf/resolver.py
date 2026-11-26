"""Static Maven model resolution over the crawled poms (no network, no Maven).

- parent chain resolution against poms known in the crawl
- `${...}` property interpolation (own properties, then up the parent chain,
  plus project.* built-ins)
- dependencyManagement / BOM import / pluginManagement lookups

Rule: never guess. When something cannot be resolved from crawled data, the
result is None plus a reason.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field

PROP_RE = re.compile(r"\$\{([^}]+)\}")
MAX_DEPTH = 20


@dataclass(frozen=True)
class PomRef:
    project_id: int
    repo: str  # path_with_namespace, for display
    branch: str
    is_default: bool
    facts: dict = field(compare=False, hash=False)

    @property
    def path(self) -> str:
        return self.facts["path"]

    @property
    def key(self) -> tuple[int, str, str]:
        return (self.project_id, self.branch, self.path)

    @property
    def checkout(self) -> tuple[int, str]:
        return (self.project_id, self.branch)

    @property
    def ga(self) -> str:
        return ga(self.facts.get("groupId"), self.facts.get("artifactId"))

    def where(self) -> str:
        return f"{self.repo}@{self.branch}:{self.path}"


def ga(group: str | None, artifact: str | None) -> str:
    return f"{group or '?'}:{artifact or '?'}"


# -- versions -------------------------------------------------------------

_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)(.*)$")
_RELEASE_QUALIFIERS = {"", "final", "ga", "release", "releases"}


def is_range(v: str) -> bool:
    return v[:1] in "[(" or "," in v or v in ("LATEST", "RELEASE")


def is_snapshot(v: str) -> bool:
    return v.endswith("-SNAPSHOT") or v == "SNAPSHOT"


def version_status(resolved: str | None, managed: bool) -> str:
    if resolved is None:
        return "unresolved"
    if is_range(resolved):
        return "range"
    if is_snapshot(resolved):
        return "snapshot"
    return "managed" if managed else "resolved"


def parse_version(v: str) -> tuple[tuple[int, ...], str] | None:
    m = _NUM_RE.match(v.strip())
    if not m:
        return None
    nums = tuple(int(x) for x in m.group(1).split("."))
    qual = m.group(2).lstrip(".-_").lower()
    return nums, qual


def compare_versions(a: str, b: str) -> int | None:
    """Approximate Maven ordering for common `1.2.3[-qualifier]` versions.

    Returns -1/0/1, or None if either side is not comparable.
    A qualified version (`-SNAPSHOT`, `-RC1`, ...) sorts before its release.
    """
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        return None
    na, qa = pa
    nb, qb = pb
    width = max(len(na), len(nb))
    na = na + (0,) * (width - len(na))
    nb = nb + (0,) * (width - len(nb))
    if na != nb:
        return -1 if na < nb else 1
    ra, rb = qa in _RELEASE_QUALIFIERS, qb in _RELEASE_QUALIFIERS
    if ra and rb:
        return 0
    if ra != rb:
        return 1 if ra else -1
    if qa == qb:
        return 0
    return None  # two different pre-release qualifiers: don't pretend to know


_TAG_RE = re.compile(r"^(?:.*?[-_/])?[vV]?(\d+(?:\.\d+)+)$")


def version_from_tag(tag: str) -> str | None:
    """`v1.2.3`, `1.2.3`, `my-artifact-1.2.3`, `release/1.2.3` -> `1.2.3`. Releases only."""
    m = _TAG_RE.match(tag.strip())
    return m.group(1) if m else None


def latest_tag_version(tag_names: list[str]) -> str | None:
    best: str | None = None
    for name in tag_names:
        v = version_from_tag(name)
        if v and (best is None or compare_versions(v, best) == 1):
            best = v
    return best


# -- resolver -------------------------------------------------------------


class Resolver:
    def __init__(self, poms: list[PomRef]):
        self.poms = {p.key: p for p in poms}
        self.by_ga: dict[str, list[PomRef]] = defaultdict(list)
        self.by_checkout: dict[tuple[int, str], list[PomRef]] = defaultdict(list)
        for p in sorted(poms, key=_sort_key):
            self.by_ga[p.ga].append(p)
            self.by_checkout[p.checkout].append(p)
        self._parent_memo: dict = {}
        self._version_memo: dict = {}
        self._props_memo: dict = {}
        self._in_progress: set = set()

    # -- parent chain --

    def parent(self, pom: PomRef) -> tuple[PomRef | None, dict | None]:
        """Return (parent pom, problem). Both None when the pom has no <parent>."""
        if pom.key in self._parent_memo:
            return self._parent_memo[pom.key]
        guard = ("parent", pom.key)
        if guard in self._in_progress:
            return None, {"type": "parent_cycle", "pom": pom.where()}
        self._in_progress.add(guard)
        try:
            result = self._find_parent(pom)
        finally:
            self._in_progress.discard(guard)
        self._parent_memo[pom.key] = result
        return result

    def _find_parent(self, pom: PomRef) -> tuple[PomRef | None, dict | None]:
        par = pom.facts.get("parent")
        if not par:
            return None, None
        pga = ga(par.get("groupId"), par.get("artifactId"))
        declared = par.get("version")
        candidates = [c for c in self.by_ga.get(pga, []) if c.key != pom.key]

        # 1. Same checkout (multi-module reactor): trust coordinates, prefer relativePath.
        same = [c for c in candidates if c.checkout == pom.checkout]
        if same:
            expected = _expected_parent_path(pom.path, par.get("relativePath"))
            for c in same:
                if c.path == expected:
                    return c, None
            return same[0], None

        # 2. Other repos: exact version match only.
        version, _ = self.resolve(declared, pom, own_only=True)
        coords = f"{pga}:{version or declared or '?'}"
        if not candidates:
            return None, {"type": "unresolved_parent", "parent": pga, "version": version or declared}
        if version is None:
            return None, {
                "type": "parent_version_not_in_crawl",
                "parent": coords,
                "reason": "parent version expression cannot be resolved",
            }
        matches = [c for c in candidates if self.effective_version(c) == version]
        if matches:
            matches.sort(key=lambda c: (not c.is_default, _sort_key(c)))
            return matches[0], None
        available = sorted({v for c in candidates if (v := self.effective_version(c))})
        return None, {
            "type": "parent_version_not_in_crawl",
            "parent": coords,
            "available": available,
        }

    def chain(self, pom: PomRef) -> tuple[list[PomRef], dict | None]:
        """[pom, parent, grandparent, ...] and the problem that stopped the walk, if any."""
        out = [pom]
        seen = {pom.key}
        cur = pom
        while True:
            par, problem = self.parent(cur)
            if par is None:
                return out, problem
            if par.key in seen or len(out) > MAX_DEPTH:
                return out, {"type": "parent_cycle", "pom": pom.where()}
            out.append(par)
            seen.add(par.key)
            cur = par

    # -- properties --

    def properties(self, pom: PomRef) -> dict[str, str]:
        if pom.key in self._props_memo:
            return self._props_memo[pom.key]
        merged: dict[str, str] = {}
        for p in reversed(self.chain(pom)[0]):
            merged.update(p.facts.get("properties", {}))
        self._props_memo[pom.key] = merged
        return merged

    def _builtin(self, name: str, pom: PomRef) -> str | None:
        f = pom.facts
        par = f.get("parent") or {}
        if name.startswith("pom."):
            name = "project." + name[4:]
        table = {
            "project.version": f.get("version"),
            "project.groupId": f.get("groupId"),
            "project.artifactId": f.get("artifactId"),
            "project.packaging": f.get("packaging"),
            "project.parent.version": par.get("version"),
            "project.parent.groupId": par.get("groupId"),
            "project.parent.artifactId": par.get("artifactId"),
            # deprecated aliases still seen in the wild
            "version": f.get("version"),
            "groupId": f.get("groupId"),
            "artifactId": f.get("artifactId"),
            "parent.version": par.get("version"),
            "parent.groupId": par.get("groupId"),
        }
        return table.get(name)

    def _lookup(self, name: str, pom: PomRef, own_only: bool) -> str | None:
        if name.startswith(("project.", "pom.")):
            return self._builtin(name, pom)
        props = pom.facts.get("properties", {}) if own_only else self.properties(pom)
        if name in props:
            return props[name]
        if own_only:
            return None
        return self._builtin(name, pom)

    def resolve(
        self, expr: str | None, pom: PomRef, own_only: bool = False
    ) -> tuple[str | None, list[str]]:
        """Interpolate `expr` in the context of `pom`. Returns (value, missing property names)."""
        if expr is None:
            return None, []
        return self._interp(expr, pom, own_only, 0, ())

    def _interp(self, s, pom, own_only, depth, stack) -> tuple[str | None, list[str]]:
        missing: list[str] = []

        def repl(m: re.Match) -> str:
            name = m.group(1).strip()
            if name in stack or depth > MAX_DEPTH:
                missing.append(name)
                return m.group(0)
            raw = self._lookup(name, pom, own_only)
            if raw is None:
                missing.append(name)
                return m.group(0)
            val, miss = self._interp(raw, pom, own_only, depth + 1, stack + (name,))
            if miss:
                missing.extend(miss)
                return m.group(0)
            return val

        out = PROP_RE.sub(repl, s)
        if missing:
            return None, sorted(set(missing))
        return out, []

    def effective_version(self, pom: PomRef) -> str | None:
        if pom.key in self._version_memo:
            return self._version_memo[pom.key]
        guard = ("version", pom.key)
        if guard in self._in_progress:
            return None
        self._in_progress.add(guard)
        try:
            v, _ = self.resolve(pom.facts.get("version"), pom)
        finally:
            self._in_progress.discard(guard)
        self._version_memo[pom.key] = v
        return v

    def coords(self, pom: PomRef) -> str:
        return f"{pom.ga}:{self.effective_version(pom) or pom.facts.get('version') or '?'}"

    def find(self, coord_ga: str, version: str) -> PomRef | None:
        matches = [c for c in self.by_ga.get(coord_ga, []) if self.effective_version(c) == version]
        if not matches:
            return None
        matches.sort(key=lambda c: (not c.is_default, _sort_key(c)))
        return matches[0]

    # -- management lookups --

    def managed_dependency(self, pom: PomRef, group: str, artifact: str, _seen=None) -> dict:
        """Find the managed version of group:artifact for `pom`.

        Explicit dependencyManagement entries anywhere up the chain win over
        BOM imports (Maven semantics). Inherited entries are interpolated in the
        child's context; BOM entries in the BOM's own context.

        Returns {"found": True, "declared", "resolved", "missing", "managed_by"}
        or {"found": False, "reason"}.
        """
        seen = set(_seen or ()) | {pom.key}
        chain, chain_problem = self.chain(pom)
        for anc in chain:
            for d in anc.facts.get("dependencyManagement", []):
                if d.get("scope") == "import":
                    continue
                if d.get("groupId") == group and d.get("artifactId") == artifact:
                    declared = d.get("version")
                    val, miss = self.resolve(declared, pom)
                    return {
                        "found": True,
                        "declared": declared,
                        "resolved": val,
                        "missing": miss,
                        "managed_by": self.coords(anc),
                    }
        unavailable: list[str] = []
        for anc in chain:
            for d in anc.facts.get("dependencyManagement", []):
                if d.get("scope") != "import":
                    continue
                bga = ga(d.get("groupId"), d.get("artifactId"))
                bv, _ = self.resolve(d.get("version"), pom)
                if bv is None:
                    unavailable.append(f"{bga}:{d.get('version')} (version unresolved)")
                    continue
                bom = self.find(bga, bv)
                if bom is None:
                    unavailable.append(f"{bga}:{bv}")
                    continue
                if bom.key in seen:
                    continue
                r = self.managed_dependency(bom, group, artifact, seen)
                if r["found"]:
                    r["managed_by"] = f"{bga}:{bv} (bom)" + (
                        "" if r["managed_by"].startswith(f"{bga}:{bv}") else f" <- {r['managed_by']}"
                    )
                    return r
                unavailable.extend(r.get("unavailable", []))
        reason = "no dependencyManagement entry in the crawled parent chain or BOMs"
        if unavailable:
            reason += "; BOMs not available in the crawl: " + ", ".join(sorted(set(unavailable)))
        if chain_problem:
            reason += f"; parent chain stops at {_problem_str(chain_problem)}"
        return {"found": False, "reason": reason, "unavailable": sorted(set(unavailable))}

    def managed_plugin(self, pom: PomRef, group: str, artifact: str) -> dict:
        chain, chain_problem = self.chain(pom)
        for i, anc in enumerate(chain):
            sources = anc.facts.get("pluginManagement", [])
            if i > 0:
                sources = sources + anc.facts.get("plugins", [])
            for p in sources:
                if p.get("groupId") == group and p.get("artifactId") == artifact and p.get("version"):
                    declared = p["version"]
                    val, miss = self.resolve(declared, pom)
                    return {
                        "found": True,
                        "declared": declared,
                        "resolved": val,
                        "missing": miss,
                        "managed_by": self.coords(anc),
                    }
        reason = "no plugin version in the crawled parent chain"
        if chain_problem:
            reason += f"; parent chain stops at {_problem_str(chain_problem)}"
        return {"found": False, "reason": reason}


def _problem_str(problem: dict) -> str:
    target = problem.get("parent") or problem.get("pom") or "?"
    if problem.get("version") and problem.get("type") == "unresolved_parent":
        target += f":{problem['version']}"
    return f"{target} ({problem['type']})"


def _expected_parent_path(pom_path: str, relative: str | None) -> str | None:
    if relative == "":
        return None
    rel = relative if relative is not None else "../pom.xml"
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(pom_path), rel))
    if not joined.endswith(".xml"):
        joined = posixpath.join(joined, "pom.xml")
    return joined


def _sort_key(p: PomRef):
    return (p.repo, p.branch, p.path)
