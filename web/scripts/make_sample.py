"""Generate web/public/sample.yaml: a fictional cartography output for the web UI demo.

Runs the real CLI (crawl + analysis) against an in-memory fake GitLab, twice, so
the output also has a "gone" repo. All names are made up.

    python web/scripts/make_sample.py        (from the repository root, with requirements.txt and requirements-dev.txt installed)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cartograf import cli  # noqa: E402
from cartograf.gitlab_client import GitLabError  # noqa: E402
from conftest import FakeGitLab, pom  # noqa: E402

NOW = datetime(2026, 11, 20, 9, 30, tzinfo=timezone(timedelta(hours=1)))
OUT = ROOT / "web" / "public" / "sample.yaml"
GROUPS = "platform,payments,web,data,archive"


def ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat(timespec="seconds")


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


class SampleGitLab(FakeGitLab):
    url = "https://gitlab.example.com"

    def __init__(self):
        super().__init__()
        self.broken: set[int] = set()  # project ids whose tree listing fails

    def add_project(self, group, pid, path, branches, default="main", tags=None):
        super().add_project(group, pid, path, branches, default, tags)
        self.groups[group][-1]["web_url"] = f"{self.url}/{path}"

    def tree(self, pid, ref):
        if pid in self.broken:
            raise GitLabError("500 Internal Server Error on repository/tree", 500)
        return super().tree(pid, ref)

    def current_user(self):
        return {"username": "demo-reader"}


# -- frameworks -------------------------------------------------------------------

def acme(v: str) -> dict:
    parent = f"com.acme.platform:acme-parent:{v}"
    managed = ("com.acme.platform:acme-core:${acme.version}",
               "com.acme.platform:acme-web:${acme.version}")
    return {
        "pom.xml": pom("acme-parent", g="com.acme.platform", v=v, packaging="pom",
                       modules=("acme-bom", "acme-core", "acme-web"), props={"acme.version": v}, dm=managed),
        "acme-bom/pom.xml": pom("acme-bom", parent=parent, packaging="pom", dm=managed),
        "acme-core/pom.xml": pom("acme-core", parent=parent),
        "acme-web/pom.xml": pom("acme-web", parent=parent, deps=("com.acme.platform:acme-core",)),
    }


def messaging(v: str, acme_v: str) -> dict:
    return {"pom.xml": pom("messaging-starter", g="com.acme.messaging", v=v,
                           parent=f"com.acme.platform:acme-parent:{acme_v}",
                           deps=("com.acme.platform:acme-core",))}


def app(a: str, g: str = "com.acme.apps", v: str = "1.0.0", **kw) -> dict:
    return {"pom.xml": pom(a, g=g, v=v, **kw)}


SPRING = "org.springframework.boot:spring-boot-starter-parent:3.3.5"
CORP = "com.acme:corp-parent:12"
ACME_PARENT = "com.acme.platform:acme-parent"


def seed(gl: SampleGitLab, first_run: bool) -> None:
    pid = iter(range(1001, 2000))

    def add(group, path, branches, pid_=None, **kw):
        gl.add_project(group, pid_ or next(pid), path, branches, **kw)

    # frameworks
    add("platform", "platform/acme-framework", {
        "main": ("a1f3c9e", ago(6), acme("3.5.0")),
        "develop": ("a7d02b4", ago(1), acme("3.6.0-SNAPSHOT")),
    }, tags=["v3.3.0", "v3.4.0", "v3.5.0"])
    add("platform", "platform/messaging-framework", {
        "main": ("m42be10", ago(12), messaging("2.2.1", "3.5.0")),
    }, tags=["v2.1.0", "v2.2.0", "v2.2.1"])
    add("platform", "platform/build-framework", {
        "main": ("b9c1d77", ago(40), app("acme-maven-plugin", g="com.acme.build", v="1.8.0",
                                         packaging="maven-plugin")),
    }, tags=["v1.7.0", "v1.8.0"])
    add("data", "data/etl-framework", {
        "main": ("e0a4f21", ago(3), app("etl-core", g="com.acme.data", v="0.9.3")),
    }, tags=[])

    # a shared corporate parent (not a framework) that pulls frameworks in for its children
    add("platform", "platform/corp-parent", {
        "main": ("c12aa00", ago(150), app("corp-parent", g="com.acme", v="12", packaging="pom",
                                          dm=("com.acme.platform:acme-bom:3.4.0:import:pom",),
                                          plugin_mgmt=("com.acme.build:acme-maven-plugin:1.7.0",))),
    })
    add("platform", "platform/docs-site", {"main": ("d0c5000", ago(20), {"mkdocs.yml": "site"})})

    # payments
    add("payments", "payments/payment-api", {
        "main": ("p1a0001", ago(2), app("payment-api", parent=f"{ACME_PARENT}:3.5.0",
                                        deps=("com.acme.platform:acme-core", "com.acme.platform:acme-web"))),
        "feature/sca-v2": ("p1a0002", ago(9), app("payment-api", parent=f"{ACME_PARENT}:3.4.0",
                                                   deps=("com.acme.platform:acme-core",))),
    })
    add("payments", "payments/ledger", {
        "main": ("l3d6e01", ago(30), app("ledger", parent=f"{ACME_PARENT}:3.4.0",
                                         deps=("com.acme.platform:acme-core",))),
    })
    add("payments", "payments/invoicing", {
        "main": ("i7v0c01", ago(5), app("invoicing", parent=f"{ACME_PARENT}:3.5.0",
                                        deps=("com.acme.platform:acme-core",))),
    })
    add("payments", "payments/refunds", {
        "main": ("r3f0d01", ago(8), app("refunds", parent=SPRING,
                                        props={"messaging.version": "2.2.0"},
                                        dm=("com.acme.platform:acme-bom:3.5.0:import:pom",),
                                        deps=("com.acme.platform:acme-core",
                                              "com.acme.messaging:messaging-starter:${messaging.version}"))),
    })
    add("payments", "payments/notifications", {
        "main": ("n0t1f01", ago(15), app("notifications", parent=f"{ACME_PARENT}:3.5.0",
                                         deps=("com.acme.messaging:messaging-starter:2.2.1",))),
        "develop": ("n0t1f02", ago(4), app("notifications", parent=f"{ACME_PARENT}:3.5.0",
                                           deps=("com.acme.messaging:messaging-starter:2.1.0",))),
    })
    add("payments", "payments/fraud-scoring", {
        "main": ("f4a0d01", ago(22), app("fraud-scoring",
                                         deps=("com.acme.platform:acme-core:${acme.version}",))),
    })
    if first_run:
        add("payments", "payments/old-gateway", {
            "main": ("o1d0001", ago(400), app("old-gateway", parent=f"{ACME_PARENT}:3.3.0")),
        }, pid_=1999)  # fixed id so the other repos keep theirs on the second run

    # web
    add("web", "web/storefront", {
        "main": ("s7f0001", ago(1), {
            "pom.xml": pom("storefront", g="com.acme.web", v="4.2.0", parent=CORP, packaging="pom",
                           modules=("storefront-ui",)),
            "storefront-ui/pom.xml": pom("storefront-ui", parent="com.acme.web:storefront:4.2.0",
                                         deps=("com.acme.platform:acme-web",)),
        }),
    })
    add("web", "web/checkout", {
        "main": ("c4e0001", ago(11), app("checkout", g="com.acme.web", parent=CORP,
                                         deps=("com.acme.platform:acme-web:[3.0,4.0)",))),
    })
    add("web", "web/search", {
        "main": ("s3a0001", ago(60), app("search", g="com.acme.web", parent=f"{ACME_PARENT}:3.3.0")),
    })
    add("web", "web/gateway", {
        "main": ("g4t0001", ago(14), app("gateway", g="com.acme.web", parent=SPRING)),
    })
    add("web", "web/media-service", {
        # new commit on the second run, whose fetch fails
        "main": ("m3d0001" if first_run else "m3d0002", ago(2), app("media-service", g="com.acme.web", parent=f"{ACME_PARENT}:3.5.0")),
    })
    add("web", "web/cms", {"main": ("c0m5001", ago(3), {"package.json": "{}"})})
    add("web", "web/landing", {"main": ("l4n0001", ago(70), {"index.html": "<html/>"})})

    # data
    add("data", "data/ingest", {
        "main": ("i9e0001", ago(4), app("ingest", g="com.acme.data", deps=("com.acme.data:etl-core:0.9.3",),
                                        plugins=("com.acme.build:acme-maven-plugin:1.8.0",))),
    })
    add("data", "data/warehouse-sync", {
        "main": ("w4h0001", ago(19), app("warehouse-sync", g="com.acme.data",
                                         deps=("com.acme.data:etl-core:0.9.1",))),
    })
    add("data", "data/reporting", {
        "main": ("r9p0001", ago(6), app("reporting", g="com.acme.data",
                                        deps=("com.acme.data:etl-core:1.0.0-SNAPSHOT",))),
    })
    add("data", "data/legacy-batch", {
        "main": ("l9b0001", ago(300), app("legacy-batch", g="com.acme.data",
                                          deps=("com.acme.legacy:old-framework-utils:1.0",
                                                "org.apache.commons:commons-lang3:3.14.0"))),
    })
    add("data", "data/broken-pom", {
        "main": ("b0k0001", ago(27), {"pom.xml": "<project><artifactId>oops</artifactId>"}),
    })
    add("data", "data/notebooks", {"main": ("n8b0001", ago(10), {"requirements.txt": "pandas"})})

    if not first_run:  # second run: one fetch fails (it was fine on the first run, so it shows as an error)
        gl.broken.update(g["id"] for g in gl.groups["web"] if g["path_with_namespace"] == "web/media-service")


def run(first_run: bool) -> None:
    gl = SampleGitLab()
    seed(gl, first_run)
    cli.GitLabClient = lambda url, token, pool_size=8: gl
    cli.datetime = FixedDatetime
    os.environ["GITLAB_TOKEN"] = "fake"
    rc = cli.main(["--suffix=-framework", "--groups", GROUPS, "--url", gl.url, "--output", str(OUT)])
    if rc != 0:
        raise SystemExit(rc)


if __name__ == "__main__":
    OUT.unlink(missing_ok=True)
    run(first_run=True)
    run(first_run=False)
