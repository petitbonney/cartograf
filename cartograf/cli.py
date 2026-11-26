"""CLI glue: arguments, env, run crawl + analysis, write the state file, print a summary."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from . import FACTS_VERSION, store
from .analyze import analyze
from .crawl import (
    DEFAULT_EXCLUDE_BRANCHES,
    DEFAULT_EXCLUDE_POM_PATHS,
    CrawlConfig,
    crawl,
)
from .gitlab_client import AuthError, GitLabClient, GitLabError

log = logging.getLogger("cartograf")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="cartography.py",
        description="Map Maven framework usage across GitLab repositories.",
    )
    ap.add_argument("--suffix", help="repo-name suffix that marks a framework (e.g. -framework)")
    ap.add_argument("--groups", help="comma-separated GitLab group IDs or full paths")
    ap.add_argument("--groups-file", type=Path, help="file with one group per line (# comments ok)")
    ap.add_argument("--url", help="GitLab base URL (default: $GITLAB_URL)")
    ap.add_argument("--output", type=Path, help="state/output file (default: cartography.yaml|.json)")
    ap.add_argument("--format", choices=("yaml", "json"), help="output format (default: from extension)")
    ap.add_argument("--branch-window-days", type=int, help="age window for the most recent branch (default 90)")
    ap.add_argument("--exclude-branch", action="append", metavar="PATTERN", default=[],
                    help="extra branch glob to ignore (repeatable); defaults: " + ", ".join(DEFAULT_EXCLUDE_BRANCHES))
    ap.add_argument("--exclude-pom-path", action="append", metavar="PATTERN", default=[],
                    help="extra pom path glob to ignore (repeatable); defaults skip src/test, src/it, target")
    ap.add_argument("--workers", type=int, default=8, help="concurrent API requests (default 8)")
    ap.add_argument("--full", action="store_true", help="ignore stored SHAs and re-fetch everything")
    ap.add_argument("--analyze-only", action="store_true", help="no network: re-run analysis on stored facts")
    ap.add_argument("--dry-run", action="store_true", help="inventory + branch selection only; print what would be fetched")
    ap.add_argument("--no-tags", action="store_true", help="do not fetch framework tags for the latest version")
    ap.add_argument("--verbose", "-v", action="store_true")
    return ap


def read_groups(args: argparse.Namespace, meta: dict) -> list[str]:
    groups: list[str] = []
    if args.groups:
        groups += [g.strip() for g in args.groups.split(",") if g.strip()]
    if args.groups_file:
        for line in args.groups_file.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                groups.append(line)
    if not groups:
        groups = list(meta.get("groups") or [])
    return list(dict.fromkeys(groups))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    fmt = args.format
    output: Path = args.output or Path("cartography.json" if fmt == "json" else "cartography.yaml")
    in_fmt = store.format_for(output)  # the existing file is read in the format its name implies
    try:
        state = store.load(output, in_fmt) or {}
    except Exception as exc:
        log.error("cannot read %s: %s", output, exc)
        return 2
    meta = state.setdefault("meta", {})

    suffix = args.suffix or meta.get("suffix")
    if not suffix:
        log.error("--suffix is required (no suffix stored in %s)", output)
        return 2
    meta["suffix"] = suffix
    now = datetime.now().astimezone()

    if args.analyze_only:
        if not state.get("repos"):
            log.error("--analyze-only needs an existing %s with stored facts", output)
            return 2
        meta["generated_at"] = now.isoformat(timespec="seconds")
        analyze(state)
        store.save(output, state, fmt)
        print_summary(state, None, output)
        return 0

    groups = read_groups(args, meta)
    if not groups:
        log.error("no groups given (--groups / --groups-file) and none stored in %s", output)
        return 2
    url = (args.url or os.environ.get("GITLAB_URL") or meta.get("gitlab_url") or "").rstrip("/")
    if not url:
        log.error("GitLab URL missing: pass --url or set GITLAB_URL")
        return 2
    token = os.environ.get("GITLAB_TOKEN", "")
    if not token:
        log.error("GITLAB_TOKEN is not set (personal access token with read_api scope)")
        return 2

    window = args.branch_window_days or meta.get("branch_window_days") or 90
    cfg = CrawlConfig(
        groups=groups,
        suffix=suffix,
        branch_window_days=window,
        exclude_branches=DEFAULT_EXCLUDE_BRANCHES + args.exclude_branch,
        exclude_pom_paths=DEFAULT_EXCLUDE_POM_PATHS + args.exclude_pom_path,
        workers=max(1, args.workers),
        full=args.full,
        fetch_tags=not args.no_tags,
    )
    client = GitLabClient(url, token, pool_size=cfg.workers)
    del token

    try:
        user = client.current_user()
        log.info("authenticated as %s on %s", user.get("username"), url)
        new_state, stats = crawl(client, state, cfg, now, dry_run=args.dry_run)
    except AuthError as exc:
        log.error("%s", exc)
        return 1
    except GitLabError as exc:
        log.error("GitLab error: %s", exc)
        return 1
    except KeyboardInterrupt:
        log.error("interrupted: %s left unchanged", output)
        return 130

    if stats.missing_groups:
        log.warning("groups not found or not accessible: %s", ", ".join(stats.missing_groups))

    if args.dry_run:
        for repo, branch, action in stats.plan:
            print(f"{action:6} {repo} @ {branch}")
        print(f"\n{stats.projects} projects, {stats.branches} branches selected: "
              f"{sum(1 for p in stats.plan if p[2] == 'fetch')} to fetch, {stats.reused} unchanged, "
              f"{stats.gone} gone. Nothing written.")
        return 0

    m = new_state.setdefault("meta", {})
    m.update(
        {
            "generated_at": now.isoformat(timespec="seconds"),
            "gitlab_url": url,
            "suffix": suffix,
            "groups": groups,
            "branch_window_days": window,
            "exclude_branches": cfg.exclude_branches,
            "exclude_pom_paths": cfg.exclude_pom_paths,
            "token_user": user.get("username"),
            "facts_version": FACTS_VERSION,
            "last_run": {
                "projects": stats.projects,
                "branches": stats.branches,
                "fetched": stats.fetched,
                "reused": stats.reused,
                "fetch_errors": stats.errors,
                "gone": stats.gone,
                "missing_groups": stats.missing_groups,
                "api_requests": client.request_count,
            },
        }
    )
    analyze(new_state)
    store.save(output, new_state, fmt)
    print_summary(new_state, stats, output)
    return 0


def print_summary(state: dict, stats, output: Path) -> None:
    meta = state["meta"]
    c = meta.get("counts", {})
    lines = [
        "",
        f"Wrote {output}",
        "Repos: {repos_seen} active ({frameworks} frameworks, {linked} linked, {adhoc} adhoc, "
        "{non_maven} non-maven), {gone} gone".format(**{k: c.get(k, 0) for k in (
            "repos_seen", "frameworks", "linked", "adhoc", "non_maven", "gone")}),
    ]
    if stats is not None:
        lines.append(f"Branches: {stats.branches} selected, {stats.fetched} fetched, "
                     f"{stats.reused} unchanged (skipped), {stats.errors} errors")
    rc = meta.get("review_counts") or {}
    if rc:
        lines.append("Review: " + ", ".join(f"{k}={v}" for k, v in rc.items()))
    else:
        lines.append("Review: nothing flagged")
    print("\n".join(lines))
