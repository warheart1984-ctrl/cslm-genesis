"""STM — short-term / session working memory (Jarvis: budgeted active view).

In Jarvis, STM is primarily an activated *view* over LTM. In CSLM, the session
also holds working notes (turn summaries, released-claim stubs) that may later
promote to LTM only under an explicit release+receipt rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from memory.types import MemoryParticle


@dataclass
class ShortTermMemory:
    """In-process session working set. Eviction is dormancy, not deletion of LTM."""

    session_id: str
    _entries: dict[str, MemoryParticle] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    def write(self, particle: MemoryParticle) -> MemoryParticle:
        if particle.session_id and particle.session_id != self.session_id:
            raise ValueError(
                f"STM session mismatch: particle={particle.session_id} "
                f"board={self.session_id}"
            )
        particle.tier = "stm"
        particle.session_id = self.session_id
        if particle.memory_id not in self._entries:
            self._order.append(particle.memory_id)
        self._entries[particle.memory_id] = particle
        return particle

    def get(self, memory_id: str) -> MemoryParticle | None:
        return self._entries.get(memory_id)

    def list(self) -> list[MemoryParticle]:
        return [self._entries[mid] for mid in self._order if mid in self._entries]

    def remove(self, memory_id: str) -> MemoryParticle | None:
        particle = self._entries.pop(memory_id, None)
        if particle is not None and memory_id in self._order:
            self._order.remove(memory_id)
        return particle

    def clear(self) -> None:
        self._entries.clear()
        self._order.clear()

    def __len__(self) -> int:
        return len(self._entries)
