"""Namespace-safe pom.xml parsing into plain dicts (no network, no Maven).

Only the facts needed for analysis are kept. Keys with no value are dropped so
the stored YAML stays small.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET

DEFAULT_PLUGIN_GROUP = "org.apache.maven.plugins"


class PomParseError(Exception):
    pass


def _local(tag: object) -> str:
    if not isinstance(tag, str):  # comments / processing instructions
        return ""
    return tag.rsplit("}", 1)[-1]


def _child(el: Element | None, name: str) -> Element | None:
    if el is None:
        return None
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _children(el: Element | None, name: str) -> list[Element]:
    if el is None:
        return []
    return [c for c in el if _local(c.tag) == name]


def _text(el: Element | None, name: str) -> str | None:
    c = _child(el, name)
    if c is None or c.text is None:
        return None
    t = c.text.strip()
    return t or None


def _compact(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _dep(el: Element) -> dict:
    return _compact(
        {
            "groupId": _text(el, "groupId"),
            "artifactId": _text(el, "artifactId"),
            "version": _text(el, "version"),
            "scope": _text(el, "scope"),
            "type": _text(el, "type"),
        }
    )


def _plugin(el: Element) -> dict:
    return _compact(
        {
            "groupId": _text(el, "groupId") or DEFAULT_PLUGIN_GROUP,
            "artifactId": _text(el, "artifactId"),
            "version": _text(el, "version"),
        }
    )


def parse_pom(content: bytes | str, path: str) -> dict:
    """Parse pom content. Raises PomParseError on empty or invalid XML."""
    if isinstance(content, bytes):
        if not content.strip():
            raise PomParseError("empty file")
    elif not content.strip():
        raise PomParseError("empty file")
    try:
        root = SafeET.fromstring(content)
    except Exception as exc:  # ParseError, defusedxml forbidden constructs, ...
        raise PomParseError(f"{exc.__class__.__name__}: {exc}") from exc
    if _local(root.tag) != "project":
        raise PomParseError(f"root element is <{_local(root.tag)}>, not <project>")

    parent_el = _child(root, "parent")
    parent = None
    if parent_el is not None:
        parent = _compact(
            {
                "groupId": _text(parent_el, "groupId"),
                "artifactId": _text(parent_el, "artifactId"),
                "version": _text(parent_el, "version"),
            }
        )
        rel = _child(parent_el, "relativePath")
        if rel is not None:
            # An explicit empty <relativePath/> means "do not look on disk".
            parent["relativePath"] = (rel.text or "").strip()

    props: dict[str, str] = {}
    props_el = _child(root, "properties")
    for p in list(props_el) if props_el is not None else []:
        name = _local(p.tag)
        if name:
            props[name] = (p.text or "").strip()

    dm = _child(_child(root, "dependencyManagement"), "dependencies")
    deps = _child(root, "dependencies")
    build = _child(root, "build")
    plugins = _child(build, "plugins")
    pm = _child(_child(build, "pluginManagement"), "plugins")
    scm = _child(root, "scm")

    urls = [
        u
        for u in (
            _text(root, "url"),
            _text(scm, "url"),
            _text(scm, "connection"),
            _text(scm, "developerConnection"),
        )
        if u
    ]

    facts = {
        "path": path,
        "groupId": _text(root, "groupId") or (parent or {}).get("groupId"),
        "artifactId": _text(root, "artifactId"),
        "version": _text(root, "version") or (parent or {}).get("version"),
        "packaging": _text(root, "packaging") or "jar",
        "parent": parent,
        "properties": props,
        "dependencyManagement": [_dep(d) for d in _children(dm, "dependency")],
        "dependencies": [_dep(d) for d in _children(deps, "dependency")],
        "plugins": [_plugin(p) for p in _children(plugins, "plugin")],
        "pluginManagement": [_plugin(p) for p in _children(pm, "plugin")],
        "modules": [
            (m.text or "").strip()
            for m in _children(_child(root, "modules"), "module")
            if (m.text or "").strip()
        ],
        "urls": urls,
    }
    if not facts["artifactId"]:
        raise PomParseError("missing <artifactId>")
    return _compact(facts)


def is_pom_path(path: str) -> bool:
    return path == "pom.xml" or path.endswith("/pom.xml")
