import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFileDialog
)
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QColor, QImage, QPixmap

from config import MAX_SIZE, ADC_MIN, ADC_MAX, MT_MIN, MT_MAX


def map_to_millitesla(adc_values):
    adc_values = np.clip(adc_values, ADC_MIN, ADC_MAX)
    ratio = (adc_values - ADC_MIN) / (ADC_MAX - ADC_MIN)
    return ratio * (MT_MAX - MT_MIN) + MT_MIN


def mt_to_heatmap_color(value):
    clamped = max(min(value, MT_MAX), MT_MIN)
    ratio = (clamped - MT_MIN) / (MT_MAX - MT_MIN)
    hue = int((1 - ratio) * 240)
    return QColor.fromHsv(hue, 255, 255)


def diff_to_grayscale(value, max_diff):
    """White = no change, black = max change."""
    if max_diff == 0:
        return QColor(255, 255, 255)
    intensity = int(255 * (1 - min(abs(value) / max_diff, 1.0)))
    return QColor(intensity, intensity, intensity)


class HeatmapPanel(QWidget):
    """Single heatmap panel used inside the subtraction view."""
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.title = title
        self.data = np.zeros((MAX_SIZE, MAX_SIZE))
        self.mode = "heatmap"   # "heatmap" or "diff"
        self.max_diff = 1.0
        self.setMinimumSize(200, 200)

    def set_data(self, data, mode="heatmap", max_diff=1.0):
        self.data = data
        self.mode = mode
        self.max_diff = max_diff
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        size = min(w, h - 24)   # leave room for title
        tile = size / MAX_SIZE
        ox = (w - size) / 2
        oy = 24 + (h - 24 - size) / 2

        # Title
        painter.setPen(Qt.GlobalColor.white)
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 4, w, 20), Qt.AlignmentFlag.AlignCenter, self.title)

        # Tiles
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)

        for i in range(MAX_SIZE):
            for j in range(MAX_SIZE):
                val = self.data[i][j]
                if self.mode == "diff":
                    color = diff_to_grayscale(val, self.max_diff)
                else:
                    color = mt_to_heatmap_color(val)

                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                rect = QRectF(ox + j * tile, oy + i * tile, tile, tile)
                painter.drawRect(rect)

                painter.setPen(Qt.GlobalColor.black if self.mode != "diff" else Qt.GlobalColor.gray)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{val:.1f}")


class SubtractionWidget(QWidget):
    """
    Full subtraction mode view.
    Shows: [Base] | [Current] | [Diff]
    Workflow: capture base → live current updates → save diff PNG → back to live
    """
    def __init__(self, on_back, on_send_cmd, parent=None):
        super().__init__(parent)
        self.on_back = on_back
        self.on_send_cmd = on_send_cmd

        self.base_data = None
        self.current_data = np.zeros((MAX_SIZE, MAX_SIZE))

        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: white; font-size: 13px; }
            QPushButton {
                background-color: #2d2d2d;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
            QPushButton:disabled { background-color: #222; color: #555; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- Panels row ----
        panels_row = QHBoxLayout()
        panels_row.setSpacing(8)

        self.base_panel = HeatmapPanel("Base")
        self.current_panel = HeatmapPanel("Current")
        self.diff_panel = HeatmapPanel("Difference")

        panels_row.addWidget(self.base_panel)
        panels_row.addWidget(self.current_panel)
        panels_row.addWidget(self.diff_panel)
        root.addLayout(panels_row, stretch=1)

        # ---- Status label ----
        self.status_label = QLabel("Capture a base snapshot to begin.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #aaa; font-size: 12px;")
        root.addWidget(self.status_label)

        # ---- Buttons row ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.snap_button = QPushButton("📸  Capture Base")
        self.snap_button.clicked.connect(self.capture_base)
        btn_row.addWidget(self.snap_button)

        self.save_button = QPushButton("💾  Save Diff PNG")
        self.save_button.clicked.connect(self.save_diff)
        self.save_button.setEnabled(False)
        btn_row.addWidget(self.save_button)

        self.back_button = QPushButton("↩  Back to Live")
        self.back_button.clicked.connect(self.go_back)
        btn_row.addWidget(self.back_button)

        btn_row.addStretch()

        self.home_button = QPushButton("⌂  HOME")
        self.home_button.clicked.connect(lambda: self.on_send_cmd("HOME"))
        btn_row.addWidget(self.home_button)

        self.a8_button = QPushButton("A8")
        self.a8_button.clicked.connect(lambda: self.on_send_cmd("A8"))
        btn_row.addWidget(self.a8_button)

        root.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def update_current(self, mt_data):
        """Called every frame with the latest mT data."""
        self.current_data = mt_data.copy()
        self.current_panel.set_data(self.current_data, mode="heatmap")

        if self.base_data is not None:
            diff = self.current_data - self.base_data
            max_diff = np.max(np.abs(diff))
            if max_diff == 0:
                max_diff = 1.0
            self.diff_panel.set_data(diff, mode="diff", max_diff=max_diff)

    # ------------------------------------------------------------------ #
    #  Actions                                                             #
    # ------------------------------------------------------------------ #

    def capture_base(self):
        self.base_data = self.current_data.copy()
        self.base_panel.set_data(self.base_data, mode="heatmap")
        self.save_button.setEnabled(True)
        self.status_label.setText("Base captured. Move to next position and save diff when ready.")

    def save_diff(self):
        if self.base_data is None:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Diff PNG", "diff.png", "PNG Files (*.png)"
        )
        if not filename:
            return

        diff = self.current_data - self.base_data
        max_diff = np.max(np.abs(diff))
        if max_diff == 0:
            max_diff = 1.0

        # Render all three panels into one image
        tile_px = 60
        panel_w = MAX_SIZE * tile_px
        panel_h = MAX_SIZE * tile_px + 30   # +30 for title
        total_w = panel_w * 3 + 20          # 10px gap between panels
        total_h = panel_h

        image = QImage(total_w, total_h, QImage.Format.Format_RGB888)
        image.fill(QColor(30, 30, 30))

        painter = QPainter(image)

        datasets = [
            ("Base",       self.base_data, "heatmap", max_diff),
            ("Current",    self.current_data, "heatmap", max_diff),
            ("Difference", diff, "diff", max_diff),
        ]

        for col, (title, data, mode, md) in enumerate(datasets):
            x_off = col * (panel_w + 10)

            # Title
            painter.setPen(Qt.GlobalColor.white)
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(x_off, 4, panel_w, 22),
                Qt.AlignmentFlag.AlignCenter,
                title
            )

            font.setBold(False)
            font.setPointSize(8)
            painter.setFont(font)

            for i in range(MAX_SIZE):
                for j in range(MAX_SIZE):
                    val = data[i][j]
                    if mode == "diff":
                        color = diff_to_grayscale(val, md)
                    else:
                        color = mt_to_heatmap_color(val)

                    painter.setBrush(color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    rect = QRectF(
                        x_off + j * tile_px,
                        30 + i * tile_px,
                        tile_px, tile_px
                    )
                    painter.drawRect(rect)

                    painter.setPen(Qt.GlobalColor.black if mode != "diff" else Qt.GlobalColor.gray)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{val:.1f}")

        painter.end()
        image.save(filename)
        self.status_label.setText(f"Saved: {filename}")

    def go_back(self):
        self.base_data = None
        self.save_button.setEnabled(False)
        self.status_label.setText("Capture a base snapshot to begin.")
        self.on_back()