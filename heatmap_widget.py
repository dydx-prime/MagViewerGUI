# heatmap_widget.py

import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QLinearGradient
from PyQt6.QtCore import QRectF, Qt
from mapper import map_to_millitesla, value_to_color
from config import MIN_FIELD, MAX_FIELD


class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.adc_data = None
        self.calibration = None
        self.calibrating = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def update_data(self, adc_data, calibration, calibrating):
        self.adc_data = adc_data
        self.calibration = calibration
        self.calibrating = calibrating
        self.update()

    def paintEvent(self, event):
        if self.adc_data is None:
            return

        painter = QPainter(self)

        rows, cols = self.adc_data.shape

        width = self.width()
        height = self.height()
        size = min(width, height)

        tile_size = size / max(rows, cols)
        offset_x = (width - size) / 2
        offset_y = (height - size) / 2

        adc = self.adc_data.astype(float)

        if not self.calibrating and self.calibration is not None:
            adc -= self.calibration

        mapped = map_to_millitesla(adc)

        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)

        for r in range(rows):
            for c in range(cols):
                value = mapped[r, c]
                painter.setBrush(value_to_color(value))

                rect = QRectF(
                    offset_x + c * tile_size,
                    offset_y + r * tile_size,
                    tile_size,
                    tile_size
                )

                painter.drawRect(rect)

                # auto contrast text
                painter.setPen(QColor(255, 255, 255) if value < -90 else QColor(0, 0, 0))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{value:.0f}")

        self._draw_legend(painter, offset_x, offset_y, size)

    def _draw_legend(self, painter, offset_x, offset_y, size):
        bar_width = 30
        bar_height = size
        bar_x = offset_x + size + 40
        bar_y = offset_y

        gradient = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_height)

        for i in range(101):
            ratio = i / 100
            value = MAX_FIELD - ratio * (MAX_FIELD - MIN_FIELD)
            gradient.setColorAt(ratio, value_to_color(value))

        painter.setBrush(gradient)
        painter.drawRect(QRectF(bar_x, bar_y, bar_width, bar_height))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(bar_x, bar_y, bar_width, bar_height))

        painter.drawText(
            QRectF(bar_x + 40, bar_y - 5, 60, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{MAX_FIELD}"
        )

        painter.drawText(
            QRectF(bar_x + 40, bar_y + bar_height - 20, 60, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{MIN_FIELD}"
        )