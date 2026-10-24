from palantir_nodes.nodes.categories import all_categories
from palantir_nodes.nodes.registry import NodeRegistry, load_builtin_nodes


def test_builtin_library_loads_and_is_valid():
    registry = load_builtin_nodes()
    assert len(registry) >= 15
    known = {c.name for c in all_categories()}
    for cls in registry:
        assert cls.category in known, cls.type_id
        cls.default_params()
        cls.default_input_values()
        assert cls.is_implemented(), cls.type_id


def test_registry_search_prefers_label_prefix():
    registry = load_builtin_nodes()
    results = registry.search("gau")
    assert results[0].type_id == "image.gaussian_blur"
    assert registry.search("matem")  # por categoría


def test_registry_copy_is_independent():
    original = load_builtin_nodes()
    clone = original.copy()
    assert len(clone) == len(original)
    assert isinstance(clone, NodeRegistry)
