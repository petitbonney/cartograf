import pytest

from cartograf.analyze import analyze
from conftest import make_state, pom

FW_PARENT = "com.acme.fw:acme-parent"


@pytest.fixture(scope="module")
def result():
    state = make_state({
        "grp/acme-framework": {"main": {
            "pom.xml": pom("acme-parent", g="com.acme.fw", v="3.5.0", packaging="pom",
                           modules=("core", "bom", "plugin"),
                           props={"acme.version": "3.5.0"},
                           dm=("com.acme.fw:acme-core:${acme.version}",),
                           plugin_mgmt=("com.acme.fw:acme-maven-plugin:${acme.version}",)),
            "core/pom.xml": pom("acme-core", parent=f"{FW_PARENT}:3.5.0"),
            "bom/pom.xml": pom("acme-bom", parent=f"{FW_PARENT}:3.5.0", packaging="pom",
                               dm=("com.acme.fw:acme-core:${project.version}",)),
            "plugin/pom.xml": pom("acme-maven-plugin", parent=f"{FW_PARENT}:3.5.0"),
        }},
        "grp/tools-framework": {"main": {
            "pom.xml": pom("tools", g="com.acme.tools", v="2.0.0", deps=("com.acme.fw:acme-core:3.5.0",)),
        }},
        "grp/corp-parent": {"main": {
            "pom.xml": pom("corp-parent", g="com.acme", v="1.0", packaging="pom", parent=f"{FW_PARENT}:3.5.0"),
        }},
        "grp/svc-corp-child": {"main": {
            "pom.xml": pom("svc", g="com.acme.svc", v="0.1.0", parent="com.acme:corp-parent:1.0",
                           deps=("com.acme.fw:acme-core",)),
        }},
        "grp/svc-old-parent": {"main": {
            "pom.xml": pom("old", g="com.acme.old", v="1", parent=f"{FW_PARENT}:3.4.0",
                           deps=("com.acme.fw:acme-core",)),
        }},
        "grp/svc-bom-user": {"main": {
            "pom.xml": pom("bomuser", g="com.acme.b", v="1",
                           parent="org.springframework.boot:spring-boot-starter-parent:3.2.0",
                           props={"fw.version": "3.5.0"},
                           dm=("com.acme.fw:acme-bom:${fw.version}:import:pom",),
                           deps=("com.acme.fw:acme-core",)),
        }},
        "grp/svc-modules": {"main": {
            "pom.xml": pom("svc-root", g="com.acme.m", v="${revision}", packaging="pom",
                           props={"revision": "1.2.0"}, parent=f"{FW_PARENT}:3.5.0", modules=("app",)),
            "app/pom.xml": pom("app", parent="com.acme.m:svc-root:${revision}", deps=("com.acme.fw:acme-core",)),
        }},
        "grp/svc-branchy": {
            "main": {"pom.xml": pom("br", g="b", v="1", deps=("com.acme.fw:acme-core:3.4.0",))},
            "feature/x": {"pom.xml": pom("br", g="b", v="1", deps=("com.acme.fw:acme-core:3.5.0",))},
        },
        "grp/svc-ranges": {"main": {
            "pom.xml": pom("r", g="r", v="1", deps=("com.acme.fw:acme-core:[3.0,4.0)",),
                           plugins=("com.acme.fw:acme-maven-plugin:3.6.0-SNAPSHOT",)),
        }},
        "grp/svc-unresolved": {"main": {
            "pom.xml": pom("u", g="u", v="1", deps=("com.acme.fw:acme-core:${undefined.prop}",)),
        }},
        "grp/svc-weak": {"main": {
            "pom.xml": pom("w", g="w", v="1", deps=("com.other:legacy-framework-utils:1.0",)),
        }},
        "grp/adhoc-app": {"main": {"pom.xml": pom("thing", g="org.other", v="1", deps=("junit:junit:4.13",))}},
        "grp/docs-site": {"main": None},
        "grp/svc-broken": {"main": {"pom.xml": ""}},
    })
    state["repos"]["grp/acme-framework"]["latest_tag"] = "3.5.0"
    return analyze(state)


def links(result, repo, branch="main"):
    return result["repos"][repo]["branches"][branch]["framework_links"]


def review(result, type_, **match):
    return [r for r in result["review"] if r["type"] == type_ and all(r.get(k) == v for k, v in match.items())]


def test_kinds(result):
    kinds = {p: r["kind"] for p, r in result["repos"].items()}
    assert kinds["grp/acme-framework"] == "framework"
    assert kinds["grp/tools-framework"] == "framework"
    assert kinds["grp/corp-parent"] == "linked"
    assert kinds["grp/svc-corp-child"] == "linked"
    assert kinds["grp/adhoc-app"] == "adhoc"
    assert kinds["grp/svc-weak"] == "adhoc"
    assert kinds["grp/docs-site"] == "non-maven"
    assert result["meta"]["counts"]["frameworks"] == 2
    assert result["meta"]["counts"]["non_maven"] == 1


