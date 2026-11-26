import pytest

from cartograf.pom_parser import parse_pom
from cartograf.resolver import (
    PomRef,
    Resolver,
    compare_versions,
    latest_tag_version,
    version_from_tag,
    version_status,
)
from conftest import pom


def ref(repo, path, xml, branch="main", pid=None, default=True):
    return PomRef(pid or abs(hash(repo)) % 10000, repo, branch, default, parse_pom(xml, path))


def test_property_resolution_own_then_parent_chain():
    parent = ref("g/parent", "pom.xml", pom("parent", g="g", v="1", props={"a": "A", "b": "B-${a}"}))
    child = ref("g/child", "pom.xml", pom("child", parent="g:parent:1", props={"a": "override"}))
    r = Resolver([parent, child])
    assert r.parent(child) == (parent, None)
    assert r.resolve("${b}", child) == ("B-override", [])  # child property wins, interpolated in child context
    assert r.resolve("${b}", parent) == ("B-A", [])
    assert r.resolve("${project.version}", child) == ("1", [])
    assert r.resolve("${project.parent.version}", child) == ("1", [])
    assert r.resolve("${project.groupId}", child) == ("g", [])


def test_missing_and_cyclic_properties_are_unresolved():
    p = ref("g/a", "pom.xml", pom("a", g="g", v="1", props={"x": "${y}", "y": "${x}"}))
    r = Resolver([p])
    assert r.resolve("${nope}", p) == (None, ["nope"])
    v, missing = r.resolve("${x}", p)
    assert v is None and missing


def test_ci_friendly_revision_in_multimodule():
    root = ref("g/svc", "pom.xml", pom("svc-root", g="g", v="${revision}", props={"revision": "1.2.0"},
                                       packaging="pom", modules=("app",)))
    mod = ref("g/svc", "app/pom.xml", pom("app", parent="g:svc-root:${revision}"))
    mod = PomRef(root.project_id, "g/svc", "main", True, mod.facts)
    r = Resolver([root, mod])
    assert r.parent(mod)[0] is root
    assert r.effective_version(mod) == "1.2.0"
    assert r.effective_version(root) == "1.2.0"


def test_cross_repo_parent_requires_exact_version():
    fw = ref("g/x-framework", "pom.xml", pom("fw-parent", g="fw", v="3.5.0", packaging="pom"))
    old = ref("g/old", "pom.xml", pom("old", g="o", v="1", parent="fw:fw-parent:3.4.0"))
    ext = ref("g/ext", "pom.xml", pom("ext", g="o", v="1", parent="org.springframework.boot:spring-boot-starter-parent:3.2.0"))
    r = Resolver([fw, old, ext])
    par, problem = r.parent(old)
    assert par is None
    assert problem == {"type": "parent_version_not_in_crawl", "parent": "fw:fw-parent:3.4.0", "available": ["3.5.0"]}
    par, problem = r.parent(ext)
    assert par is None
    assert problem["type"] == "unresolved_parent"
    assert problem["parent"] == "org.springframework.boot:spring-boot-starter-parent"


def test_managed_dependency_via_parent_and_bom():
    parent = ref("g/fw", "pom.xml", pom("fw-parent", g="fw", v="3.5.0", packaging="pom",
                                        props={"fw.version": "3.5.0"}, dm=("fw:fw-core:${fw.version}",)))
    bom = ref("g/fw", "bom/pom.xml", pom("fw-bom", g="fw", v="3.5.0", packaging="pom",
                                         dm=("fw:fw-core:${project.version}",)))
    via_parent = ref("g/a", "pom.xml", pom("a", g="a", v="0.1", parent="fw:fw-parent:3.5.0"))
    via_bom = ref("g/b", "pom.xml", pom("b", g="b", v="0.1", props={"v": "3.5.0"},
                                        dm=("fw:fw-bom:${v}:import:pom",)))
    r = Resolver([parent, bom, via_parent, via_bom])

    m = r.managed_dependency(via_parent, "fw", "fw-core")
    assert m["found"] and m["resolved"] == "3.5.0" and m["managed_by"] == "fw:fw-parent:3.5.0"

    m = r.managed_dependency(via_bom, "fw", "fw-core")
    # ${project.version} in a BOM is interpolated in the BOM's own context
    assert m["found"] and m["resolved"] == "3.5.0" and "fw:fw-bom:3.5.0 (bom)" in m["managed_by"]

    m = r.managed_dependency(via_bom, "fw", "other")
    assert not m["found"]


def test_managed_dependency_unavailable_bom_reason():
    p = ref("g/b", "pom.xml", pom("b", g="b", v="1", dm=("ext:ext-bom:9:import:pom",)))
    m = Resolver([p]).managed_dependency(p, "ext", "lib")
    assert not m["found"]
    assert "ext:ext-bom:9" in m["reason"]


def test_explicit_management_beats_bom_import():
    bom = ref("g/fw", "pom.xml", pom("fw-bom", g="fw", v="2", packaging="pom", dm=("fw:core:2",)))
    p = ref("g/b", "pom.xml", pom("b", g="b", v="1", dm=("fw:fw-bom:2:import:pom", "fw:core:1.9")))
    m = Resolver([bom, p]).managed_dependency(p, "fw", "core")
    assert m["resolved"] == "1.9"


def test_managed_plugin_from_parent():
    parent = ref("g/p", "pom.xml", pom("p", g="p", v="1", plugin_mgmt=("fw:fw-plugin:4.0",)))
    child = ref("g/c", "pom.xml", pom("c", parent="p:p:1", plugins=("fw:fw-plugin",)))
    m = Resolver([parent, child]).managed_plugin(child, "fw", "fw-plugin")
    assert m["found"] and m["resolved"] == "4.0"


@pytest.mark.parametrize("resolved,managed,expected", [
    (None, False, "unresolved"),
    ("[1.0,2.0)", False, "range"),
    ("LATEST", False, "range"),
    ("1.0-SNAPSHOT", True, "snapshot"),
    ("1.0", True, "managed"),
    ("1.0", False, "resolved"),
])
def test_version_status(resolved, managed, expected):
    assert version_status(resolved, managed) == expected


@pytest.mark.parametrize("a,b,expected", [
    ("3.4.0", "3.5.0", -1),
    ("3.10", "3.9", 1),
    ("3.5", "3.5.0", 0),
    ("3.5.0-SNAPSHOT", "3.5.0", -1),
    ("3.5.0.RELEASE", "3.5.0", 0),
    ("3.5.0-RC1", "3.5.0-RC2", None),
    ("abc", "1.0", None),
])
def test_compare_versions(a, b, expected):
    assert compare_versions(a, b) == expected


def test_tags():
    assert version_from_tag("v1.2.3") == "1.2.3"
    assert version_from_tag("acme-parent-1.2.3") == "1.2.3"
    assert version_from_tag("release/2.0") == "2.0"
    assert version_from_tag("1.2.3-rc1") is None
    assert latest_tag_version(["v3.9.0", "v3.10.0", "nightly", "v3.10.0-rc1"]) == "3.10.0"
