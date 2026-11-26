from datetime import datetime, timezone

import pytest

from cartograf import FACTS_VERSION
from cartograf.analyze import analyze
from cartograf.crawl import CrawlConfig, crawl, select_branches
from conftest import pom

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
RECENT = "2026-11-20T10:00:00.000+01:00"
OLD = "2026-01-01T10:00:00Z"


def b(name, date):
    return {"name": name, "commit": {"id": f"sha-{name}", "committed_date": date}}


def test_select_branches_default_plus_most_recent():
    branches = [b("main", OLD), b("develop", "2026-11-01T00:00:00Z"), b("feature/new", RECENT),
                b("renovate/foo", "2026-11-25T00:00:00Z"), b("dependabot/npm/x", "2026-11-25T00:00:00Z")]
    picked = select_branches(branches, "main", 90, ["dependabot/*", "renovate/*", "renovate-*"], NOW)
    assert [(p["name"], p["default"]) for p in picked] == [("main", True), ("feature/new", False)]


def test_select_branches_window_excludes_old():
    picked = select_branches([b("main", OLD), b("old-feature", OLD)], "main", 90, [], NOW)
    assert [p["name"] for p in picked] == ["main"]


def test_select_branches_empty():
    assert select_branches([], "main", 90, [], NOW) == []


def cfg(**kw):
    return CrawlConfig(groups=["grp"], suffix="-framework", workers=2, **kw)


def seed(fake):
    fake.add_project("grp", 1, "grp/acme-framework",
                     {"main": ("f1", RECENT, {"pom.xml": pom("acme-parent", g="fw", v="3.5.0", packaging="pom")})},
                     tags=["v3.4.0", "v3.5.0"])
    fake.add_project("grp", 2, "grp/svc", {
        "main": ("s1", RECENT, {"pom.xml": pom("svc", g="s", v="1", parent="fw:acme-parent:3.5.0"),
                                "src/test/resources/pom.xml": pom("fixture", g="t", v="1"),
                                "README.md": "hi"}),
    })
    fake.add_project("grp", 3, "grp/docs", {"main": ("d1", RECENT, {"README.md": "docs"})})
    fake.add_project("grp", 4, "grp/empty", {})


def run(fake, state, **kw):
    new, stats = crawl(fake, state, cfg(**kw), NOW)
    new.setdefault("meta", {}).update({"suffix": "-framework", "facts_version": FACTS_VERSION})
    return analyze(new), stats


def test_first_run_then_incremental_skip(fake_gitlab):
    seed(fake_gitlab)
    state, stats = run(fake_gitlab, {})
    assert stats.fetched == 3 and stats.reused == 0
    repos = state["repos"]
    assert repos["grp/svc"]["kind"] == "linked"
    assert [p["path"] for p in repos["grp/svc"]["branches"]["main"]["poms"]] == ["pom.xml"]  # test fixture skipped
    assert repos["grp/docs"]["kind"] == "non-maven"
    assert repos["grp/docs"]["branches"]["main"]["maven"] is False
    assert repos["grp/empty"]["kind"] == "non-maven" and repos["grp/empty"]["empty_repo"] is True
    assert repos["grp/acme-framework"]["latest_tag"] == "3.5.0"

    # Second run, nothing changed: no tree / raw calls at all (non-maven included).
    fake_gitlab.calls.clear()
    state2, stats2 = run(fake_gitlab, state)
    assert stats2.fetched == 0 and stats2.reused == 3
    assert fake_gitlab.calls == []
    assert state2["repos"]["grp/svc"]["branches"] == state["repos"]["grp/svc"]["branches"]

    # One repo gets a new commit: only that one is fetched.
    fake_gitlab.set_branches(2, {
        "main": ("s2", RECENT, {"pom.xml": pom("svc", g="s", v="2", deps=("fw:acme-parent:3.4.0",))}),
    })
    fake_gitlab.calls.clear()
    state3, stats3 = run(fake_gitlab, state2)
    assert stats3.fetched == 1 and stats3.reused == 2
    assert {c[1] for c in fake_gitlab.calls} == {2}
    [lk] = state3["repos"]["grp/svc"]["branches"]["main"]["framework_links"]
    assert lk["resolved"] == "3.4.0" and lk["behind"] is True

    # --full ignores stored SHAs.
    _, stats4 = run(fake_gitlab, state3, full=True)
    assert stats4.fetched == 3


def test_gone_repos_are_kept_and_marked(fake_gitlab):
    seed(fake_gitlab)
    state, _ = run(fake_gitlab, {})
    fake_gitlab.groups["grp"] = [p for p in fake_gitlab.groups["grp"] if p["id"] != 2]
    state2, stats = run(fake_gitlab, state)
    gone = state2["repos"]["grp/svc"]
    assert gone["status"] == "gone" and gone["kind"] == "gone" and "gone_since" in gone
    assert stats.gone == 1
    assert state2["meta"]["counts"]["gone"] == 1


def test_renamed_repo_keyed_by_project_id(fake_gitlab):
    seed(fake_gitlab)
    state, _ = run(fake_gitlab, {})
    for p in fake_gitlab.groups["grp"]:
        if p["id"] == 2:
            p["path_with_namespace"] = "grp/svc-renamed"
    fake_gitlab.calls.clear()
    state2, stats = run(fake_gitlab, state)
    assert "grp/svc" not in state2["repos"]
    assert state2["repos"]["grp/svc-renamed"]["kind"] == "linked"
    assert stats.fetched == 0  # same project ID, same SHA: reused


def test_fetch_error_is_recorded_and_retried(fake_gitlab):
    from cartograf.gitlab_client import GitLabError
    seed(fake_gitlab)
    orig = fake_gitlab.tree

    def broken(pid, ref):
        if pid == 2:
            raise GitLabError("HTTP 500", 500)
        return orig(pid, ref)

    fake_gitlab.tree = broken
    state, stats = run(fake_gitlab, {})
    assert stats.errors == 1
    assert "fetch_error" in state["repos"]["grp/svc"]["branches"]["main"]
    assert any(r["type"] == "fetch_error" for r in state["review"])
    fake_gitlab.tree = orig
    state2, stats2 = run(fake_gitlab, state)
    assert stats2.fetched == 1
    assert "fetch_error" not in state2["repos"]["grp/svc"]["branches"]["main"]


def test_missing_group_listed(fake_gitlab):
    seed(fake_gitlab)
    new, stats = crawl(fake_gitlab, {}, CrawlConfig(groups=["grp", "nope"], suffix="-framework"), NOW)
    assert stats.missing_groups == ["nope"]


def test_all_groups_missing_fails(fake_gitlab):
    from cartograf.gitlab_client import AuthError
    with pytest.raises(AuthError):
        crawl(fake_gitlab, {}, CrawlConfig(groups=["nope"], suffix="-framework"), NOW)


def test_dry_run_fetches_nothing(fake_gitlab):
    seed(fake_gitlab)
    _, stats = crawl(fake_gitlab, {}, cfg(), NOW, dry_run=True)
    assert fake_gitlab.calls == []
    assert sorted(a for _, _, a in stats.plan) == ["fetch", "fetch", "fetch"]
