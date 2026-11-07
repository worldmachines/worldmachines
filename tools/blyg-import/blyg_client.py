"""The whole HTTP surface the importer uses: three Studio owner-API calls.

Kept small and isolated so a change to the API base (e.g. /api moving under
the mount) or the auth scheme touches only this file.

  POST /items                 {"kind":...,"contentMd":...}                 -> 201 item (id, revision)
  GET /items/{id}                                                          -> 200 item (revision)
  PATCH /items/{id}           {"contentMd":..., "expectedRevision": n}     -> 200 item (revision)
  POST /items/{id}/publish    {"note"?: ..., "expectedRevision": n}        -> 200 {ok, version, revision}

Studio's private contract 5.x (0.49.12+): camelCase fields, and item commands
conditional on the item's `revision` (a stale one is a 409 revision-conflict;
we re-read once and retry, as website/scripts/blyg_sync.py does).
"""

from __future__ import annotations

import email.utils
import json
import time
import urllib.error
import urllib.request
from typing import Callable, Optional


class ApiError(Exception):
    def __init__(self, status: int, body: str, method: str = "", path: str = ""):
        self.status, self.body, self.method, self.path = status, body, method, path
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:500]}")


def _retry_after(value: Optional[str], default: float) -> float:
    if not value:
        return default
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value).timestamp()
            return max(0.0, when - time.time())
        except (TypeError, ValueError):
            return default


class BlygClient:
    def __init__(self, base: str, token: str, write_interval: float = 1.1, max_retries: int = 8,
                 timeout: float = 60.0, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, opener=None, log=print):
        self.base = base.rstrip("/")
        self.token = token
        self.write_interval = write_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self.sleep, self.clock = sleep, clock
        self.opener = opener or urllib.request.urlopen
        self.log = log
        self._last_write = None
        self.calls = 0
        self._revisions: dict = {}

    # The delegated write budget is 60/min shared by all grants (API_DELEGATED_WRITE_LIMIT),
    # so writes are paced; 429s are still honoured below.
    def _pace(self):
        if self._last_write is not None:
            wait = self.write_interval - (self.clock() - self._last_write)
            if wait > 0:
                self.sleep(wait)
        self._last_write = self.clock()

    def _request(self, method: str, path: str, body: Optional[dict]) -> dict:
        url = self.base + path
        data = None if body is None else json.dumps(body).encode("utf-8")
        backoff = 2.0
        for attempt in range(self.max_retries + 1):
            if method != "GET":
                self._pace()
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "worldmachines-blyg-import/1",
            })
            self.calls += 1
            try:
                with self.opener(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
                retryable = e.code == 429 or e.code in (502, 503, 504)
                if retryable and attempt < self.max_retries:
                    wait = _retry_after(e.headers.get("Retry-After") if e.headers else None, backoff)
                    self.log(f"  HTTP {e.code} on {method} {path}; waiting {wait:.0f}s")
                    self.sleep(wait)
                    backoff = min(backoff * 2, 300)
                    continue
                raise ApiError(e.code, raw, method, path) from None
            except urllib.error.URLError as e:
                # A lost connection on create may have created the item; do not
                # retry it blind (a duplicate draft is worse than a stop).
                if path == "/items" and method == "POST":
                    raise
                if attempt < self.max_retries:
                    self.log(f"  network error on {method} {path}: {e.reason}; retrying in {backoff:.0f}s")
                    self.sleep(backoff)
                    backoff = min(backoff * 2, 300)
                    continue
                raise
        raise RuntimeError("unreachable")

    def create_item(self, content_md: str, kind: str) -> str:
        item = self._request("POST", "/items", {"kind": kind, "contentMd": content_md})
        self._note_revision(item.get("id"), item)
        return item["id"]

    def update_item(self, item_id: str, content_md: str) -> None:
        self._item_command("PATCH", item_id, f"/items/{item_id}", {"contentMd": content_md})

    def publish_item(self, item_id: str, note: Optional[str] = None) -> int:
        body = {"note": note} if note else {}
        return int(self._item_command("POST", item_id, f"/items/{item_id}/publish", body)["version"])

    def _item_command(self, method: str, item_id: str, path: str, body: dict) -> dict:
        for attempt in (0, 1):
            rev = self._revisions.get(item_id)
            if rev is None:
                rev = self._request("GET", f"/items/{item_id}", None).get("revision")
            try:
                out = self._request(method, path, dict(body, expectedRevision=rev))
            except ApiError as e:
                if attempt == 0 and e.status == 409 and "revision-conflict" in (e.body or ""):
                    self._revisions.pop(item_id, None)
                    continue
                raise
            self._note_revision(item_id, out)
            return out
        raise RuntimeError("unreachable")

    def _note_revision(self, item_id, payload) -> None:
        if item_id and isinstance(payload, dict) and isinstance(payload.get("revision"), int):
            self._revisions[item_id] = payload["revision"]
