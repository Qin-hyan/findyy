"""物品词表与中文别名（供检测提示词与自然语言查询实体对齐共用）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ObjectClass:
    zh: str
    en: str
    aliases: list[str] = field(default_factory=list)
    threshold: float = 0.12
    min_area: float = 0.0005
    context_only: bool = False

    def all_names(self) -> list[str]:
        return [self.zh, *self.aliases]


@dataclass
class ObjectCatalog:
    classes: list[ObjectClass]
    color_aliases: dict[str, list[str]]
    example_queries: list[str]

    @property
    def detectable(self) -> list[ObjectClass]:
        return [c for c in self.classes if not c.context_only]

    def by_en(self, en: str) -> ObjectClass | None:
        for c in self.classes:
            if c.en.lower() == en.lower():
                return c
        return None

    def by_zh(self, zh: str) -> ObjectClass | None:
        for c in self.classes:
            if c.zh == zh:
                return c
        return None

    def match_alias(self, alias: str) -> ObjectClass | None:
        alias = alias.strip()
        if not alias:
            return None
        for c in self.classes:
            if alias == c.zh or alias in c.aliases:
                return c
        # 子串匹配：如 "我的车钥匙" 命中 "车钥匙"
        best: tuple[int, ObjectClass] | None = None
        for c in self.classes:
            for name in c.all_names():
                if name and name in alias:
                    if best is None or len(name) > best[0]:
                        best = (len(name), c)
        return best[1] if best else None

    def normalize_color(self, text: str) -> str | None:
        for canonical, words in self.color_aliases.items():
            for w in words:
                if w in text:
                    return canonical
            if canonical in text:
                return canonical
        return None

    def prompt_map(self) -> dict[int, ObjectClass]:
        """OWLv2 提示词下标 -> 类别（仅可检测类别）。"""
        return {i: c for i, c in enumerate(self.detectable)}


def load_catalog(path: str | Path) -> ObjectCatalog:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"物品词表不存在: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    classes = [
        ObjectClass(
            zh=str(item["zh"]),
            en=str(item["en"]),
            aliases=[str(a) for a in (item.get("aliases") or [])],
            threshold=float(item.get("threshold", 0.12)),
            min_area=float(item.get("min_area", 0.0005)),
            context_only=bool(item.get("context_only", False)),
        )
        for item in (data.get("classes") or [])
    ]
    if not classes:
        raise ValueError(f"物品词表为空: {p}")
    return ObjectCatalog(
        classes=classes,
        color_aliases={str(k): [str(x) for x in v] for k, v in (data.get("colors") or {}).items()},
        example_queries=[str(q) for q in (data.get("example_queries") or [])],
    )