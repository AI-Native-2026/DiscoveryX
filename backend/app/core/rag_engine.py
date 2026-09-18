"""RAG engine — PMC-grounded retrieval with RBAC filtering and citations.

Pipeline: ingest → chunk → embed (bge-m3) → store (ChromaDB) → retrieve →
RBAC-filter by sensitivity → synthesize an answer with DeepSeek (DLP-checked).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from app.core.embeddings import get_embedder
from app.core.errors import ConfigurationError
from app.core.llm_factory import TokenLedger
from app.core.logging import get_logger
from app.models.schemas import Citation, RAGResult

logger = get_logger("discoveryx.rag")

DEFAULT_COLLECTION = "kb_public_literature"


def chunk_text(text: str, *, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Paragraph-aware fixed-size chunking with overlap."""
    from config.settings import get_settings

    s = get_settings()
    size = size or s.chunk_size
    overlap = overlap or s.chunk_overlap

    text = (text or "").strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= size:
            buf = f"{buf}\n\n{para}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(para) <= size:
                buf = para
            else:
                start = 0
                while start < len(para):
                    chunks.append(para[start : start + size])
                    start += size - overlap
                buf = ""
    if buf:
        chunks.append(buf)

    # add overlap between adjacent chunks for context continuity
    if overlap > 0 and len(chunks) > 1:
        merged = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:], strict=False):
            merged.append((prev[-overlap:] + " " + cur).strip())
        chunks = merged
    return chunks


