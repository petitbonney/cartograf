"""Load/save the state file (YAML or JSON), deterministically.

YAML pitfall: unquoted `3.10` is a float, `1.0` too, `no`/`on` are booleans in
YAML 1.1. Every string that is not an obviously safe identifier is written
double-quoted, so versions always round-trip as strings.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

_SAFE_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_./@+-]*$")
_YAML_SPECIAL = {
    "y", "n", "yes", "no", "on", "off", "true", "false", "null", "nan", "inf", "~",
}


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:  # never emit &id001 anchors
        return True


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    if "\n" not in data and (not _SAFE_PLAIN.match(data) or data.lower() in _YAML_SPECIAL):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _represent_str)


def plain(obj: Any) -> Any:
    """Normalize to plain dict/list/scalars (sets become sorted lists)."""
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(plain(v) for v in obj)
    return obj


def dumps(data: dict, fmt: str = "yaml") -> str:
    data = plain(data)
    if fmt == "json":
        return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    return yaml.dump(
        data,
        Dumper=_Dumper,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
        width=4096,
    )


def loads(text: str, fmt: str = "yaml") -> dict:
    data = json.loads(text) if fmt == "json" else yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("state file does not contain a mapping")
    return data


def format_for(path: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return "json" if path.suffix.lower() == ".json" else "yaml"


def load(path: Path, fmt: str | None = None) -> dict | None:
    if not path.exists():
        return None
    return loads(path.read_text(encoding="utf-8"), format_for(path, fmt))


def save(path: Path, data: dict, fmt: str | None = None) -> None:
    text = dumps(data, format_for(path, fmt))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
