"""Mini-suite para probar estrategias de scraping/busqueda en LinkedIn y MeetFrank.

Uso:
  python scripts/search_probe.py --platform linkedin --keywords "AI Engineer,LLM Engineer" --locations "Remote"
  python scripts/search_probe.py --platform meetfrank --keywords "AI Engineer,ML Engineer" --locations "Remote"
"""

from __future__ import annotations

import argparse
import time
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


@dataclass
class Lead:
    url: str
    title: str
    company: str = ""
    location: str = ""


def _fetch(url: str, timeout: int = 20) -> str:
    req = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _parse_linkedin(html: str, limit: int) -> list[Lead]:
    soup = BeautifulSoup(html, "html.parser")
    leads: list[Lead] = []

    for card in soup.select("div.base-search-card")[: limit * 2]:
        link = card.select_one("a.base-card__full-link")
        if not link:
            continue
        url = link.get("href", "").split("?")[0].strip()
        if not url:
            continue
        title_el = card.select_one("h3.base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle")
        location_el = card.select_one("span.job-search-card__location")
        title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else ""
        company = " ".join(company_el.get_text(" ", strip=True).split()) if company_el else ""
        location = " ".join(location_el.get_text(" ", strip=True).split()) if location_el else ""
        leads.append(Lead(url=url, title=title, company=company, location=location))
        if len(leads) >= limit:
            break

    if leads:
        return leads

    # Fallback: anchors directos
    seen: set[str] = set()
    for anchor in soup.select("a[href*='/jobs/view/']"):
        url = anchor.get("href", "").split("?")[0].strip()
        if not url or url in seen:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        leads.append(Lead(url=url, title=title))
        seen.add(url)
        if len(leads) >= limit:
            break
    return leads


def _parse_meetfrank(html: str, limit: int) -> list[Lead]:
    soup = BeautifulSoup(html, "html.parser")
    leads: list[Lead] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        if "/jobs/" not in href and "/offer/" not in href:
            continue
        url = href
        if not url.startswith("http"):
            url = f"https://meetfrank.com{url}"
        url = url.split("#")[0]
        if url in seen:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        leads.append(Lead(url=url, title=title))
        seen.add(url)
        if len(leads) >= limit:
            break
    return leads


def _score_keyword_hits(leads: Iterable[Lead], keywords: list[str]) -> int:
    hits = 0
    for lead in leads:
        title = lead.title.lower()
        if any(kw.lower() in title for kw in keywords if kw):
            hits += 1
    return hits


def _dedupe(leads: Iterable[Lead]) -> list[Lead]:
    seen: set[str] = set()
    unique: list[Lead] = []
    for lead in leads:
        if lead.url in seen:
            continue
        seen.add(lead.url)
        unique.append(lead)
    return unique


def _build_linkedin_url(keyword: str, location: str, start: int, tpr: str | None, remote_only: bool) -> str:
    keyword_q = quote_plus(keyword)
    location_q = quote_plus(location) if location else ""
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={keyword_q}&location={location_q}&start={start}"
    )
    if tpr:
        url += f"&f_TPR={tpr}"
    if remote_only:
        url += "&f_WT=2"
    return url


def _build_linkedin_public_url(keyword: str, location: str, tpr: str | None) -> str:
    keyword_q = quote_plus(keyword)
    location_q = quote_plus(location) if location else ""
    url = f"https://www.linkedin.com/jobs/search/?keywords={keyword_q}&location={location_q}"
    if tpr:
        url += f"&f_TPR={tpr}"
    return url


