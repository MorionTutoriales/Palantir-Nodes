"""Categorías de nodos: nombre visible, color de encabezado y orden en los menús."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    name: str
    color: str
    order: int


INPUT = "Entradas"
IMAGE = "Imagen"
MATH = "Matemáticas"
COMPOSITE = "Composición"
OUTPUT = "Salidas"

_CATEGORIES: dict[str, Category] = {}

UNKNOWN_COLOR = "#555555"


def register_category(name: str, color: str, order: int = 100) -> Category:
    category = Category(name, color, order)
    _CATEGORIES[name] = category
    return category


def get_category(name: str) -> Category:
    return _CATEGORIES.get(name, Category(name, UNKNOWN_COLOR, 1000))


def all_categories() -> list[Category]:
    return sorted(_CATEGORIES.values(), key=lambda c: (c.order, c.name))


register_category(INPUT, "#8A3A4A", 0)
register_category(IMAGE, "#3B6A9C", 10)
register_category(MATH, "#2E6F6A", 20)
register_category(COMPOSITE, "#6A4A8C", 30)
register_category(OUTPUT, "#7A3B2E", 40)
