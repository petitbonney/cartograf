import json

import pytest
import requests

from cartograf import gitlab_client
from cartograf.gitlab_client import AuthError, GitLabClient, NotFound, encode_id


def response(status=200, body=None, headers=None, url="https://gitlab.test/api/v4/x"):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body if body is not None else []).encode()
    r.headers.update(headers or {})
    r.url = url
    return r


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params) if params else None))
        return self.responses.pop(0)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(gitlab_client.time, "sleep", lambda s: None)
    c = GitLabClient("https://gitlab.test/", "secret-token")

    def install(responses):
        s = FakeSession(responses)
        c._local.session = s
        return s

    c.install = install
    return c


def test_encode_id():
    assert encode_id("grp/sub grp") == "grp%2Fsub%20grp"
    assert encode_id("a/b/pom.xml") == "a%2Fb%2Fpom.xml"
    assert encode_id(42) == "42"


def test_paginate_x_next_page(client):
    s = client.install([
        response(body=[{"id": 1}], headers={"x-next-page": "2"}),
        response(body=[{"id": 2}], headers={"x-next-page": ""}),
    ])
    assert [p["id"] for p in client.paginate("/groups/g/projects")] == [1, 2]
    assert s.calls[1][1]["page"] == "2"


def test_paginate_keyset_link(client):
    nxt = "https://gitlab.test/api/v4/projects/1/repository/tree?page_token=abc&per_page=100"
    s = client.install([
        response(body=[{"path": "a"}], headers={"Link": f'<{nxt}>; rel="next"'}),
        response(body=[{"path": "b"}]),
    ])
    assert [p["path"] for p in client.paginate("/projects/1/repository/tree")] == ["a", "b"]
    assert s.calls[1] == (nxt, None)


def test_retry_on_429_then_success(client, monkeypatch):
    slept = []
    monkeypatch.setattr(gitlab_client.time, "sleep", slept.append)
    client.install([response(429, headers={"Retry-After": "3"}), response(502), response(body={"ok": 1})])
    assert client.get("/user") == {"ok": 1}
    assert slept[0] == 3.0 and len(slept) == 2


def test_401_and_404(client):
    client.install([response(401)])
    with pytest.raises(AuthError):
        client.get("/user")
    client.install([response(404)])
    with pytest.raises(NotFound):
        client.get("/groups/nope")


def test_token_not_in_repr():
    c = GitLabClient("https://gitlab.test", "secret-token")
    assert "secret-token" not in repr(c)
    assert "secret-token" not in str(vars(c).get("api"))
