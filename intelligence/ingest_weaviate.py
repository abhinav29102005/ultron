"""
intelligence/ingest_weaviate.py
===============================

Simple CLI to ingest web search results (via WebSkill) or a list of URLs
into the configured Weaviate instance. Designed for manual runs during
development; it uses the application's ServiceContainer to reuse settings
and web scraping code.

Usage examples:
  python -m intelligence.ingest_weaviate --query "python coroutines" --limit 5
  python -m intelligence.ingest_weaviate --urls urls.txt

"""
from __future__ import annotations

import asyncio
import logging
from typing import List

import typer

from core.container import ServiceContainer
from config.settings import Settings

app = typer.Typer()
logger = logging.getLogger("ingest_weaviate")


async def _run_query(container: ServiceContainer, query: str, limit: int = 5) -> List[dict]:
    web = container.web_skill
    docs = []
    results = await web.search(query, max_results=limit)
    for i, r in enumerate(results):
        try:
            text = await web.fetch_page(r.url, max_chars=4000)
        except Exception:
            text = ""
        docs.append({
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
            "content": text,
            "source": r.source or "web",
            "doc_id": f"Doc_{i+1:02d}",
            "section": "§1",
        })
    return docs


async def _run_urls(container: ServiceContainer, urls: List[str]) -> List[dict]:
    web = container.web_skill
    docs = []
    for i, u in enumerate(urls):
        try:
            text = await web.fetch_page(u, max_chars=4000)
        except Exception:
            text = ""
        docs.append({
            "title": u,
            "url": u,
            "snippet": "",
            "content": text,
            "source": "web",
            "doc_id": f"Doc_{i+1:02d}",
            "section": "§1",
        })
    return docs


@app.command()
def ingest(query: str | None = None, urls: str | None = None, limit: int = 5):
    """Ingest either search results for `query` or newline-separated `urls` file."""
    settings = Settings.load()
    container = ServiceContainer(settings)

    async def _main():
        await container.initialise()
        if query:
            docs = await _run_query(container, query, limit=limit)
        elif urls:
            with open(urls, "r", encoding="utf-8") as fh:
                ulist = [l.strip() for l in fh if l.strip()]
            docs = await _run_urls(container, ulist)
        else:
            typer.echo("Provide --query or --urls")
            raise typer.Exit(code=2)

        wc = container.weaviate_client
        if wc is None:
            typer.echo("No Weaviate client configured (WEAVIATE_URL missing or client unavailable).")
            raise typer.Exit(code=1)

        typer.echo(f"Indexing {len(docs)} docs into Weaviate...")
        wc.ingest_documents(docs)
        typer.echo("Done.")

    asyncio.run(_main())


if __name__ == "__main__":
    app()
