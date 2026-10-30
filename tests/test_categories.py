from pdxhackerspace_potluck.categories import (
    DEFAULT_CATEGORIES,
    category_id,
    load_categories,
)


def test_defaults_when_unset_or_blank() -> None:
    assert load_categories(None) == DEFAULT_CATEGORIES
    assert load_categories(" , ") == DEFAULT_CATEGORIES


def test_category_id_slugifies() -> None:
    assert category_id("Main Dishes!") == "main-dishes"
    assert category_id("!!!") == "other"


def test_custom_labels_get_unique_ids_and_cycled_colors() -> None:
    cats = load_categories("Sides, Sides, " + ", ".join(f"C{i}" for i in range(8)))
    assert [c.id for c in cats[:3]] == ["sides", "sides-2", "c0"]
    assert cats[0].color == DEFAULT_CATEGORIES[0].color
    assert cats[7].color == DEFAULT_CATEGORIES[0].color  # wrapped around


def test_long_labels_are_truncated() -> None:
    assert len(load_categories("x" * 100)[0].label) == 40