class RAGEngine:
    def __init__(self) -> None:
        from config.settings import get_settings

        self.settings = get_settings()
        self._client: Any | None = None

    # ------------------------------------------------------------------ store
    def client(self) -> Any:
        if self._client is None:
            try:
                import os

                os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
                import chromadb

                self.settings.chroma_dir.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=str(self.settings.chroma_dir),
                    settings=chromadb.Settings(anonymized_telemetry=False),
                )
            except Exception as exc:  # noqa: BLE001
                raise ConfigurationError(f"failed to initialise ChromaDB: {exc}") from exc
        return self._client

    def _collection(self, name: str) -> Any:
        return self.client().get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def delete_collection(self, name: str) -> bool:
        """Drop a collection. Returns True when it existed and was removed."""
        try:
            self.client().delete_collection(name=name)
            logger.info("collection dropped: %s", name)
            return True
        except Exception as exc:  # noqa: BLE001 - missing collection is fine
            logger.warning("collection %s not dropped: %s", name, exc)
            return False

    # ---------------------------------------------------------------- indexing
    def index_documents(
        self,
        documents: Iterable[dict[str, Any]],
        *,
        collection: str = DEFAULT_COLLECTION,
        sensitivity: str = "public",
        source: str = "PMC",
    ) -> int:
        """Index documents. Each document needs ``id``/``text`` plus optional metadata."""
        embedder = get_embedder()
        col = self._collection(collection)

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for doc in documents:
            doc_id = str(doc.get("id") or doc.get("pmcid") or doc.get("pmid") or "")
            body = doc.get("text") or f"{doc.get('title', '')}\n\n{doc.get('abstract', '')}"
            if not doc_id or not body.strip():
                continue
            for i, chunk in enumerate(chunk_text(body)):
                ids.append(f"{doc_id}#{i}")
                texts.append(chunk)
                metadatas.append(
                    {
                        "doc_id": doc_id,
                        "chunk": i,
                        "title": doc.get("title", "")[:300],
                        "journal": doc.get("journal", ""),
                        "year": str(doc.get("year", "")),
                        "source": source,
                        "sensitivity": sensitivity,
                        "collection": collection,
                    }
                )

        if not ids:
            return 0
        embeddings = embedder.embed(texts)
        col.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        logger.info("indexed %d chunks into %s", len(ids), collection)
        return len(ids)

    def index_pmc(self, articles: Sequence[dict[str, Any]]) -> int:
        docs = [
            {
                "id": a.get("pmcid") or a.get("pmid"),
                "title": a.get("title", ""),
                "text": f"{a.get('title', '')}\n\n{a.get('abstract', '')}",
                "journal": a.get("journal", ""),
                "year": a.get("year", ""),
            }
            for a in articles
        ]
        return self.index_documents(docs, collection=DEFAULT_COLLECTION, sensitivity="public", source="PMC")

    # ------------------------------------------------------------------ query
    def _all_collections(self) -> list[str]:
        try:
            cols = self.client().list_collections()
        except Exception:  # pragma: no cover
            return []
        names: list[str] = []
        for c in cols:
            names.append(c if isinstance(c, str) else getattr(c, "name", str(c)))
        return names

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        collections: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        embedder = get_embedder()
        vec = embedder.embed_one(query)
        names = collections or self._all_collections()
        hits: list[dict[str, Any]] = []
        for name in names:
            try:
                col = self._collection(name)
                if col.count() == 0:
                    continue
                res = col.query(
                    query_embeddings=[vec],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("query failed for collection %s: %s", name, exc)
                continue
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            for text, meta, dist in zip(docs, metas, dists, strict=False):
                hits.append(
                    {
                        "text": text,
                        "metadata": meta or {},
                        "score": round(1.0 - float(dist), 4),
                    }
                )
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[: top_k * max(1, len(names))]

    async def query(
        self,
        query: str,
        principal: Any,
        *,
        top_k: int | None = None,
        collections: list[str] | None = None,
        guard: Any = None,
        ledger: Any = None,
    ) -> RAGResult:
        top_k = top_k or self.settings.rag_top_k
        retrieved = self.retrieve(query, top_k=top_k, collections=collections)
        total = len(retrieved)
        allowed = guard.filter_chunks(retrieved, principal) if guard else retrieved
        # Count only chunks withheld by policy; truncating the candidate list to
        # top_k is a ranking step, reported separately.
        blocked = total - len(allowed)
        kept = allowed[:top_k]

        citations: list[Citation] = []
        seen: set[str] = set()
        for hit in kept:
            meta = hit["metadata"]
            cid = str(meta.get("doc_id", ""))
            if cid in seen:
                continue
            seen.add(cid)
            citations.append(
                Citation(
                    id=cid,
                    title=str(meta.get("title", "")),
                    source=str(meta.get("source", "PMC")),
                    sensitivity=str(meta.get("sensitivity", "public")),
                    score=float(hit["score"]),
                    snippet=hit["text"][:240],
                )
            )

        if not kept:
            return RAGResult(
                query=query,
                answer="No accessible sources were found for this query (the knowledge base may be empty, or results were filtered by clearance).",
                citations=[],
                used_chunks=0,
                blocked_chunks=blocked,
            )

        # Meter this query on its own ledger, then roll it up into the caller's
        # (workflow run / Copilot turn) so nothing is double counted.
        own = TokenLedger()
        answer = self._synthesize(query, kept, principal=principal, guard=guard, ledger=own)
        usage = own.snapshot()
        if ledger is not None:
            ledger.add(usage)
        return RAGResult(
            query=query,
            answer=answer,
            citations=citations,
            used_chunks=len(kept),
            blocked_chunks=blocked,
            token_usage=usage,
        )

    def _synthesize(
        self,
        query: str,
        hits: list[dict[str, Any]],
        *,
        principal: Any,
        guard: Any,
        ledger: Any = None,
    ) -> str:
        from config.settings import get_settings

        sources = []
        for i, hit in enumerate(hits, 1):
            meta = hit["metadata"]
            sources.append(f"[{i}] {meta.get('doc_id')} — {meta.get('title')} ({meta.get('journal')}, {meta.get('year')})\n{hit['text']}")
        context = "\n\n".join(sources)

        if not get_settings().has_llm():
            return "Extractive answer (LLM not configured):\n\n" + context[:1200]

        from app.core.llm_factory import ChatMessage, LLMFactory

        system = (
            "You are a drug-discovery research assistant. Answer using ONLY the provided sources. "
            "Cite sources inline as [n]. If the sources are insufficient, say so explicitly. Be concise."
        )
        prompt = f"Question: {query}\n\nSources:\n{context}"
        try:
            # Share the caller's ledger so this call is metered with the rest of
            # the run (or the Copilot turn) instead of a throwaway counter.
            llm = LLMFactory(ledger) if ledger is not None else LLMFactory()
            result = llm.complete(
                [ChatMessage.system(system), ChatMessage.user(prompt)],
                principal=principal,
                guard=guard,
                purpose="rag",
            )
            return result.content.strip()
        except Exception as exc:  # noqa: BLE001 - degrade to extractive
            logger.warning("RAG synthesis failed, returning extractive: %s", exc)
            return "Extractive answer (LLM unavailable):\n\n" + context[:1200]

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        cols = []
        for name in self._all_collections():
            try:
                count = self._collection(name).count()
            except Exception:  # noqa: BLE001
                count = 0
            cols.append({"collection": name, "chunks": count})
        return {
            "store": "chromadb",
            "path": str(self.settings.chroma_dir),
            "embedding_model": self.settings.embedding_model,
            "collections": cols,
            "total_chunks": sum(c["chunks"] for c in cols),
        }
