import pytest
import yaml

from cartograf import store

TRICKY = ["3.10", "1.0", "1", "no", "No", "yes", "on", "off", "y", "n", "true", "null", "~", "",
          "0o17", "1e3", "0x1F", "2026-11-25", "12:30", "3.2.1", "${fw.version}", "[1.0,2.0)",
          "- dash", "a: b", "#comment", "@at", "*star", "1.0-SNAPSHOT", ".inf", "NaN"]


@pytest.mark.parametrize("value", TRICKY)
def test_yaml_round_trip_keeps_strings(value):
    data = {"v": value, "list": [value], value: "key"}
    text = store.dumps(data)
    back = yaml.safe_load(text)
    assert back == data
    assert isinstance(back["v"], str)


@pytest.mark.parametrize("value", ["3.10", "1.0", "no", "on", "0o17", "1e3"])
def test_version_like_strings_are_double_quoted(value):
    assert f'v: "{value}"' in store.dumps({"v": value})


def test_deterministic_and_no_aliases():
    shared = {"x": 1}
    a = store.dumps({"b": [3, 1], "a": shared, "c": shared, "s": {"z", "a"}})
    b = store.dumps({"c": shared, "a": shared, "s": {"a", "z"}, "b": [3, 1]})
    assert a == b
    assert "&id" not in a and "*id" not in a
    assert yaml.safe_load(a)["s"] == ["a", "z"]


def test_ints_and_none_stay_native():
    back = yaml.safe_load(store.dumps({"project_id": 123, "resolved": None, "behind": True}))
    assert back == {"project_id": 123, "resolved": None, "behind": True}


def test_save_load_yaml_and_json(tmp_path):
    data = {"meta": {"suffix": "-framework"}, "repos": {"g/r": {"project_id": 1, "v": "3.10"}}}
    for name in ("state.yaml", "state.json"):
        p = tmp_path / name
        store.save(p, data)
        assert store.load(p) == data
    assert store.load(tmp_path / "missing.yaml") is None
    assert list(tmp_path.glob(".state*")) == []  # temp files cleaned up
