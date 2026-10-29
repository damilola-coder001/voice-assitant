import asyncio
import html
import logging
import re
from typing import List, Optional
import urllib.parse
import xml.etree.ElementTree as ET
import httpx

from app.services.tech_intelligence.cleaner import (
    clean_news_headline,
    clean_news_snippet,
)
from app.services.tech_intelligence.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

class AuthoritativeTechFeedProvider(BaseSearchProvider):
    """
    Direct feed provider aggregating primary and authoritative sources:
    - Google News RSS (Real-time global technology news)
    - Hacker News Algolia API & Firebase API (Developer discussions & trending articles)
    - CISA Known Exploited Vulnerabilities Catalog (CVEs & Cybersecurity)
    - arXiv API (AI, ML, and Advanced Computing research)
    """

    @property
    def name(self) -> str:
        return "tech_feeds"

    async def is_available(self) -> bool:
        return True

    async def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: Optional[str] = None,
    ) -> List[SearchResult]:
        lower_q = query.lower()
        results: List[SearchResult] = []

        tasks = []
        # 1. Cybersecurity specific
        if any(w in lower_q for w in ["cve", "vulnerability", "breach", "exploit", "cisa", "ransomware"]):
            tasks.append(self._fetch_cisa_vulnerabilities(query, max_results))
            tasks.append(self._fetch_google_news(f"{query} cybersecurity", max_results))

        # 2. Research / arXiv
        elif any(w in lower_q for w in ["paper", "research", "arxiv", "quantum"]):
            tasks.append(self._fetch_arxiv_papers(query, max_results))
            tasks.append(self._search_hn_algolia(query, max_results))

        # 3. AI / ML
        elif any(w in lower_q for w in ["ai", "artificial intelligence", "llm", "model", "benchmark", "claude", "gemini", "gpt", "openai", "deepseek", "anthropic"]):
            tasks.append(self._fetch_google_news(f"{query} tech", max_results))
            tasks.append(self._search_hn_algolia(query, max_results))

        # 4. Developer / Software
        elif any(w in lower_q for w in ["developer", "github", "programming", "code", "python", "rust", "javascript", "framework", "docker", "kubernetes"]):
            tasks.append(self._search_hn_algolia(query, max_results))
            tasks.append(self._fetch_google_news(f"{query} software", max_results))

        # 5. General Tech / Trending
        else:
            tasks.append(self._fetch_google_news(f"{query} technology", max_results))
            tasks.append(self._search_hn_algolia(query, max_results))
            tasks.append(self._fetch_hacker_news_stories(query, max_results))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for res in gathered:
            if isinstance(res, list):
                results.extend(res)

        return results[:max_results]

    async def _fetch_google_news(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Fetch breaking and verified tech news from Google News RSS feed."""
        results: List[SearchResult] = []
        try:
            encoded_q = urllib.parse.quote_plus(query.strip())
            rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            }
            async with httpx.AsyncClient(timeout=6.0, headers=headers, follow_redirects=True) as client:
                res = await client.get(rss_url)
                if res.status_code == 200:
                    root = ET.fromstring(res.content)
                    items = root.findall(".//item")[:limit]
                    for item in items:
                        title_el = item.find("title")
                        link_el = item.find("link")
                        pub_date_el = item.find("pubDate")
                        source_el = item.find("source")

                        desc_el = item.find("description")

                        if title_el is not None and link_el is not None:
                            full_title = html.unescape(title_el.text or "").strip()
                            link = link_el.text or ""
                            raw_pub = source_el.text if source_el is not None and source_el.text else "Tech News"
                            pub_date = pub_date_el.text[:16] if pub_date_el is not None and pub_date_el.text else None

                            # Clean publisher by stripping domain extensions and punctuation
                            clean_pub = re.sub(r"\b[a-zA-Z0-9\-\.]+\.(com|org|net|edu|gov|io|co|ai)\b", "", raw_pub).strip(",; ") or "Tech News"

                            clean_title = clean_news_headline(full_title)
                            raw_desc = html.unescape(desc_el.text or "").strip() if desc_el is not None else ""
                            clean_snip = clean_news_snippet(raw_desc, clean_title)

                            results.append(
                                SearchResult(
                                    title=clean_title,
                                    url=link,
                                    snippet=clean_snip or clean_title,
                                    publisher=clean_pub,
                                    published_date=pub_date,
                                    credibility_tier=3,
                                )
                            )
        except Exception as e:
            logger.warning(f"Error fetching Google News RSS: {e}")
        return results

    async def _search_hn_algolia(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Fetch targeted developer stories via official Hacker News Algolia Search API."""
        results: List[SearchResult] = []
        try:
            encoded_q = urllib.parse.quote_plus(query.strip())
            url = f"https://hn.algolia.com/api/v1/search?query={encoded_q}&tags=story&hitsPerPage={limit}"
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    hits = res.json().get("hits", [])
                    for hit in hits:
                        title = hit.get("title")
                        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                        points = hit.get("points") or 0
                        num_comments = hit.get("num_comments") or 0
                        created_at = (hit.get("created_at") or "")[:10]

                        if title:
                            results.append(
                                SearchResult(
                                    title=title,
                                    url=story_url,
                                    snippet=f"Hacker News discussion ({points} points, {num_comments} comments): {title}",
                                    publisher="Hacker News",
                                    published_date=created_at,
                                    credibility_tier=4,
                                )
                            )
        except Exception as e:
            logger.warning(f"Error searching HN Algolia: {e}")
        return results

    async def _fetch_hacker_news_stories(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Fetch top developer stories from official Hacker News Firebase API."""
        results: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                if res.status_code != 200:
                    return results

                story_ids = res.json()[:12]

                item_tasks = [
                    client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                    for sid in story_ids
                ]
                item_resps = await asyncio.gather(*item_tasks, return_exceptions=True)

                q_terms = [t for t in query.lower().split() if len(t) > 2]

                for item_res in item_resps:
                    if isinstance(item_res, httpx.Response) and item_res.status_code == 200:
                        data = item_res.json()
                        if not data or data.get("type") != "story":
                            continue

                        title = data.get("title", "")
                        url = data.get("url") or f"https://news.ycombinator.com/item?id={data.get('id')}"
                        score = data.get("score", 0)

                        title_lower = title.lower()
                        is_relevant = any(t in title_lower for t in q_terms) or not q_terms

                        if is_relevant:
                            results.append(
                                SearchResult(
                                    title=title,
                                    url=url,
                                    snippet=f"Trending on Hacker News ({score} points): {title}",
                                    publisher="Hacker News",
                                    credibility_tier=4,
                                )
                            )
                            if len(results) >= limit:
                                break
        except Exception as e:
            logger.warning(f"Error fetching Hacker News feed: {e}")

        return results

    async def _fetch_cisa_vulnerabilities(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Fetch authoritative confirmed vulnerabilities from CISA KEV catalog."""
        results: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(
                    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
                )
                if res.status_code != 200:
                    return results

                data = res.json()
                vulns = data.get("vulnerabilities", [])
                if not vulns:
                    return results

                recent_vulns = sorted(vulns, key=lambda v: v.get("dateAdded", ""), reverse=True)[:30]
                q_terms = [t for t in query.lower().split() if len(t) > 2]

                for v in recent_vulns:
                    cve_id = v.get("cveID", "")
                    vendor = v.get("vendorProject", "")
                    product = v.get("product", "")
                    desc = v.get("shortDescription", "")
                    action = v.get("requiredAction", "")
                    date_added = v.get("dateAdded", "")

                    content = f"{cve_id} {vendor} {product} {desc}".lower()
                    is_match = any(t in content for t in q_terms) or not q_terms

                    if is_match:
                        results.append(
                            SearchResult(
                                title=f"CISA Advisory: {cve_id} in {vendor} {product}",
                                url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                                snippet=f"{desc} (Mitigation: {action})",
                                publisher="CISA Security Advisories",
                                published_date=date_added,
                                credibility_tier=1,
                                is_primary_source=True,
                            )
                        )
                        if len(results) >= limit:
                            break
        except Exception as e:
            logger.warning(f"Error fetching CISA vulnerabilities feed: {e}")

        return results

    async def _fetch_arxiv_papers(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Fetch latest peer-reviewed AI/CS research papers from arXiv API."""
        results: List[SearchResult] = []
        try:
            clean_q = re.sub(r"[^a-zA-Z0-9\s]", "", query).strip()
            arxiv_url = f"https://export.arxiv.org/api/query?search_query=all:{clean_q}+AND+cat:cs.*&max_results={limit}&sortBy=submittedDate&sortOrder=descending"

            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(arxiv_url)
                if res.status_code == 200:
                    entries = re.findall(r"<entry>(.*?)</entry>", res.text, re.DOTALL)
                    for entry in entries:
                        title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
                        id_m = re.search(r"<id>(.*?)</id>", entry)
                        summary_m = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
                        published_m = re.search(r"<published>(.*?)</published>", entry)

                        if title_m and id_m:
                            t = re.sub(r"\s+", " ", html.unescape(title_m.group(1))).strip()
                            link = id_m.group(1).strip()
                            s = ""
                            if summary_m:
                                s = re.sub(r"\s+", " ", html.unescape(summary_m.group(1))).strip()[:300] + "..."
                            pub_date = published_m.group(1)[:10] if published_m else None

                            results.append(
                                SearchResult(
                                    title=f"arXiv Research: {t}",
                                    url=link,
                                    snippet=s,
                                    publisher="arXiv Computer Science",
                                    published_date=pub_date,
                                    credibility_tier=2,
                                    is_primary_source=True,
                                )
                            )
        except Exception as e:
            logger.warning(f"Error fetching arXiv papers: {e}")

        return results
