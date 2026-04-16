import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QColor, QLinearGradient

from config import MAX_SIZE, ADC_MIN, ADC_MAX, MT_MIN, MT_MAX


class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibration = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibrating = False

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

    def map_to_millitesla(self, adc_values):
        adc_values = np.clip(adc_values, ADC_MIN, ADC_MAX)
        ratio = (adc_values - ADC_MIN) / (ADC_MAX - ADC_MIN)
        return ratio * (MT_MAX - MT_MIN) + MT_MIN

    def update_data(self, data, calibration, calibrating):
        self.data = data
        self.calibration = calibration
        self.calibrating = calibrating
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        width = self.width()
        height = self.height()

        # Make square heatmap
        size = min(width, height)
        tile_size = size / MAX_SIZE

        offset_x = (width - size) / 2
        offset_y = (height - size) / 2

        adc = self.data.copy()

        if not self.calibrating and np.any(self.calibration):
            adc -= self.calibration

        # Convert ADC counts (relative to quiescent) to millitesla
        mt = self.map_to_millitesla(adc)

        # Tesla val text mods
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)

        for i in range(MAX_SIZE):
            for j in range(MAX_SIZE):
                value = mt[i][j]

                clamped = max(min(value, MT_MAX), MT_MIN)
                ratio = (clamped - MT_MIN) / (MT_MAX - MT_MIN)
                hue = int((1 - ratio) * 240)

                color = QColor.fromHsv(hue, 255, 255)
                painter.setBrush(color)

                rect = QRectF(
                    offset_x + j * tile_size,
                    offset_y + i * tile_size,
                    tile_size,
                    tile_size
                )

                painter.drawRect(rect)

                # Display mT value in tile
                painter.setPen(Qt.GlobalColor.black)
                painter.drawText(
                    rect,
                    Qt.AlignmentFlag.AlignCenter,
                    f"{value:.1f}"
                )

        # ---------- Gradient Legend Bar ----------
        bar_width = 30
        bar_height = size
        bar_x = offset_x + size + 40
        bar_y = offset_y

        # Create vertical gradient (top = MT_MAX, bottom = MT_MIN)
        gradient = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_height)

        for i in range(101):
            ratio = i / 100
            hue = int((ratio) * 240)
            color = QColor.fromHsv(hue, 255, 255)
            gradient.setColorAt(ratio, color)

        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.SolidLine)
        painter.drawRect(QRectF(bar_x, bar_y, bar_width, bar_height))

        # ---------- Labels ----------
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(
            QRectF(bar_x + 40, bar_y - 5, 80, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{MT_MAX:.0f} mT"
        )

        painter.drawText(
            QRectF(bar_x + 40, bar_y + bar_height - 20, 80, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{MT_MIN:.0f} mT"
        )