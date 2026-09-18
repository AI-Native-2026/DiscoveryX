"""Text embeddings (sentence-transformers, default BAAI/bge-m3).

The model is loaded lazily and cached; a clear error is raised if it cannot be
loaded so the API can degrade gracefully.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.errors import ConfigurationError
from app.core.logging import get_logger

logger = get_logger("discoveryx.embeddings")


class Embedder:
    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        from config.settings import get_settings

        s = get_settings()
        self.model_name = model_name or s.embedding_model
        self.device = device or s.embedding_device
        self.batch_size = s.embedding_batch_size
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("loading embedding model %s on %s", self.model_name, self.device)
                self._model = SentenceTransformer(self.model_name, device=self.device)
            except Exception as exc:  # noqa: BLE001
                raise ConfigurationError(
                    f"failed to load embedding model '{self.model_name}': {exc}"
                ) from exc
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, v)) for v in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def dim(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
