from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
    QLabel, QSlider, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from algorithms import ALGORITHMS


class AlgorithmPanel(QWidget):
    """
    Floating overlay panel for selecting and tuning detection algorithms.
    Emits `algorithms_changed` whenever the active set or params change.
    """
    algorithms_changed = pyqtSignal(dict)  # {name: param_value} for active algorithms

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            AlgorithmPanel {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 10px;
            }
            QLabel { color: white; font-size: 12px; }
            QCheckBox { color: white; font-size: 13px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #505050; }
        """)

        self.checkboxes = {}
        self.sliders = {}
        self.value_labels = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("Detection Algorithms")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        main_layout.addLayout(header)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #555;")
        main_layout.addWidget(line)

        # Algorithm rows
        for name, (fn, param_label, p_min, p_max, p_default) in ALGORITHMS.items():
            row_layout = QVBoxLayout()
            row_layout.setSpacing(2)

            cb = QCheckBox(name)
            cb.setChecked(False)
            cb.stateChanged.connect(self._emit_change)
            self.checkboxes[name] = cb
            row_layout.addWidget(cb)

            # Slider row
            slider_row = QHBoxLayout()
            slider_row.setContentsMargins(20, 0, 0, 0)

            lbl = QLabel(param_label + ":")
            lbl.setFixedWidth(110)
            slider_row.addWidget(lbl)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(int(p_min * 10))
            slider.setMaximum(int(p_max * 10))
            slider.setValue(int(p_default * 10))
            slider.setFixedWidth(120)
            slider.valueChanged.connect(self._emit_change)
            self.sliders[name] = slider
            slider_row.addWidget(slider)

            val_label = QLabel(f"{p_default:.1f}")
            val_label.setFixedWidth(30)
            self.value_labels[name] = val_label
            slider_row.addWidget(val_label)

            row_layout.addLayout(slider_row)
            main_layout.addLayout(row_layout)

        self.adjustSize()

    def _emit_change(self):
        active = {}
        for name, cb in self.checkboxes.items():
            if cb.isChecked():
                val = self.sliders[name].value() / 10.0
                self.value_labels[name].setText(f"{val:.1f}")
                active[name] = val
        self.algorithms_changed.emit(active)

    def get_active(self):
        active = {}
        for name, cb in self.checkboxes.items():
            if cb.isChecked():
                active[name] = self.sliders[name].value() / 10.0
        return active