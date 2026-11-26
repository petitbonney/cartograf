import yaml

from cartograf import cli, store
from conftest import make_state, pom


def test_missing_token_fails_clearly(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    rc = cli.main(["--suffix=-framework", "--groups", "g", "--url", "https://gitlab.test",
                   "--output", str(tmp_path / "out.yaml")])
    assert rc == 2
    assert "GITLAB_TOKEN" in caplog.text
    assert not (tmp_path / "out.yaml").exists()


def test_analyze_only_from_stored_facts(tmp_path, capsys):
    state = make_state({
        "grp/x-framework": {"main": {"pom.xml": pom("x", g="x", v="3.10")}},
        "grp/app": {"main": {"pom.xml": pom("app", g="a", v="1", deps=("x:x:3.10",))}},
    })
    out = tmp_path / "cartography.yaml"
    store.save(out, state)
    assert cli.main(["--analyze-only", "--output", str(out)]) == 0
    text = out.read_text()
    data = yaml.safe_load(text)
    [lk] = data["repos"]["grp/app"]["branches"]["main"]["framework_links"]
    assert lk["resolved"] == "3.10" and isinstance(lk["resolved"], str)
    assert 'resolved: "3.10"' in text
    assert "linked" in capsys.readouterr().out


def test_analyze_only_json(tmp_path):
    state = make_state({"grp/x-framework": {"main": {"pom.xml": pom("x", g="x", v="1.0")}}})
    out = tmp_path / "c.json"
    store.save(out, state)
    assert cli.main(["--analyze-only", "--output", str(out)]) == 0
    assert store.load(out)["frameworks"]["grp/x-framework"]["latest"] == "1.0"


def test_analyze_only_needs_state(tmp_path):
    assert cli.main(["--analyze-only", "--suffix=-f", "--output", str(tmp_path / "none.yaml")]) == 2
