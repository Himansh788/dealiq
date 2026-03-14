"""
Vervotech Content Library
=========================
Scrapes, stores, and retrieves Vervotech marketing content
(case studies, blogs, ebooks, documentation, videos, etc.)

Usage:
  # Run once to seed the DB (or schedule weekly):
  python -m scripts.scrape_content

  # Query from service code:
  from services.content_library import get_relevant_content
  items = await get_relevant_content(client_type="TMC", content_types=["case_study"])
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

VERVOTECH_CONTENT_SOURCES = [
    "https://vervotech.com/case-studies/",
    "https://vervotech.com/blogs/",
    "https://vervotech.com/ebooks/",
    "https://vervotech.com/documentation/",
    "https://vervotech.com/infographics/",
    "https://vervotech.com/impact10/",
    "https://vervotech.com/on-demand-webinars/",
    "https://vervotech.com/walkthrough-videos/",
    "https://vervotech.com/hotel-mapping/",
    "https://vervotech.com/room-mapping/",
    "https://vervotech.com/dual-map/",
    "https://vervotech.com/love-for-vervotech/",
]

CLIENT_TYPES = [
    "TMC", "OTA", "B2B", "Wholesaler", "Aggregator",
    "DMC", "Metasearch", "Corporate_Travel", "Tech_Partner",
]

CONTENT_TYPE_MAP = {
    "case-studies":     "case_study",
    "blogs":            "blog",
    "ebooks":           "ebook",
    "documentation":    "documentation",
    "infographics":     "infographic",
    "on-demand-webinars": "video",
    "walkthrough-videos": "video",
    "impact10":         "impact_story",
}


# --------------------------------------------------------------------------- #
# Classification helper (AI-backed, called during scrape)
# --------------------------------------------------------------------------- #

async def _classify_content(title: str, text: str, source_url: str) -> dict:
    """
    Use Groq to classify a scraped page into client_types, products, topics,
    and generate a 2-3 sentence summary.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return {
            "client_types": [],
            "products": [],
            "topics": [],
            "has_specific_numbers": False,
            "summary": text[:300] if text else "",
            "customer_name": None,
            "customer_type": None,
        }

    snippet = text[:2000] if text else title

    prompt = f"""Classify this Vervotech content piece for a B2B hotel mapping company.

Title: {title}
URL: {source_url}
Content snippet: {snippet}

Return ONLY valid JSON:
{{
  "client_types": ["TMC"|"OTA"|"B2B"|"Wholesaler"|"Aggregator"|"DMC"|"Metasearch"|"Corporate_Travel"|"Tech_Partner"],
  "products": ["hotel_mapping"|"room_mapping"|"dual_map"|"reconfirmation"|"profit_maximizer"|"brand_mapping"],
  "topics": ["accuracy"|"ROI"|"integration"|"scale"|"cost_saving"|"automation"],
  "has_specific_numbers": true|false,
  "summary": "2-3 sentence summary for sales use",
  "customer_name": "Company name if case study else null",
  "customer_type": "TMC/OTA/etc if case study else null"
}}"""

    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=groq_key)
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        import json
        return json.loads(raw.strip())
    except Exception as e:
        logger.warning("content_library: classify failed: %s", e)
        return {
            "client_types": [],
            "products": [],
            "topics": [],
            "has_specific_numbers": False,
            "summary": text[:300] if text else "",
            "customer_name": None,
            "customer_type": None,
        }


# --------------------------------------------------------------------------- #
# Scraper
# --------------------------------------------------------------------------- #

