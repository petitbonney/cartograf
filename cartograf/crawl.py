"""Pass 0 (inventory + branch selection) and incremental fetch of pom facts."""

from __future__ import annotations

import fnmatch
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import FACTS_VERSION
from .analyze import is_framework
from .gitlab_client import AuthError, GitLabClient, GitLabError, NotFound
from .pom_parser import PomParseError, is_pom_path, parse_pom
from .resolver import latest_tag_version

log = logging.getLogger(__name__)

DEFAULT_EXCLUDE_BRANCHES = ["dependabot/*", "renovate/*", "renovate-*"]
# Test fixtures and build output, not real modules.
DEFAULT_EXCLUDE_POM_PATHS = [
    "src/test/*", "*/src/test/*",
    "src/it/*", "*/src/it/*",
    "target/*", "*/target/*",
    "node_modules/*", "*/node_modules/*",
]


@dataclass
class CrawlConfig:
    groups: list[str]
    suffix: str
    branch_window_days: int = 90
    exclude_branches: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_BRANCHES))
    exclude_pom_paths: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_POM_PATHS))
    workers: int = 8
    full: bool = False
    fetch_tags: bool = True


@dataclass
class CrawlStats:
    projects: int = 0
    branches: int = 0
    fetched: int = 0
    reused: int = 0
    errors: int = 0
    gone: int = 0
    missing_groups: list[str] = field(default_factory=list)
    plan: list[tuple[str, str, str]] = field(default_factory=list)  # (repo, branch, action)


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def select_branches(
    branches: list[dict],
    default_branch: str | None,
    window_days: int,
    exclude: list[str],
    now: datetime,
) -> list[dict]:
    """Default branch + the most recently committed other branch (in window, not excluded)."""
    picked: list[dict] = []
    by_name = {b["name"]: b for b in branches}
    if default_branch in by_name:
        picked.append(_branch_info(by_name[default_branch], True))
    elif branches:
        log.warning("default branch %r not found among branches", default_branch)

    cutoff = now - timedelta(days=window_days)
    best, best_ts = None, None
    for b in branches:
        if b["name"] == default_branch:
            continue
        if any(fnmatch.fnmatchcase(b["name"], pat) for pat in exclude):
            continue
        ts = parse_ts((b.get("commit") or {}).get("committed_date"))
        if ts is None or ts < cutoff:
            continue
        if best_ts is None or ts > best_ts or (ts == best_ts and b["name"] < best["name"]):
            best, best_ts = b, ts
    if best is not None:
        picked.append(_branch_info(best, False))
    return picked


def _branch_info(b: dict, is_default: bool) -> dict:
    c = b.get("commit") or {}
    return {
        "name": b["name"],
        "sha": c.get("id"),
        "committed_at": c.get("committed_date"),
        "default": is_default,
    }


