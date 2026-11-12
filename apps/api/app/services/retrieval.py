"""检索（W11）：向量召回 + 关键词召回 + RRF 融合。

为什么必须混合：
- 向量擅长语义（"报销上限" ≈ "住宿标准"），但对**编号、金额、专有名词**几乎无效
  （问 "LX-HR-2026-03" 或 "10000 元"，向量召回经常漏）；
- 关键词反过来：字面命中很准，但同义表述就废。

RRF（Reciprocal Rank Fusion）融合两路排名，不需要归一化分数，是工程上最省事的选择：
    score(d) = Σ 1 / (k + rank_i(d))      k 取 60

只检索**子块**（`parent_id IS NOT NULL`），命中后按 parent_id 回填父块——
这是 W10 父子块设计的兑现点。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.embedding import get_embedder

logger = logging.getLogger(__name__)

RRF_K = 60


def _vector_candidates(
    db: Session, tenant_id: uuid.UUID, query_vec: list[float], limit: int
) -> list[dict]:
    sql = text(
        """
        SELECT c.id, c.doc_id, c.content, c.page, c.section_path, c.parent_id,
               1 - (c.embedding <=> :vec) AS score
        FROM chunk c
        WHERE c.tenant_id = :tid
          AND c.parent_id IS NOT NULL
          AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> :vec
        LIMIT :lim
        """
    )
    rows = db.execute(
        sql, {"vec": str(query_vec), "tid": str(tenant_id), "lim": limit}
    ).mappings()
    return [dict(r) for r in rows]


def _keyword_candidates(
    db: Session, tenant_id: uuid.UUID, query: str, limit: int
) -> list[dict]:
    """关键词召回：把问题切成词，任一词命中即召回。

    中文没有分词器（zhparser 需要编译），所以用朴素的"子串命中"：
    对每个长度 ≥ 2 的词做 ILIKE。对金额、编号、专有名词特别有效。
    """
    tokens = [
        t.strip()
        for t in query.replace("？", " ").replace("，", " ").replace("。", " ").split()
        if len(t.strip()) >= 2
    ]
    if not tokens:
        return []

    patterns = [f"%{t}%" for t in tokens]
    sql = text(
        """
        SELECT c.id, c.doc_id, c.content, c.page, c.section_path, c.parent_id,
               (SELECT count(*) FROM unnest(CAST(:patterns AS text[])) p WHERE c.content ILIKE p) AS score
        FROM chunk c
        WHERE c.tenant_id = :tid
          AND c.parent_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM unnest(CAST(:patterns AS text[])) p WHERE c.content ILIKE p)
        ORDER BY score DESC
        LIMIT :lim
        """
    )
    rows = db.execute(
        sql,
        {
            "patterns": patterns,
            "tid": str(tenant_id),
            "lim": limit,
        },
    ).mappings()
    return [dict(r) for r in rows]


def rrf_fuse(vector: list[dict], keyword: list[dict], limit: int) -> list[dict]:
    """按名次融合两路结果（分数不可比，只用排名）。"""
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}

    for rank, row in enumerate(vector, start=1):
        key = str(row["id"])
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
        by_id[key] = row

    for rank, row in enumerate(keyword, start=1):
        key = str(row["id"])
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
        by_id.setdefault(key, row)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    out = []
    for key, score in ranked:
        row = dict(by_id[key])
        row["rrf_score"] = round(score, 6)
        out.append(row)
    return out


def search(
    db: Session, *, tenant_id: uuid.UUID, query: str, top_k: int | None = None
) -> list[dict]:
    """返回融合后的候选块（含所属文档名，便于引用展示）。"""
    s = get_settings()
    top_k = top_k or s.retrieval_top_k
    cand = s.retrieval_candidates

    embedder = get_embedder()
    query_vec = embedder.embed([query])[0]

    vector_hits = _vector_candidates(db, tenant_id, query_vec, cand)
    keyword_hits = _keyword_candidates(db, tenant_id, query, cand)

    fused = rrf_fuse(vector_hits, keyword_hits, top_k * 2)

    # 补文档名（引用里要显示"来自哪份文档"）
    if fused:
        doc_ids = list({str(r["doc_id"]) for r in fused})
        rows = db.execute(
            text("SELECT id, name FROM document WHERE id::text = ANY(:ids)"),
            {"ids": doc_ids},
        ).mappings()
        names = {str(r["id"]): r["name"] for r in rows}
        for r in fused:
            r["doc_name"] = names.get(str(r["doc_id"]), "")

    return fused[:top_k]


def build_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    """把候选块拼成给模型看的上下文，并返回引用列表。

    编号从 1 开始，模型只需输出 [1][2]；真正的映射由程序维护——
    让模型自己写文档名和页码它一定会编。
    """
    if not chunks:
        return "", []

    parts: list[str] = []
    citations: list[dict] = []
    for i, c in enumerate(chunks, start=1):
        doc = c.get("doc_name") or "未知文档"
        section = c.get("section_path") or ""
        page = c.get("page") or 0
        header = f"[{i}] 《{doc}》{section}（第 {page} 页）"
        parts.append(f"{header}\n{c['content']}")
        citations.append(
            {
                "index": i,
                "chunk_id": str(c["id"]),
                "doc_id": str(c["doc_id"]),
                "doc_name": doc,
                "page": page,
                "section_path": section,
                "snippet": c["content"][:120],
            }
        )
    return "\n\n".join(parts), citations