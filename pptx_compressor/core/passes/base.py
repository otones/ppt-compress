"""Base classes for compression passes and per-pass report records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from ..pptx import PptxFile


@dataclass
class PassReport:
    """Result of running a single compression pass."""

    name: str  # human label
    enabled: bool
    ran: bool = False
    # Bytes freed by *this* pass (best-effort; image pass counts recompression
    # deltas; deletion passes count the size of removed parts).
    bytes_freed: int = 0
    items_affected: int = 0
    details: List[str] = field(default_factory=list)

    def add_detail(self, msg: str) -> None:
        self.details.append(msg)


class CompressionPass(ABC):
    """Abstract base for a single compression pass."""

    # Stable id matching Settings attribute name.
    id: str = ""
    label: str = ""

    def __init__(self, settings):
        self.settings = settings
        self.report = PassReport(name=self.label, enabled=self._is_enabled())

    def _is_enabled(self) -> bool:
        return bool(getattr(self.settings, self.id, True))

    @abstractmethod
    def run(self, pptx: PptxFile) -> PassReport:
        """Execute the pass in-place on pptx. Returns a PassReport."""
        ...

    def _size_of(self, pptx: PptxFile, path: str) -> int:
        part = pptx.get_part(path)
        return len(part.data) if part is not None else 0
