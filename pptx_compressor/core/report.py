"""Compression report: aggregates per-pass results into a summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .passes.base import PassReport


def _human_size(n: int) -> str:
    if n is None:
        return "0 B"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


@dataclass
class CompressionReport:
    """Top-level result of compressing one file."""

    input_path: str
    output_path: str
    input_size: int = 0
    output_size: int = 0
    passes: List[PassReport] = field(default_factory=list)

    @property
    def bytes_freed(self) -> int:
        return max(0, self.input_size - self.output_size)

    @property
    def savings_pct(self) -> float:
        if self.input_size <= 0:
            return 0.0
        return (self.bytes_freed / self.input_size) * 100.0

    def summary_line(self) -> str:
        return (
            f"压缩完成:{_human_size(self.input_size)} → "
            f"{_human_size(self.output_size)}"
            f"(节省 {self.savings_pct:.1f}%)"
        )

    def detail_lines(self) -> List[str]:
        lines: List[str] = []
        lines.append(self.summary_line())
        lines.append("")
        lines.append("分项报告:")
        for p in self.passes:
            if not p.ran:
                continue
            status = "✓" if p.items_affected else "—"
            lines.append(
                f"  [{status}] {p.name}:影响 {p.items_affected} 项,"
                f"节省 {_human_size(p.bytes_freed)}"
            )
            for d in p.details:
                lines.append(f"       · {d}")
        return lines

    def to_text(self) -> str:
        return "\n".join(self.detail_lines())
