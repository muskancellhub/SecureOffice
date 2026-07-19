"""Backfill product embeddings for global-search semantic lane (Slice 3).

Populates products.embedding for every active product that doesn't have one yet
(or, with --all, re-embeds everything). Idempotent and resumable — safe to run
repeatedly. Requires pgvector installed and OPENAI_API_KEY set.

Usage:
    python -m scripts.backfill_search_embeddings          # only missing rows
    python -m scripts.backfill_search_embeddings --all     # re-embed all active
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from app.core.database import engine
from app.services.search_embedding_service import (
    embed_texts,
    product_embed_text,
    to_pgvector_literal,
)

BATCH = 100


def _embedding_column_exists(conn) -> bool:
    return bool(conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='products' AND column_name='embedding'"
    )).scalar())


def main(reembed_all: bool = False) -> int:
    with engine.begin() as conn:
        if not _embedding_column_exists(conn):
            print('products.embedding column not found — is pgvector installed? '
                  'Aborting.')
            return 1

        where = 'is_active = true'
        if not reembed_all:
            where += ' AND embedding IS NULL'
        rows = conn.execute(text(
            f"SELECT id, name, vendor, sku, description FROM products WHERE {where}"
        )).all()

    print(f'{len(rows)} product(s) to embed '
          f"({'all active' if reembed_all else 'missing only'})")
    if not rows:
        return 0

    done = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        texts = [
            product_embed_text(r.name, r.vendor, r.sku, r.description)
            for r in chunk
        ]
        vectors = embed_texts(texts)
        if vectors is None:
            print('Embedding call failed (no OPENAI_API_KEY or API error). '
                  'Aborting.')
            return 1

        with engine.begin() as conn:
            for r, vec in zip(chunk, vectors):
                conn.execute(
                    text("UPDATE products SET embedding = CAST(:emb AS vector) "
                         "WHERE id = :id"),
                    {'emb': to_pgvector_literal(vec), 'id': str(r.id)},
                )
        done += len(chunk)
        print(f'  embedded {done}/{len(rows)}')

    print('Done.')
    return 0


if __name__ == '__main__':
    sys.exit(main(reembed_all='--all' in sys.argv))
