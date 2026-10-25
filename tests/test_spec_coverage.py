"""La biblioteca de nodos cubre la lista de la sección 5 de la especificación original."""

import pytest

from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.registry import load_builtin_nodes

# Etiqueta que usa la especificación -> etiqueta del nodo registrado (si difiere).
SPEC_NODES = {
    "Entradas": [
        "Load Image",
        "Load Video",
        "Webcam",
        "Number",
        "Boolean",
        "Color",
    ],
    "Procesamiento de imágenes": [
        "Grayscale",
        "Gaussian Blur",
        "Median Blur",
        "Threshold",
        "Adaptive Threshold",
        "Canny Edge Detection",
        "Resize",
        "Crop",
        "Rotate",
        "Flip",
        "HSV Conversion",
        "Color Range (InRange)",  # "Color Range / InRange"
        "Erode",
        "Dilate",
        "Morphological Operations",
        "Find Contours",
        "Draw Contours",
    ],
    "Matemáticas": [
        "Add",
        "Subtract",
        "Multiply",
        "Divide",
        "Clamp",
        "Map Range",
        "Minimum",
        "Maximum",
        "Compare",
    ],
    "Composición": [
        "Blend Images",
        "Add Weighted",
        "Bitwise AND",
        "Bitwise OR",
        "Bitwise NOT",
        "Mask",
        "Merge Channels",
        "Split Channels",
    ],
    "Salidas": ["Image Viewer", "Video Viewer", "Save Image", "Save Video"],
}

CATEGORY_OF_SECTION = {
    "Entradas": "Entradas",
    "Procesamiento de imágenes": "Imagen",
    "Matemáticas": "Matemáticas",
    "Composición": "Composición",
    "Salidas": "Salidas",
}

ALL = [(section, label) for section, labels in SPEC_NODES.items() for label in labels]


@pytest.fixture(scope="module")
def by_label():
    return {cls.label: cls for cls in load_builtin_nodes()}


def test_spec_lists_44_nodes():
    assert len(ALL) == 44


@pytest.mark.parametrize("section,label", ALL, ids=[f"{s[:4]}-{n}" for s, n in ALL])
def test_every_spec_node_is_registered_and_complete(by_label, section, label):
    cls = by_label.get(label)
    assert cls is not None, f"Falta el nodo '{label}' de la especificación"
    assert cls.category == CATEGORY_OF_SECTION[section]
    assert cls.is_implemented(), f"'{label}' no tiene procesamiento"
    assert cls.generate_code is not NodeDefinition.generate_code, f"'{label}' no se exporta"
    assert cls.outputs or cls.inputs  # tiene sockets (es utilizable en un grafo)


def test_sources_are_flagged_for_realtime(by_label):
    assert by_label["Load Video"].is_source and by_label["Webcam"].is_source
    assert not by_label["Load Image"].is_source


def test_only_known_extras_beyond_the_spec(by_label):
    spec = {label for labels in SPEC_NODES.values() for label in labels}
    assert set(by_label) - spec == {
        "Integer",
        "Vector2",
        "Vector3",
        "Slider",
        "Tick",
        "Sine",
        "Cosine",
        "Convert Color Space",
        "RGB to HSV",
        "HSV to RGB",
        "Number to String",
        "String to Number",
        "Integer to Float",
        "Float to Integer",
        "String Viewer",
        "Value to JSON",
        "JSON Value",
    }
