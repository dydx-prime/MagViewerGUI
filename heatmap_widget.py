import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import QRectF, Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QPen

from config import MAX_SIZE, ADC_MIN, ADC_MAX, MT_MIN, MT_MAX
from algorithms import ALGORITHMS


# Overlay color per algorithm (RGBA)
ALGO_COLORS = {
    "Threshold Anomaly": QColor(255, 80,  80,  160),   # red
    "Gradient Edge":     QColor(255, 200, 0,   160),   # yellow
    "Local Variance":    QColor(0,   200, 255, 160),   # cyan
    "Blob Detection":    QColor(180, 0,   255, 160),   # purple
    "Z-Score Spatial":   QColor(0,   255, 120, 160),   # green
}

# Distinct colors for individual blobs
BLOB_PALETTE = [
    QColor(255, 80,  80,  180),
    QColor(255, 160, 0,   180),
    QColor(80,  255, 80,  180),
    QColor(0,   180, 255, 180),
    QColor(200, 0,   255, 180),
    QColor(255, 255, 0,   180),
]


class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibration = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibrating = False
        self.active_algorithms = {}  # {name: param_value}

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

    def set_active_algorithms(self, active: dict):
        self.active_algorithms = active
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        width = self.width()
        height = self.height()

        size = min(width, height)
        tile_size = size / MAX_SIZE
        offset_x = (width - size) / 2
        offset_y = (height - size) / 2

        adc = self.data.copy()
        if not self.calibrating and np.any(self.calibration):
            adc -= self.calibration

        mt = self.map_to_millitesla(adc)

        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)

        # ---------- Draw Heatmap Tiles ----------
        for i in range(MAX_SIZE):
            for j in range(MAX_SIZE):
                value = mt[i][j]
                clamped = max(min(value, MT_MAX), MT_MIN)
                ratio = (clamped - MT_MIN) / (MT_MAX - MT_MIN)
                hue = int((1 - ratio) * 240)

                color = QColor.fromHsv(hue, 255, 255)
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)

                rect = QRectF(
                    offset_x + j * tile_size,
                    offset_y + i * tile_size,
                    tile_size,
                    tile_size
                )
                painter.drawRect(rect)

                painter.setPen(Qt.GlobalColor.black)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{value:.1f}")

        # ---------- Draw Algorithm Overlays ----------
        for algo_name, param in self.active_algorithms.items():
            if algo_name not in ALGORITHMS:
                continue

            fn = ALGORITHMS[algo_name][0]
            result = fn(mt, param)
            color = ALGO_COLORS.get(algo_name, QColor(255, 255, 255, 150))

            if algo_name == "Blob Detection":
                self._draw_blobs(painter, result, tile_size, offset_x, offset_y)
            else:
                self._draw_boolean_overlay(painter, result, color, tile_size, offset_x, offset_y)

        # ---------- Draw tile grid lines ----------
        pen = QPen(QColor(0, 0, 0, 60))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(MAX_SIZE):
            for j in range(MAX_SIZE):
                painter.drawRect(QRectF(
                    offset_x + j * tile_size,
                    offset_y + i * tile_size,
                    tile_size, tile_size
                ))

        # ---------- Gradient Legend Bar ----------
        bar_width = 30
        bar_height = size
        bar_x = offset_x + size + 40
        bar_y = offset_y

        gradient = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_height)
        for i in range(101):
            ratio = i / 100
            hue = int(ratio * 240)
            gradient.setColorAt(ratio, QColor.fromHsv(hue, 255, 255))

        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.SolidLine)
        painter.drawRect(QRectF(bar_x, bar_y, bar_width, bar_height))

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

    def _draw_boolean_overlay(self, painter, mask, color, tile_size, offset_x, offset_y):
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(mask.shape[0]):
            for j in range(mask.shape[1]):
                if mask[i, j]:
                    painter.drawRect(QRectF(
                        offset_x + j * tile_size,
                        offset_y + i * tile_size,
                        tile_size, tile_size
                    ))

    def _draw_blobs(self, painter, labeled, tile_size, offset_x, offset_y):
        painter.setPen(Qt.PenStyle.NoPen)
        unique_labels = np.unique(labeled)
        for label_id in unique_labels:
            if label_id == 0:
                continue
            color = BLOB_PALETTE[(label_id - 1) % len(BLOB_PALETTE)]
            painter.setBrush(color)
            positions = np.argwhere(labeled == label_id)
            for i, j in positions:
                painter.drawRect(QRectF(
                    offset_x + j * tile_size,
                    offset_y + i * tile_size,
                    tile_size, tile_size
                ))

            # Draw blob ID label at center of bounding box
            rows, cols = positions[:, 0], positions[:, 1]
            cx = offset_x + (cols.mean() + 0.5) * tile_size
            cy = offset_y + (rows.mean() + 0.5) * tile_size
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(QPointF(cx - 5, cy + 5), f"B{label_id}")
            painter.setPen(Qt.PenStyle.NoPen)