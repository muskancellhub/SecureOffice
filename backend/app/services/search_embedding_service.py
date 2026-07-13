"""Embedding helpers for global-search semantic lane (Slice 3).

Thin wrapper over the OpenAI embeddings API — the same provider the rest of the
app already uses (chatbot, ai_design, anam). Everything here is best-effort: if
no API key is configured or the call fails, callers get ``None`` and fall back
to lexical-only search rather than erroring.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_OPENAI_EMBEDDINGS_URL = 'https://api.openai.com/v1/embeddings'


def product_embed_text(name: str | None, vendor: str | None,
                       sku: str | None, description: str | None) -> str:
    """Build the text blob we embed for a product.

    Mirrors the fields the lexical lane weights (name/vendor/sku/description) so
    the semantic and full-text lanes are searching the same surface.
    """
    parts = [p for p in (name, vendor, sku, description) if p]
    return ' — '.join(parts)


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch of texts. Returns one vector per input, or None on failure."""
    api_key = settings.openai_api_key.strip()
    if not api_key:
        return None
    if not texts:
        return []
    try:
        resp = httpx.post(
            _OPENAI_EMBEDDINGS_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={'model': settings.search_embedding_model, 'input': texts},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # Preserve request order (API returns an 'index' per item).
        ordered = sorted(data['data'], key=lambda d: d['index'])
        return [d['embedding'] for d in ordered]
    except Exception as exc:  # noqa: BLE001 — never let search fail on embeddings
        logger.warning('embed_texts failed: %s', exc)
        return None


def embed_query(q: str) -> list[float] | None:
    """Embed a single search query. Returns the vector or None."""
    vectors = embed_texts([q])
    if not vectors:
        return None
    return vectors[0]


def to_pgvector_literal(vector: list[float]) -> str:
    """Format a Python float list as a pgvector text literal: '[0.1,0.2,...]'.

    Bound as a plain string param and cast with ``::vector`` in SQL, so no raw
    interpolation and no pgvector psycopg2 adapter registration is required.
    """
    return '[' + ','.join(repr(float(x)) for x in vector) + ']'
