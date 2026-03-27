from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from config import SYSTEM_PROMPT_FILE


class PromptProvider(ABC):
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt used for conversation turns."""


class FilePromptProvider(PromptProvider):
    def __init__(self, prompt_path: str | Path = SYSTEM_PROMPT_FILE):
        self.prompt_path = Path(prompt_path)
        self._cached_prompt = ""
        self._last_mtime: float | None = None

    def get_system_prompt(self) -> str:
        if not self.prompt_path.exists():
            return self._cached_prompt

        mtime = self.prompt_path.stat().st_mtime
        if self._last_mtime != mtime:
            self._cached_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
            self._last_mtime = mtime
        return self._cached_prompt
