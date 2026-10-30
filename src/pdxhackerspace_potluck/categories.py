"""Dish categories: the built-in set, or labels from POTLUCK_CATEGORIES."""

import re
from dataclasses import dataclass

MAX_LABEL_LENGTH = 40


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    emoji: str
    color: str


FALLBACK = Category(id="other", label="Other", emoji="\U0001f37d", color="#8a7d6b")

DEFAULT_CATEGORIES = (
    Category("meat", "Meat", "\U0001f356", "#b5462f"),
    Category("vegetables", "Vegetables", "\U0001f957", "#5a8a4a"),
    Category("carbs", "Carbs", "\U0001f35e", "#c2913c"),
    Category("appetizers", "Appetizers", "\U0001f968", "#d27d3a"),
    Category("desserts", "Desserts", "\U0001f370", "#c96d8f"),
    Category("drinks", "Drinks", "\U0001f964", "#5b8aa6"),
    FALLBACK,
)

_COLORS = tuple(c.color for c in DEFAULT_CATEGORIES)


def category_id(label: str) -> str:
    """Turn a configured category label into a stable form value."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "other"


def load_categories(value: str | None) -> tuple[Category, ...]:
    """Parse a comma-separated list of labels; empty means the defaults."""
    labels = [part.strip() for part in (value or "").split(",") if part.strip()]
    if not labels:
        return DEFAULT_CATEGORIES

    categories: list[Category] = []
    seen: set[str] = set()
    for index, label in enumerate(labels):
        base_id = category_id(label)
        cat_id = base_id
        suffix = 2
        while cat_id in seen:
            cat_id = f"{base_id}-{suffix}"
            suffix += 1
        seen.add(cat_id)
        categories.append(
            Category(
                id=cat_id,
                label=label[:MAX_LABEL_LENGTH],
                emoji=FALLBACK.emoji,
                color=_COLORS[index % len(_COLORS)],
            )
        )
    return tuple(categories)
