from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from config import LOCAL_KNOWLEDGE_DIR


TOKEN_RE = re.compile(r"[a-z0-9]+")
SPLIT_RE = re.compile(r"\n(?=#)|\n{2,}")


class KnowledgeSource(ABC):
    @abstractmethod
    def get_relevant_context(self, query: str, limit: int = 3) -> list[str]:
        """Return the most relevant context snippets for the query."""


class MarkdownKnowledgeSource(KnowledgeSource):
    def __init__(self, knowledge_dir: str | Path = LOCAL_KNOWLEDGE_DIR):
        self.knowledge_dir = Path(knowledge_dir)
        self._cache: dict[Path, tuple[float, list[str]]] = {}
        self.last_selected_paths: list[str] = []

    def get_relevant_context(self, query: str, limit: int = 3) -> list[str]:
        if not self.knowledge_dir.exists():
            self.last_selected_paths = []
            return []

        scored_chunks: list[tuple[int, str, str]] = []
        query_tokens = self._tokenize(query)
        query_text = query.lower().strip()

        for path in sorted(self.knowledge_dir.glob("*.md")):
            for chunk in self._load_chunks(path):
                score = self._score_chunk(query_text, query_tokens, chunk)
                if score > 0:
                    scored_chunks.append((score, chunk, path.name))

        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        selected = scored_chunks[:limit]
        self.last_selected_paths = [filename for _, _, filename in selected]
        return [chunk for _, chunk, _ in selected]

    def _load_chunks(self, path: Path) -> list[str]:
        if not path.exists():
            return []

        mtime = path.stat().st_mtime
        cached = self._cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]

        text = path.read_text(encoding="utf-8").strip()
        raw_chunks = [part.strip() for part in SPLIT_RE.split(text) if part.strip()]
        chunks = [self._normalize_chunk(chunk) for chunk in raw_chunks]
        self._cache[path] = (mtime, chunks)
        return chunks

    def _normalize_chunk(self, chunk: str) -> str:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        return " ".join(lines)

    def _score_chunk(self, query_text: str, query_tokens: set[str], chunk: str) -> int:
        chunk_lower = chunk.lower()
        chunk_tokens = self._tokenize(chunk_lower)
        overlap = len(query_tokens & chunk_tokens)

        score = overlap * 3
        if query_text and query_text in chunk_lower:
            score += 8

        for token in query_tokens:
            if token and token in chunk_lower:
                score += 1

        if chunk.startswith("#"):
            score += 1
        return score

    def _tokenize(self, text: str) -> set[str]:
        return {token for token in TOKEN_RE.findall(text.lower()) if len(token) > 1}
