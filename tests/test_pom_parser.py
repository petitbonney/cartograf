import pytest

from cartograf.pom_parser import PomParseError, is_pom_path, parse_pom
from conftest import pom


def test_namespace_and_basic_fields():
    f = parse_pom(pom("app", g="com.acme", v="1.0", packaging="war"), "pom.xml")
    assert f["groupId"] == "com.acme"
    assert f["artifactId"] == "app"
    assert f["version"] == "1.0"
    assert f["packaging"] == "war"
    assert f["path"] == "pom.xml"


def test_no_namespace_also_works():
    xml = "<project><groupId>g</groupId><artifactId>a</artifactId><version>2</version></project>"
    f = parse_pom(xml, "pom.xml")
    assert (f["groupId"], f["artifactId"], f["version"]) == ("g", "a", "2")


def test_inherits_group_and_version_from_parent():
    f = parse_pom(pom("child", parent="com.acme:parent:3.2.1"), "m/pom.xml")
    assert f["groupId"] == "com.acme"
    assert f["version"] == "3.2.1"
    assert f["parent"] == {"groupId": "com.acme", "artifactId": "parent", "version": "3.2.1"}


def test_relative_path_empty_is_kept():
    f = parse_pom(pom("child", parent="g:p:1", relative_path=""), "pom.xml")
    assert f["parent"]["relativePath"] == ""


def test_properties_dependencies_bom_plugins():
    xml = pom(
        "app", g="g", v="1",
        props={"fw.version": "3.10", "empty": ""},
        dm=("com.fw:fw-bom:${fw.version}:import:pom", "org.x:lib:2.0"),
        deps=("com.fw:fw-core", "junit:junit:4.13:test"),
        plugins=(":maven-compiler-plugin:3.11", "com.fw:fw-maven-plugin:${fw.version}"),
        plugin_mgmt=("org.y:y-plugin:1.0",),
        modules=("core", "web"),
    )
    f = parse_pom(xml, "pom.xml")
    assert f["properties"] == {"fw.version": "3.10", "empty": ""}
    assert f["dependencyManagement"][0] == {
        "groupId": "com.fw", "artifactId": "fw-bom", "version": "${fw.version}", "scope": "import", "type": "pom"
    }
    assert f["dependencies"][0] == {"groupId": "com.fw", "artifactId": "fw-core"}
    assert f["dependencies"][1]["scope"] == "test"
    # plugin groupId defaults to org.apache.maven.plugins
    assert f["plugins"][0] == {"groupId": "org.apache.maven.plugins", "artifactId": "maven-compiler-plugin",
                               "version": "3.11"}
    assert f["pluginManagement"] == [{"groupId": "org.y", "artifactId": "y-plugin", "version": "1.0"}]
    assert f["modules"] == ["core", "web"]


def test_scm_urls_collected():
    xml = pom("app", g="g", v="1", extra="<url>https://x/acme-framework</url>"
              "<scm><connection>scm:git:git@x:grp/acme-framework.git</connection></scm>")
    f = parse_pom(xml, "pom.xml")
    assert "https://x/acme-framework" in f["urls"]
    assert "scm:git:git@x:grp/acme-framework.git" in f["urls"]


@pytest.mark.parametrize("content,msg", [
    (b"", "empty"),
    (b"   \n", "empty"),
    (b"<project><artifactId>a</artifactId>", "ParseError"),
    (b"<settings/>", "not <project>"),
    (b"<project><groupId>g</groupId></project>", "artifactId"),
])
def test_bad_poms(content, msg):
    with pytest.raises(PomParseError, match=msg):
        parse_pom(content, "pom.xml")


def test_entity_expansion_is_refused():
    evil = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<project><artifactId>&lol2;</artifactId></project>"""
    with pytest.raises(PomParseError):
        parse_pom(evil, "pom.xml")


def test_is_pom_path():
    assert is_pom_path("pom.xml")
    assert is_pom_path("a/b/pom.xml")
    assert not is_pom_path("a/b/my-pom.xml")
    assert not is_pom_path("pom.xml.bak")
