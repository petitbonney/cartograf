"""Minimal GitLab REST v4 client: auth, pagination, retry/backoff, URL encoding.

The token is only ever placed in the PRIVATE-TOKEN request header. It is never
logged, never put in a URL, and never returned to callers.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Iterator
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class GitLabError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class AuthError(GitLabError):
    """Token missing, rejected (401) or lacking scope (403 on /user)."""


class NotFound(GitLabError):
    """404: resource missing or not visible to the token's user."""


def encode_id(id_or_path: int | str) -> str:
    """Encode a project/group ID or full path for use in a URL segment."""
    return quote(str(id_or_path), safe="")


class GitLabClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        pool_size: int = 8,
        max_retries: int = 6,
        timeout: float = 60.0,
    ):
        if not token:
            raise AuthError("GITLAB_TOKEN is empty")
        self.base_url = base_url.rstrip("/")
        self.api = self.base_url + "/api/v4"
        self._token = token
        self._pool_size = pool_size
        self.max_retries = max_retries
        self.timeout = timeout
        self._local = threading.local()
        self.request_count = 0
        self._count_lock = threading.Lock()

    def __repr__(self) -> str:  # never show the token
        return f"GitLabClient({self.base_url!r})"

    # -- low level -------------------------------------------------------

    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers["PRIVATE-TOKEN"] = self._token
            s.headers["User-Agent"] = "cartograf/1"
            adapter = HTTPAdapter(pool_connections=4, pool_maxsize=self._pool_size)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            self._local.session = s
        return s

    def _request(self, url: str, params: dict | None = None) -> requests.Response:
        attempt = 0
        while True:
            attempt += 1
            with self._count_lock:
                self.request_count += 1
            try:
                resp = self._session().get(url, params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt > self.max_retries:
                    raise GitLabError(f"network error on {url}: {exc}") from exc
                self._sleep(attempt, None, f"network error ({exc.__class__.__name__})")
                continue

            if resp.status_code < 400:
                return resp
            if resp.status_code == 401:
                raise AuthError("GitLab rejected the token (401). Check GITLAB_TOKEN.", 401)
            if resp.status_code == 404:
                raise NotFound(f"not found: {url}", 404)
            if resp.status_code in RETRY_STATUSES and attempt <= self.max_retries:
                self._sleep(attempt, resp.headers.get("Retry-After"), f"HTTP {resp.status_code}")
                continue
            raise GitLabError(
                f"HTTP {resp.status_code} on {url}: {resp.text[:200]}", resp.status_code
            )

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None, why: str) -> None:
        delay: float
        try:
            delay = float(retry_after) if retry_after else 0.0
        except ValueError:
            delay = 0.0
        if delay <= 0:
            delay = min(60.0, 2 ** (attempt - 1)) + random.uniform(0, 0.5)
        log.debug("retrying after %s in %.1fs (attempt %d)", why, delay, attempt)
        time.sleep(delay)

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request(self.api + path, params).json()

    def get_raw(self, path: str, params: dict | None = None) -> bytes:
        return self._request(self.api + path, params).content

    def paginate(self, path: str, params: dict | None = None) -> Iterator[dict]:
        """Yield items across pages. Follows `Link: rel=next` (keyset) or `x-next-page`."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        url: str | None = self.api + path
        while url:
            resp = self._request(url, params)
            data = resp.json()
            if not isinstance(data, list):
                raise GitLabError(f"expected a list from {path}")
            yield from data
            next_link = resp.links.get("next", {}).get("url")
            if next_link:
                url, params = next_link, None  # the link carries all params
                continue
            next_page = resp.headers.get("x-next-page")
            if next_page and data:
                params = dict(params or {})
                params["page"] = next_page
                url = self.api + path
            else:
                url = None

    # -- endpoints -------------------------------------------------------

    def current_user(self) -> dict:
        try:
            return self.get("/user")
        except GitLabError as exc:
            if exc.status == 403:
                raise AuthError("token lacks the read_api scope (403 on /user)", 403) from exc
            raise

    def group_projects(self, group: int | str) -> Iterator[dict]:
        return self.paginate(
            f"/groups/{encode_id(group)}/projects",
            {
                "include_subgroups": "true",
                "archived": "false",
                "with_shared": "false",
                "order_by": "id",
                "sort": "asc",
            },
        )

    def branches(self, project_id: int) -> list[dict]:
        return list(self.paginate(f"/projects/{project_id}/repository/branches"))

    def tree(self, project_id: int, ref: str) -> Iterator[dict]:
        return self.paginate(
            f"/projects/{project_id}/repository/tree",
            {"recursive": "true", "ref": ref, "pagination": "keyset"},
        )

    def raw_file(self, project_id: int, file_path: str, ref: str) -> bytes:
        return self.get_raw(
            f"/projects/{project_id}/repository/files/{encode_id(file_path)}/raw",
            {"ref": ref},
        )

    def tags(self, project_id: int, limit: int = 100) -> list[dict]:
        """Most recently updated tags (one page)."""
        return self.get(
            f"/projects/{project_id}/repository/tags",
            {"order_by": "updated", "sort": "desc", "per_page": limit},
        )
