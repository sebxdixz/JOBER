"""Web search helpers for job discovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}


@dataclass(frozen=True)
class SearchConfig:
    provider: str
    api_key: str | None = None


def get_search_config() -> SearchConfig:
    provider = os.getenv("JOBER_SEARCH_PROVIDER", "duckduckgo").strip().lower()
    api_key = os.getenv("JOBER_SEARCH_API_KEY", "").strip() or None
    return SearchConfig(provider=provider, api_key=api_key)


def _fetch_text(url: str, headers: dict[str, str], body: bytes | None = None) -> str:
    request = Request(url, headers=headers, data=body)
    with urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _fetch_json(url: str, headers: dict[str, str], body: bytes | None = None) -> dict:
    text = _fetch_text(url, headers, body)
    return json.loads(text)


def _dedupe(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def search_duckduckgo(query: str, max_results: int = 20) -> list[str]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html = _fetch_text(url, headers=DEFAULT_HEADERS)
    soup = BeautifulSoup(html, "html.parser")
    urls = [a.get("href", "").strip() for a in soup.select("a.result__a[href]")]
    return _dedupe(urls)[:max_results]


def search_serper(query: str, max_results: int = 20, api_key: str | None = None) -> list[str]:
    if not api_key:
        return []
    payload = json.dumps({"q": query, "num": max_results}).encode("utf-8")
    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    }
    data = _fetch_json("https://google.serper.dev/search", headers=headers, body=payload)
    urls = [item.get("link", "") for item in data.get("organic", []) if isinstance(item, dict)]
    return _dedupe(urls)[:max_results]


def search_serpapi(query: str, max_results: int = 20, api_key: str | None = None) -> list[str]:
    if not api_key:
        return []
    url = (
        "https://serpapi.com/search.json?"
        f"engine=google&q={quote_plus(query)}&num={max_results}&api_key={api_key}"
    )
    data = _fetch_json(url, headers=DEFAULT_HEADERS)
    urls = [item.get("link", "") for item in data.get("organic_results", []) if isinstance(item, dict)]
    return _dedupe(urls)[:max_results]


def search_web(query: str, max_results: int = 20, config: SearchConfig | None = None) -> list[str]:
    config = config or get_search_config()
    provider = config.provider
    if provider == "serper":
        return search_serper(query, max_results=max_results, api_key=config.api_key)
    if provider == "serpapi":
        return search_serpapi(query, max_results=max_results, api_key=config.api_key)
    return search_duckduckgo(query, max_results=max_results)
