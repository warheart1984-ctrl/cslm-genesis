"""LTM — longer-term durable Continuity Ledger store (append-only JSONL).

Jarvis Memoryboard treats the Continuity Ledger as LTM SoT. CSLM mirrors that
with a local append-only file. Live data paths belong in gitignore.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from memory.types import MemoryParticle

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LTM_PATH = ROOT / "memory" / "data" / "ltm.jsonl"
LTM_PATH_ENV = "CSLM_LTM_PATH"


def ltm_path(override: Path | None = None) -> Path:
    if override is not None:
        return override
    env = os.environ.get(LTM_PATH_ENV, "").strip()
    if env:
        return Path(env)
    return DEFAULT_LTM_PATH


class LongTermMemory:
    """Append-only durable particle store. Mutations append superseding rows."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = ltm_path(path)
        self._by_id: dict[str, MemoryParticle] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            for raw in self.path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line:
                    continue
                particle = MemoryParticle.from_dict(json.loads(line))
                particle.tier = "ltm"
                self._by_id[particle.memory_id] = particle
        except Exception:
            # Torn tail must not wipe a valid prefix.
            pass

    def append(self, particle: MemoryParticle) -> MemoryParticle:
        self._ensure_loaded()
        particle.tier = "ltm"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(particle.to_dict(), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
        self._by_id[particle.memory_id] = particle
        return particle

    def get(self, memory_id: str) -> MemoryParticle | None:
        self._ensure_loaded()
        return self._by_id.get(memory_id)

    def list(self) -> list[MemoryParticle]:
        self._ensure_loaded()
        return list(self._by_id.values())

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._by_id)