def _excluded_path(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def fetch_branch(client: GitLabClient, project_id: int, sha: str, exclude_paths: list[str]) -> dict:
    """List pom.xml files at `sha` and parse each one. Returns {maven, poms}."""
    paths = sorted(
        item["path"]
        for item in client.tree(project_id, sha)
        if item.get("type") == "blob"
        and is_pom_path(item["path"])
        and not _excluded_path(item["path"], exclude_paths)
    )
    if not paths:
        return {"maven": False, "poms": []}
    poms = []
    for p in paths:
        try:
            facts = parse_pom(client.raw_file(project_id, p, sha), p)
        except PomParseError as exc:
            facts = {"path": p, "error": str(exc)}
        except NotFound:
            facts = {"path": p, "error": "file not found at this commit"}
        poms.append(facts)
    return {"maven": True, "poms": poms}


_FACT_KEYS = ("sha", "committed_at", "default", "maven", "poms", "facts_sha", "fetch_error")


def _facts_only(branch: dict) -> dict:
    """A stored branch without the fields the analysis derives (kind, framework_links)."""
    return {k: branch[k] for k in _FACT_KEYS if k in branch}


def inventory(client: GitLabClient, groups: list[str]) -> tuple[dict[int, dict], list[str]]:
    projects: dict[int, dict] = {}
    missing: list[str] = []
    for g in groups:
        try:
            n = 0
            for p in client.group_projects(g):
                projects.setdefault(p["id"], p)
                n += 1
            log.info("group %s: %d projects", g, n)
        except NotFound:
            missing.append(g)
            log.warning("group %s: not found or not accessible (404)", g)
        except GitLabError as exc:
            if exc.status == 403:
                missing.append(g)
                log.warning("group %s: access denied (403)", g)
            else:
                raise
    return projects, missing


def crawl(
    client: GitLabClient,
    state: dict,
    cfg: CrawlConfig,
    now: datetime,
    dry_run: bool = False,
) -> tuple[dict, CrawlStats]:
    """Return a new state with fresh inventory and pom facts (derived fields untouched)."""
    stats = CrawlStats()
    old_repos: dict = state.get("repos") or {}
    old_by_id = {r["project_id"]: r for r in old_repos.values() if "project_id" in r}
    full = cfg.full or (state.get("meta") or {}).get("facts_version") != FACTS_VERSION

    projects, stats.missing_groups = inventory(client, cfg.groups)
    if cfg.groups and len(stats.missing_groups) == len(cfg.groups):
        raise AuthError("none of the groups is accessible: " + ", ".join(stats.missing_groups))
    stats.projects = len(projects)

    # -- branches (+ tags for frameworks), in parallel
    def list_branches(p: dict):
        try:
            return p["id"], client.branches(p["id"]), None
        except (NotFound, GitLabError) as exc:
            if isinstance(exc, AuthError):
                raise
            return p["id"], [], f"cannot list branches: {exc}"

    def list_tags(p: dict):
        try:
            return p["id"], latest_tag_version([t["name"] for t in client.tags(p["id"])])
        except (NotFound, GitLabError) as exc:
            if isinstance(exc, AuthError):
                raise
            log.warning("tags of %s: %s", p["path_with_namespace"], exc)
            return p["id"], None

    branch_lists: dict[int, tuple[list, str | None]] = {}
    tags: dict[int, str | None] = {}
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futs = [pool.submit(list_branches, p) for p in projects.values()]
        if cfg.fetch_tags:
            futs += [
                pool.submit(list_tags, p)
                for p in projects.values()
                if is_framework(p["path_with_namespace"], p, cfg.suffix)
            ]
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            if len(res) == 3:
                branch_lists[res[0]] = (res[1], res[2])
            else:
                tags[res[0]] = res[1]
            if i % 50 == 0:
                log.info("inventory: %d/%d", i, len(futs))

    # -- build new repo entries, decide fetch vs reuse
    new_repos: dict[str, dict] = {}
    jobs: list[tuple[str, dict, dict]] = []  # (repo path, project, branch info)
    for pid, p in sorted(projects.items(), key=lambda kv: kv[1]["path_with_namespace"]):
        path = p["path_with_namespace"]
        old = old_by_id.get(pid) or {}
        entry = {
            "project_id": pid,
            "name": p.get("name"),
            "web_url": p.get("web_url"),
            "default_branch": p.get("default_branch"),
            "status": "active",
            "branches": {},
        }
        if pid in tags:
            entry["latest_tag"] = tags[pid]
        elif old.get("latest_tag"):
            entry["latest_tag"] = old["latest_tag"]
        blist, err = branch_lists.get(pid, ([], None))
        old_branches = old.get("branches") or {}
        if err:
            # Branches unknown this run: keep last run's branches and facts rather than
            # losing the repo's framework links over one failed API call.
            entry["inventory_error"] = err
            entry["branches"] = {name: _facts_only(b) for name, b in sorted(old_branches.items())}
        if not blist and not err:
            entry["empty_repo"] = True
        selected = select_branches(
            blist, p.get("default_branch"), cfg.branch_window_days, cfg.exclude_branches, now
        )
        for b in selected:
            stats.branches += 1
            prev = old_branches.get(b["name"])
            entry["branches"][b["name"]] = {
                "sha": b["sha"],
                "committed_at": b["committed_at"],
                "default": b["default"],
            }
            if (
                not full
                and prev
                and prev.get("sha") == b["sha"]
                and not prev.get("fetch_error")
                and "maven" in prev
            ):
                entry["branches"][b["name"]]["maven"] = prev["maven"]
                entry["branches"][b["name"]]["poms"] = prev.get("poms") or []
                stats.reused += 1
                stats.plan.append((path, b["name"], "reuse"))
            else:
                jobs.append((path, p, b))
                stats.plan.append((path, b["name"], "fetch"))
        new_repos[path] = entry

    # -- repos that disappeared: keep, mark gone
    seen_ids = set(projects)
    for opath, o in sorted(old_repos.items()):
        if o.get("project_id") in seen_ids:
            continue
        g = dict(o)
        g["status"] = "gone"
        g.setdefault("gone_since", now.isoformat(timespec="seconds"))
        key = opath if opath not in new_repos else f"{opath} (gone #{o.get('project_id')})"
        new_repos[key] = g
        stats.gone += 1

    if dry_run:
        return {**state, "repos": new_repos}, stats

    # -- fetch changed branches
    def run(job):
        path, p, b = job
        try:
            return job, fetch_branch(client, p["id"], b["sha"], cfg.exclude_pom_paths), None
        except AuthError:
            raise
        except GitLabError as exc:
            return job, None, str(exc)

    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futs = [pool.submit(run, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            (path, p, b), result, err = fut.result()
            target = new_repos[path]["branches"][b["name"]]
            if err:
                target["fetch_error"] = err
                stats.errors += 1
                log.warning("%s@%s: %s", path, b["name"], err)
                # Keep the facts of the last commit that was read, if any, so the repo
                # keeps its framework links until the next run retries the fetch.
                prev = ((old_by_id.get(p["id"]) or {}).get("branches") or {}).get(b["name"])
                if prev and "maven" in prev:
                    target["maven"] = prev["maven"]
                    target["poms"] = prev.get("poms") or []
                    target["facts_sha"] = prev.get("facts_sha") or prev.get("sha")
            else:
                target.update(result)
                stats.fetched += 1
            if i % 25 == 0 or i == len(futs):
                log.info("fetch: %d/%d", i, len(futs))

    for r in new_repos.values():
        for b in (r.get("branches") or {}).values():
            if b.get("poms"):
                b["poms"] = sorted(b["poms"], key=lambda f: f["path"])

    new_state = dict(state)
    new_state["repos"] = new_repos
    return new_state, stats