def run_linkedin(
    keywords: list[str],
    locations: list[str],
    limit: int,
    max_requests: int,
    verbose: bool,
):
    strategies = [
        ("guest_recent_remote", {"tpr": "r604800", "remote_only": True, "public": False}),
        ("guest_recent", {"tpr": "r604800", "remote_only": False, "public": False}),
        ("guest_30d", {"tpr": "r2592000", "remote_only": False, "public": False}),
        ("guest_unfiltered", {"tpr": None, "remote_only": False, "public": False}),
        ("public_search", {"tpr": "r604800", "remote_only": False, "public": True}),
    ]

    starts = [0, 25, 50]
    if not locations:
        locations = [""]

    for name, config in strategies:
        all_leads: list[Lead] = []
        requests = 0
        for kw in keywords:
            for loc in locations[:3] + [""]:
                remote_only = config["remote_only"] or (loc.lower() in {"remote", "remoto"})
                if config["public"]:
                    url = _build_linkedin_public_url(kw, loc, config["tpr"])
                    try:
                        html = _fetch(url)
                    except Exception as exc:
                        requests += 1
                        if verbose:
                            print(f"  [warn] {name} fetch failed: {exc}")
                        continue
                    all_leads.extend(_parse_linkedin(html, limit))
                    requests += 1
                else:
                    for start in starts:
                        url = _build_linkedin_url(kw, loc, start, config["tpr"], remote_only)
                        try:
                            html = _fetch(url)
                        except Exception as exc:
                            requests += 1
                            if verbose:
                                print(f"  [warn] {name} fetch failed: {exc}")
                            continue
                        all_leads.extend(_parse_linkedin(html, limit))
                        requests += 1
                        if requests >= max_requests:
                            break
                if requests >= max_requests:
                    break
            if requests >= max_requests:
                break

        unique = _dedupe(all_leads)
        hits = _score_keyword_hits(unique, keywords)
        print(f"\n[LinkedIn] {name}")
        print(f"  Requests: {requests}")
        print(f"  Leads: {len(unique)} | Keyword hits: {hits}")
        for lead in unique[: min(5, len(unique))]:
            print(f"  - {lead.title[:80]} | {lead.url}")


def run_meetfrank(
    keywords: list[str],
    locations: list[str],
    limit: int,
    max_requests: int,
    verbose: bool,
):
    strategies = [
        ("search_param", {"param": "search"}),
        ("query_param", {"param": "query"}),
        ("search_with_remote", {"param": "search", "force_remote": True}),
    ]

    if not locations:
        locations = [""]

    for name, config in strategies:
        all_leads: list[Lead] = []
        requests = 0
        for kw in keywords:
            for loc in locations[:3] + [""]:
                query_parts = [kw, loc]
                if config.get("force_remote"):
                    query_parts.append("remote")
                query = " ".join(part for part in query_parts if part)
                query_q = quote_plus(query)
                url = f"https://meetfrank.com/jobs?{config['param']}={query_q}"
                try:
                    html = _fetch(url)
                except Exception as exc:
                    requests += 1
                    if verbose:
                        print(f"  [warn] {name} fetch failed: {exc}")
                    continue
                all_leads.extend(_parse_meetfrank(html, limit))
                requests += 1
                if requests >= max_requests:
                    break
            if requests >= max_requests:
                break

        unique = _dedupe(all_leads)
        hits = _score_keyword_hits(unique, keywords)
        print(f"\n[MeetFrank] {name}")
        print(f"  Requests: {requests}")
        print(f"  Leads: {len(unique)} | Keyword hits: {hits}")
        for lead in unique[: min(5, len(unique))]:
            print(f"  - {lead.title[:80]} | {lead.url}")


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def main():
    parser = argparse.ArgumentParser(description="Probe scraping strategies for LinkedIn/MeetFrank.")
    parser.add_argument("--platform", choices=["linkedin", "meetfrank", "all"], default="all")
    parser.add_argument("--keywords", default="AI Engineer,LLM Engineer,ML Engineer")
    parser.add_argument("--locations", default="Remote,Remoto")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-requests", type=int, default=12)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    keywords = _split_csv(args.keywords)
    locations = _split_csv(args.locations)

    if args.platform in ("linkedin", "all"):
        run_linkedin(keywords, locations, args.limit, args.max_requests, args.verbose)
        time.sleep(args.sleep)

    if args.platform in ("meetfrank", "all"):
        run_meetfrank(keywords, locations, args.limit, args.max_requests, args.verbose)


if __name__ == "__main__":
    main()