def test_framework_section(result):
    fw = result["frameworks"]["grp/acme-framework"]
    assert fw["artifacts"] == [
        "com.acme.fw:acme-bom", "com.acme.fw:acme-core", "com.acme.fw:acme-maven-plugin", "com.acme.fw:acme-parent",
    ]
    assert fw["branches"]["main"]["version"] == "3.5.0"
    assert fw["latest"] == "3.5.0"
    assert "grp/svc-corp-child" in fw["used_by"]
    assert "grp/tools-framework" in fw["used_by"]
    assert result["frameworks"]["grp/tools-framework"]["links_to"] == ["grp/acme-framework"]


def test_framework_does_not_link_to_itself(result):
    assert links(result, "grp/acme-framework") == []


def test_direct_parent_link(result):
    [lk] = [lk for lk in links(result, "grp/corp-parent") if lk["type"] == "parent"]
    assert lk["artifact"] == FW_PARENT
    assert lk["resolved"] == "3.5.0" and lk["status"] == "resolved" and lk["behind"] is False


def test_inherited_link_and_managed_dependency_through_corp_parent(result):
    ls = links(result, "grp/svc-corp-child")
    inherited = [lk for lk in ls if lk["type"] == "inherited"]
    assert len(inherited) == 1
    assert inherited[0]["inherited_type"] == "parent"
    assert inherited[0]["via"].startswith("com.acme:corp-parent:1.0")
    assert inherited[0]["resolved"] == "3.5.0"
    [dep] = [lk for lk in ls if lk["type"] == "dependency"]
    assert dep["status"] == "managed" and dep["resolved"] == "3.5.0"
    assert dep["managed_by"] == f"{FW_PARENT}:3.5.0"


def test_old_parent_version_is_known_but_managed_dep_is_not_guessed(result):
    ls = links(result, "grp/svc-old-parent")
    [par] = [lk for lk in ls if lk["type"] == "parent"]
    assert par["resolved"] == "3.4.0" and par["behind"] is True
    [dep] = [lk for lk in ls if lk["type"] == "dependency"]
    assert dep["resolved"] is None and dep["status"] == "unresolved"
    assert "parent_version_not_in_crawl" in dep["reason"]
    gap = review(result, "parent_version_not_in_crawl", parent=f"{FW_PARENT}:3.4.0")
    assert gap and gap[0]["available"] == ["3.5.0"]


def test_bom_link_and_bom_managed_dependency(result):
    ls = links(result, "grp/svc-bom-user")
    [bom] = [lk for lk in ls if lk["type"] == "bom"]
    assert bom["declared"] == "${fw.version}" and bom["resolved"] == "3.5.0"
    [dep] = [lk for lk in ls if lk["type"] == "dependency"]
    assert dep["status"] == "managed" and dep["resolved"] == "3.5.0"


def test_unresolved_external_parent_grouped_in_review(result):
    [item] = review(result, "unresolved_parent", parent="org.springframework.boot:spring-boot-starter-parent")
    assert item["versions"] == ["3.2.0"]
    assert item["poms"] == ["grp/svc-bom-user@main:pom.xml"]


def test_multimodule_revision_no_duplicate_inherited(result):
    ls = links(result, "grp/svc-modules")
    assert {(lk["pom"], lk["type"]) for lk in ls} == {("pom.xml", "parent"), ("app/pom.xml", "dependency")}
    [dep] = [lk for lk in ls if lk["type"] == "dependency"]
    assert dep["resolved"] == "3.5.0" and dep["status"] == "managed"


def test_branch_disagreement(result):
    [item] = review(result, "branch_disagreement", repo="grp/svc-branchy")
    assert item["versions"] == {"feature/x": ["3.5.0"], "main": ["3.4.0"]}
    assert result["repos"]["grp/svc-branchy"]["uses"]["grp/acme-framework"]["main"] == ["3.4.0"]


def test_range_snapshot_unresolved(result):
    ls = links(result, "grp/svc-ranges")
    assert {lk["status"] for lk in ls} == {"range", "snapshot"}
    assert review(result, "range_version", repo="grp/svc-ranges")
    assert review(result, "snapshot_version", repo="grp/svc-ranges")
    [u] = links(result, "grp/svc-unresolved")
    assert u["resolved"] is None and "undefined.prop" in u["reason"]
    assert review(result, "unresolved_version", repo="grp/svc-unresolved")


def test_weak_signal_and_pom_error(result):
    [w] = review(result, "weak_signal", repo="grp/svc-weak")
    assert w["detail"] == ["dependency com.other:legacy-framework-utils"]
    assert review(result, "pom_error", repo="grp/svc-broken")


def test_analysis_is_idempotent(result):
    import copy
    import json
    again = analyze(copy.deepcopy(result))
    assert json.dumps(again, sort_keys=True) == json.dumps(result, sort_keys=True)