async def scrape_vervotech_content(max_pages: int = 50) -> int:
    """
    Crawl Vervotech content pages, classify with AI, upsert into vervotech_content table.
    Returns number of pages upserted.

    Intended to be run once on startup / weekly via cron.
    """
    try:
        import httpx, re
        from database.connection import get_db
        from sqlalchemy import text
    except ImportError as e:
        logger.warning("content_library: missing dependency for scrape: %s", e)
        return 0

    upserted = 0
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for source_url in VERVOTECH_CONTENT_SOURCES:
            # Determine content type from URL path
            path_parts = [p for p in source_url.rstrip("/").split("/") if p]
            last_segment = path_parts[-1] if path_parts else ""
            content_type = CONTENT_TYPE_MAP.get(last_segment, "blog")

            try:
                resp = await client.get(source_url, headers={"User-Agent": "DealIQ/1.0 (content indexer)"})
                if resp.status_code != 200:
                    continue
                html = resp.text

                # Extract hrefs pointing to individual content pages
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
                links = set()
                for href in hrefs:
                    if not href.startswith("http"):
                        href = "https://vervotech.com" + href if href.startswith("/") else None
                    if href and "vervotech.com" in href and href != source_url:
                        links.add(href)

                # Fetch each linked content page
                for link in list(links)[:max_pages]:
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)

                    try:
                        page_resp = await client.get(link)
                        if page_resp.status_code != 200:
                            continue
                        page_html = page_resp.text

                        # Extract title
                        title_match = re.search(r'<title[^>]*>([^<]+)</title>', page_html, re.I)
                        title = title_match.group(1).strip() if title_match else link

                        # Extract body text (strip HTML tags)
                        body = re.sub(r'<script[^>]*>.*?</script>', '', page_html, flags=re.DOTALL | re.I)
                        body = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL | re.I)
                        body = re.sub(r'<[^>]+>', ' ', body)
                        body = re.sub(r'\s+', ' ', body).strip()

                        if len(body) < 100:
                            continue

                        classification = await _classify_content(title, body, link)

                        async for db in get_db():
                            if db is None:
                                break
                            import json as _json
                            await db.execute(text("""
                                INSERT INTO vervotech_content
                                  (url, title, content_type, summary, full_text,
                                   client_types, products, topics,
                                   has_specific_numbers, customer_name, customer_type,
                                   scraped_at, updated_at)
                                VALUES
                                  (:url, :title, :ct, :summary, :full_text,
                                   :client_types, :products, :topics,
                                   :has_numbers, :cust_name, :cust_type,
                                   NOW(), NOW())
                                ON CONFLICT (url) DO UPDATE SET
                                  title = EXCLUDED.title,
                                  summary = EXCLUDED.summary,
                                  full_text = EXCLUDED.full_text,
                                  client_types = EXCLUDED.client_types,
                                  products = EXCLUDED.products,
                                  topics = EXCLUDED.topics,
                                  has_specific_numbers = EXCLUDED.has_specific_numbers,
                                  updated_at = NOW()
                            """), {
                                "url": link,
                                "title": title[:500],
                                "ct": content_type,
                                "summary": classification.get("summary", "")[:1000],
                                "full_text": body[:10000],
                                "client_types": _json.dumps(classification.get("client_types", [])),
                                "products": _json.dumps(classification.get("products", [])),
                                "topics": _json.dumps(classification.get("topics", [])),
                                "has_numbers": classification.get("has_specific_numbers", False),
                                "cust_name": classification.get("customer_name"),
                                "cust_type": classification.get("customer_type"),
                            })
                            await db.commit()
                            upserted += 1
                            break

                    except Exception as e:
                        logger.warning("content_library: page fetch failed %s: %s", link, e)
                        continue

            except Exception as e:
                logger.warning("content_library: listing page failed %s: %s", source_url, e)
                continue

    logger.info("content_library: scrape complete, upserted=%d", upserted)
    return upserted


# --------------------------------------------------------------------------- #
# Query API
# --------------------------------------------------------------------------- #

async def get_relevant_content(
    client_type: str = "",
    products: Optional[list[str]] = None,
    content_types: Optional[list[str]] = None,
    limit: int = 3,
) -> list[dict]:
    """
    Return the most relevant content pieces for a prospect profile.
    Falls back to demo data if DB is unavailable or empty.
    """
    from services.task_execution_service import DEMO_CASE_STUDY_CONTENT

    try:
        from database.connection import get_db
        from sqlalchemy import text

        conditions = []
        if content_types:
            placeholders = ", ".join(f"'{t}'" for t in content_types if "'" not in t)
            conditions.append(f"content_type IN ({placeholders})")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            f"SELECT url, title, content_type, summary, has_specific_numbers "
            f"FROM vervotech_content {where} "
            f"ORDER BY has_specific_numbers DESC, scraped_at DESC "
            f"LIMIT {limit}"
        )

        async for db in get_db():
            if db is None:
                return DEMO_CASE_STUDY_CONTENT
            result = await db.execute(text(query))
            rows = result.fetchall()
            if not rows:
                return DEMO_CASE_STUDY_CONTENT
            return [
                {
                    "title": r.title,
                    "type": r.content_type,
                    "url": r.url,
                    "relevance_reason": r.summary or "",
                    "key_stats": "",
                }
                for r in rows
            ]
    except Exception as e:
        logger.debug("content_library: get_relevant_content failed: %s", e)

    from services.task_execution_service import DEMO_CASE_STUDY_CONTENT
    return DEMO_CASE_STUDY_CONTENT


async def get_stats() -> dict:
    """Return count of content pieces by type."""
    try:
        from database.connection import get_db
        from sqlalchemy import text
        async for db in get_db():
            if db is None:
                return {"total": 0, "by_type": {}}
            result = await db.execute(text(
                "SELECT content_type, COUNT(*) as cnt FROM vervotech_content GROUP BY content_type"
            ))
            by_type = {row.content_type: row.cnt for row in result.fetchall()}
            return {"total": sum(by_type.values()), "by_type": by_type}
    except Exception as e:
        logger.debug("content_library stats failed: %s", e)
    return {"total": 0, "by_type": {}}
