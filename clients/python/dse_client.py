"""BANXE DSE advisory client — partner SDK skeleton (copy into your project).

Thin wrapper over ``POST {base_url}/v1/dss/recommend``. ADVISORY-ONLY: the DSE
returns explainable recommendations with Risk/Earn metrics; it NEVER executes
orders, signs transactions, or holds keys. The sandbox returns mock/simulated
data — do not use it in a real-money production path.

Not published to any package registry; this is a documentation skeleton. The HTTP
client is injectable so it can be unit-tested with no network.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class DseClientError(Exception):
    """Raised on a non-2xx response from the DSE endpoint."""


@runtime_checkable
class HttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


@runtime_checkable
class HttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...


def _default_http() -> HttpClient:  # pragma: no cover - exercised only with a real client
    import httpx

    return httpx.Client()


class DseClient:
    """Minimal advisory client. `api_key` is a sandbox placeholder by default."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout: float = 10.0,
        http: HttpClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._http = http if http is not None else _default_http()

    def recommend(self, request: dict[str, Any]) -> dict[str, Any]:
        """POST a RecommendRequest, return the RecommendResponse JSON.

        Raises ``DseClientError`` on any 4xx/5xx. Advisory-only — the response is
        guidance, not execution; your app prompts the user to confirm manually.
        """
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        resp = self._http.post(
            f"{self._base}/v1/dss/recommend",
            json=request,
            headers=headers,
            timeout=self._timeout,
        )
        if resp.status_code >= 500:
            raise DseClientError(f"DSE server error: {resp.status_code}")
        if resp.status_code >= 400:
            raise DseClientError(f"DSE request rejected: {resp.status_code}")
        result: dict[str, Any] = resp.json()
        return result
