"""Widgets de edición para cada tipo de parámetro."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QWidget,
)

from palantir_nodes.nodes.specs import ParamKind, ParamSpec

_BIG = 1_000_000_000
_SLIDER_STEPS = 1000


class ValueWidget(QWidget):
    """Base: emite ``value_changed`` solo ante cambios del usuario."""

    value_changed = Signal(object)

    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(parent)
        self.spec = spec
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)

    def set_value(self, value: Any) -> None:
        self.blockSignals(True)
        try:
            self._set(value)
        finally:
            self.blockSignals(False)

    def _set(self, value: Any) -> None:
        raise NotImplementedError


def _range(spec: ParamSpec) -> tuple[float, float]:
    low = spec.minimum if spec.minimum is not None else -_BIG
    high = spec.maximum if spec.maximum is not None else _BIG
    return low, high


class _NoWheelMixin:
    """Ignora la rueda si el campo no tiene el foco (evita cambios al desplazar el panel)."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _SpinBox(_NoWheelMixin, QSpinBox):
    pass


class _DoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    pass


class _ComboBox(_NoWheelMixin, QComboBox):
    pass


class IntWidget(ValueWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        low, high = _range(spec)
        self.spin = _SpinBox()
        self.spin.setRange(int(low), int(high))
        self.spin.setSingleStep(int(spec.step or 1))
        self.spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider = None
        if spec.slider and spec.minimum is not None and spec.maximum is not None:
            self.slider = QSlider(Qt.Orientation.Horizontal)
            self.slider.setRange(int(low), int(high))
            self.slider.setSingleStep(int(spec.step or 1))
            self._layout.addWidget(self.slider, 1)
            self.slider.valueChanged.connect(self._from_slider)
        self._layout.addWidget(self.spin)
        self.spin.valueChanged.connect(self._from_spin)

    def _from_spin(self, value: int) -> None:
        if self.slider is not None:
            self.slider.blockSignals(True)
            self.slider.setValue(value)
            self.slider.blockSignals(False)
        self.value_changed.emit(value)

    def _from_slider(self, value: int) -> None:
        self.spin.setValue(value)

    def _set(self, value: Any) -> None:
        for w in (self.spin, self.slider):
            if w is not None:
                w.blockSignals(True)
                w.setValue(int(value))
                w.blockSignals(False)


class FloatWidget(ValueWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        low, high = _range(spec)
        self.spin = _DoubleSpinBox()
        self.spin.setDecimals(spec.decimals)
        self.spin.setRange(low, high)
        self.spin.setSingleStep(spec.step or (0.1 if high - low <= 10 else 1.0))
        self.spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider = None
        self._low, self._high = low, high
        if spec.slider and spec.minimum is not None and spec.maximum is not None:
            self.slider = QSlider(Qt.Orientation.Horizontal)
            self.slider.setRange(0, _SLIDER_STEPS)
            self._layout.addWidget(self.slider, 1)
            self.slider.valueChanged.connect(self._from_slider)
        self._layout.addWidget(self.spin)
        self.spin.valueChanged.connect(self._from_spin)

    def _to_slider(self, value: float) -> int:
        return round((value - self._low) / (self._high - self._low) * _SLIDER_STEPS)

    def _from_spin(self, value: float) -> None:
        if self.slider is not None:
            self.slider.blockSignals(True)
            self.slider.setValue(self._to_slider(value))
            self.slider.blockSignals(False)
        self.value_changed.emit(value)

    def _from_slider(self, position: int) -> None:
        self.spin.setValue(self._low + (self._high - self._low) * position / _SLIDER_STEPS)

    def _set(self, value: Any) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(float(value))
        self.spin.blockSignals(False)
        if self.slider is not None:
            self.slider.blockSignals(True)
            self.slider.setValue(self._to_slider(float(value)))
            self.slider.blockSignals(False)


class BoolWidget(ValueWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        self.check = QCheckBox()
        self._layout.addWidget(self.check)
        self._layout.addStretch(1)
        self.check.toggled.connect(self.value_changed.emit)

    def _set(self, value: Any) -> None:
        self.check.blockSignals(True)
        self.check.setChecked(bool(value))
        self.check.blockSignals(False)


class EnumWidget(ValueWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        self.combo = _ComboBox()
        self.combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for value, label in spec.options:
            self.combo.addItem(label, value)
        self._layout.addWidget(self.combo, 1)
        self.combo.currentIndexChanged.connect(
            lambda i: self.value_changed.emit(self.combo.itemData(i))
        )

    def _set(self, value: Any) -> None:
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(max(0, self.combo.findData(value)))
        self.combo.blockSignals(False)


class StringWidget(ValueWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        self.edit = QLineEdit()
        self._layout.addWidget(self.edit, 1)
        self.edit.editingFinished.connect(lambda: self.value_changed.emit(self.edit.text()))

    def _set(self, value: Any) -> None:
        self.edit.blockSignals(True)
        self.edit.setText(str(value))
        self.edit.blockSignals(False)


class FilePathWidget(StringWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        self.edit.setPlaceholderText("Ruta de archivo…")
        browse = QToolButton()
        browse.setText("…")
        browse.setToolTip("Examinar")
        self._layout.addWidget(browse)
        browse.clicked.connect(self._browse)

    def _browse(self) -> None:
        if self.spec.save_dialog:
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar como", self.edit.text(), self.spec.file_filter
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Abrir archivo", self.edit.text(), self.spec.file_filter
            )
        if path:
            self.edit.setText(path)
            self.value_changed.emit(path)


class ColorWidget(ValueWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        self.button = QPushButton()
        self.button.setMinimumHeight(22)
        self._layout.addWidget(self.button, 1)
        self._value = (255, 255, 255)
        self.button.clicked.connect(self._pick)

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(*self._value), self, "Seleccionar color")
        if color.isValid():
            value = (color.red(), color.green(), color.blue())
            self._set(value)
            self.value_changed.emit(value)

    def _set(self, value: Any) -> None:
        self._value = tuple(value)
        hex_color = "#{:02X}{:02X}{:02X}".format(*self._value)
        text = "#000" if QColor(hex_color).lightness() > 140 else "#FFF"
        self.button.setText(hex_color)
        self.button.setStyleSheet(
            f"QPushButton {{ background: {hex_color}; color: {text}; border: 1px solid #111; }}"
        )


class VectorWidget(ValueWidget):
    def __init__(self, spec: ParamSpec, parent=None) -> None:
        super().__init__(spec, parent)
        size = 2 if spec.kind is ParamKind.VECTOR2 else 3
        low, high = _range(spec)
        self.spins = []
        for axis in "XYZ"[:size]:
            spin = _DoubleSpinBox()
            spin.setPrefix(f"{axis} ")
            spin.setDecimals(3)
            spin.setRange(low, high)
            spin.setSingleStep(spec.step or 0.1)
            spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            spin.valueChanged.connect(self._emit)
            self._layout.addWidget(spin, 1)
            self.spins.append(spin)

    def _emit(self) -> None:
        self.value_changed.emit(tuple(s.value() for s in self.spins))

    def _set(self, value: Any) -> None:
        for spin, component in zip(self.spins, value, strict=False):
            spin.blockSignals(True)
            spin.setValue(float(component))
            spin.blockSignals(False)


_WIDGETS: dict[ParamKind, type[ValueWidget]] = {
    ParamKind.INT: IntWidget,
    ParamKind.FLOAT: FloatWidget,
    ParamKind.BOOL: BoolWidget,
    ParamKind.ENUM: EnumWidget,
    ParamKind.STRING: StringWidget,
    ParamKind.FILE_PATH: FilePathWidget,
    ParamKind.COLOR: ColorWidget,
    ParamKind.VECTOR2: VectorWidget,
    ParamKind.VECTOR3: VectorWidget,
}


def create_value_widget(spec: ParamSpec, value: Any, parent=None) -> ValueWidget:
    widget = _WIDGETS[spec.kind](spec, parent)
    widget.set_value(value)
    return widget
