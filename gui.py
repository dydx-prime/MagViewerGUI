# gui.py

import os
from datetime import datetime
import numpy as np
import serial

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QHBoxLayout
)
from PyQt6.QtCore import QTimer, QRect, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgGenerator

from config import *
from heatmap_widget import HeatmapWidget
from mapper import map_to_millitesla
from surface import build_full_surface


class MagneticGUI(QWidget):
    def __init__(self, port=COM_PORT, baudrate=BAUD_RATE):
        super().__init__()

        self.setWindowTitle("Magnetic Tile Viewer")
        self.resize(1000, 600)

        # ---------------- Theme ----------------
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: white; font-size: 14px; }
            QPushButton {
                background-color: #2d2d2d;
                padding: 6px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
        """)

        # ---------------- Serial ----------------
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
        except serial.SerialException:
            self.ser = None

        # ---------------- Data ----------------
        self.data = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibration = np.zeros((MAX_SIZE, MAX_SIZE))

        self.calibrating = False
        self.calibration_count = 0
        self.max_calibration_frames = 100

        # ---------------- Scan ----------------
        self.auto_scan = False
        self.scan_blocks = []
        self.scan_count = 0
        self.scan_elapsed_sec = 0
        self.scan_interval_ms = 4000
        self.max_scan_duration_sec = 60

        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self.save_scan)

        self.scan_elapsed_timer = QTimer()
        self.scan_elapsed_timer.timeout.connect(self.update_elapsed_time)

        # ---------------- UI Layout ----------------
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # Heatmap
        self.heatmap = HeatmapWidget()
        main_layout.addWidget(self.heatmap, stretch=5)

        # Control Panel
        control_panel = QVBoxLayout()
        main_layout.addLayout(control_panel, stretch=1)

        self.label = QLabel("Live")
        self.label.setFixedHeight(25)
        self.label.setStyleSheet("font-size: 20px; font-weight: bold;")
        control_panel.addWidget(self.label)

        # Calibration
        self.calib_button = QPushButton("Calibrate")
        self.calib_button.clicked.connect(self.start_calibration)
        control_panel.addWidget(self.calib_button)

        # Export buttons
        self.png_button = QPushButton("Export PNG")
        self.png_button.clicked.connect(self.export_png)
        control_panel.addWidget(self.png_button)

        self.svg_button = QPushButton("Export SVG")
        self.svg_button.clicked.connect(self.export_svg)
        control_panel.addWidget(self.svg_button)

        self.csv_button = QPushButton("Export CSV")
        self.csv_button.clicked.connect(self.export_csv)
        control_panel.addWidget(self.csv_button)

        # Auto Scan
        self.scan_button = QPushButton("Start Auto Scan")
        self.scan_button.clicked.connect(self.toggle_auto_scan)
        control_panel.addWidget(self.scan_button)

        # Scan counters
        self.counter_label = QLabel("Scans: 0")

        self.counter_label.setFixedHeight(40)
        self.counter_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.counter_label.hide()
        control_panel.addWidget(self.counter_label)

        self.time_label = QLabel("Time: 0 s")
        self.time_label.setFixedHeight(40)
        self.time_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.time_label.hide()
        control_panel.addWidget(self.time_label)

        # ---------------- Serial Timer ----------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial)
        self.timer.start(1)

    # ====================================================
    # SERIAL
    # ====================================================

    def read_serial(self):
        if not self.ser:
            return

        if self.ser.in_waiting:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line:
                self.process_frame(line)

    def process_frame(self, line):
        parts = line.split(",")

        if len(parts) != MAX_SIZE * MAX_SIZE:
            return

        try:
            values = np.array(list(map(int, parts)))
        except ValueError:
            return

        self.data = values.reshape((MAX_SIZE, MAX_SIZE))

        if self.calibrating:
            self.calibration += self.data

        self.frame_complete()

    def frame_complete(self):
        if self.calibrating:
            self.calibration_count += 1
            if self.calibration_count >= self.max_calibration_frames:
                self.finish_calibration()

        self.heatmap.update_data(
            self.data,
            self.calibration,
            self.calibrating
        )

    # ====================================================
    # CALIBRATION
    # ====================================================

    def start_calibration(self):
        self.calibration[:] = 0
        self.calibration_count = 0
        self.calibrating = True
        self.label.setText("Calibrating...")

    def finish_calibration(self):
        self.calibration /= self.max_calibration_frames
        self.calibrating = False
        self.label.setText("Calibrated")

    # ====================================================
    # AUTO SCAN
    # ====================================================

    def toggle_auto_scan(self):
        if not self.auto_scan:
            self.auto_scan = True
            self.scan_blocks = []
            self.scan_count = 0
            self.scan_elapsed_sec = 0

            self.counter_label.show()
            self.time_label.show()

            self.session_folder = datetime.now().strftime(
                "session_%Y-%m-%d_%H-%M-%S"
            )
            os.makedirs(self.session_folder, exist_ok=True)

            self.scan_timer.start(self.scan_interval_ms)
            self.scan_elapsed_timer.start(1000)

            self.scan_button.setText("Stop Auto Scan")
            self.label.setText("Recording")
        else:
            self.stop_auto_scan()

    def stop_auto_scan(self):
        self.auto_scan = False
        self.scan_timer.stop()
        self.scan_elapsed_timer.stop()

        self.counter_label.hide()
        self.time_label.hide()
        self.scan_button.setText("Start Auto Scan")
        self.label.setText("Live")

        if self.scan_blocks:
            surface = build_full_surface(
                self.scan_blocks,
                GRID_ROWS,
                GRID_COLS
            )
            self.save_surface_image(surface)

    def save_scan(self):
        adc = self.data.astype(float)

        if not self.calibrating:
            adc -= self.calibration

        mapped = map_to_millitesla(adc)
        self.scan_blocks.append(mapped.copy())

        self.scan_count += 1
        self.counter_label.setText(f"Scans: {self.scan_count}")

    def update_elapsed_time(self):
        self.scan_elapsed_sec += 1
        self.time_label.setText(f"Time: {self.scan_elapsed_sec} s")

        if self.scan_elapsed_sec >= self.max_scan_duration_sec:
            self.stop_auto_scan()

    def save_surface_image(self, surface):
        from PyQt6.QtGui import QImage
        from mapper import value_to_color

        rows, cols = surface.shape
        rgb = np.zeros((rows, cols, 3), dtype=np.uint8)

        for r in range(rows):
            for c in range(cols):
                value = surface[r, c]
                if np.isnan(value):
                    continue

                color = value_to_color(value)
                rgb[r, c] = [color.red(), color.green(), color.blue()]

        image = QImage(
            rgb.data,
            cols,
            rows,
            3 * cols,
            QImage.Format.Format_RGB888
        )

        image = image.scaled(
            cols * 10,
            rows * 10,
            Qt.AspectRatioMode.IgnoreAspectRatio
        )

        image.save(os.path.join(self.session_folder, "FULL_SURFACE.png"))

    # ====================================================
    # EXPORTS
    # ====================================================

    def export_png(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save PNG", "", "PNG Files (*.png)"
        )
        if filename:
            self.grab().save(filename)

    def export_svg(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save SVG", "", "SVG Files (*.svg)"
        )
        if filename:
            generator = QSvgGenerator()
            generator.setFileName(filename)
            generator.setSize(self.size())
            generator.setViewBox(QRect(0, 0, self.width(), self.height()))

            painter = QPainter(generator)
            self.render(painter)
            painter.end()

    def export_csv(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "", "CSV Files (*.csv)"
        )
        if filename:
            mapped = map_to_millitesla(self.data)
            np.savetxt(filename, mapped, delimiter=",", fmt="%.2f")

