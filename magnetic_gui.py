import os
from datetime import datetime

import numpy as np
import serial
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QHBoxLayout, QStackedLayout
)
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtCore import QTimer, QRect, Qt, QPoint
from PyQt6.QtGui import QPainter, QColor, QImage

from config import (
    MAX_SIZE, COM_PORT, BAUD_RATE, PRINT_ADC_MT_IN_TERMINAL,
    GRID_ROWS, GRID_COLS, SCAN_MODE_DURATION, SCAN_TIMING_INTERVAL,
    DEMO_MODE, ADC_QUIESCENT, ADC_MAX, ADC_MIN, MT_MIN, MT_MAX
)
from heatmap_widget import HeatmapWidget
from algorithm_overlay import AlgorithmPanel
from subtraction_widget import SubtractionWidget


class MagneticGUI(QWidget):
    def __init__(self, port=COM_PORT, baudrate=BAUD_RATE):
        super().__init__()

        self.setWindowTitle("Magnetic Tile Viewer")
        self.resize(1200, 700)

        self.scan_blocks = []

        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: white; font-size: 14px; }
            QPushButton {
                background-color: #2d2d2d;
                padding: 6px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
        """)

        # ----- Serial -----
        if DEMO_MODE:
            self.ser = None
        else:
            try:
                self.ser = serial.Serial(port, baudrate, timeout=0.1)
            except serial.SerialException:
                self.ser = None

        # ----- Data Storage -----
        self.data = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibration = np.zeros((MAX_SIZE, MAX_SIZE))
        self.current_row = 0

        # ----- Calibration Control -----
        self.calibrating = False
        self.calibration_count = 0
        self.max_calibration_frames = 100

        # ----- Scan Mode ------
        self.auto_scan = False
        self.scan_interval_ms = SCAN_TIMING_INTERVAL
        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self.save_scan)
        self.scan_count = 0
        self.max_scan_duration_sec = SCAN_MODE_DURATION
        self.scan_elapsed_timer = QTimer()
        self.scan_elapsed_timer.timeout.connect(self.update_elapsed_time)
        self.scan_elapsed_sec = 0

        # ----- Root layout: stacked (live view vs subtraction view) -----
        self.stack = QStackedLayout()
        root_widget = QWidget()
        root_widget.setLayout(self.stack)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root_widget)

        # ---- Page 0: Live view ----
        live_page = QWidget()
        live_layout = QHBoxLayout(live_page)
        live_layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel("Live")

        # Heatmap
        self.heatmap = HeatmapWidget()
        live_layout.addWidget(self.heatmap, stretch=5)

        # Control panel
        control_panel = QVBoxLayout()
        live_layout.addLayout(control_panel, stretch=1)

        # Stepper Arm Buttons
        self.motion_control_button = QPushButton("Motion Control")
        self.motion_control_button.clicked.connect(self.motion_control)
        control_panel.addWidget(self.motion_control_button)

        self.HOME_button = QPushButton("HOME")
        self.HOME_button.clicked.connect(self.HOME_execute)
        control_panel.addWidget(self.HOME_button)
        self.HOME_button.hide()

        self.A8_button = QPushButton("A8")
        self.A8_button.clicked.connect(self.A8_motion)
        control_panel.addWidget(self.A8_button)
        self.A8_button.hide()

        self.STOP_button = QPushButton("STOP")
        self.STOP_button.clicked.connect(self.motion_STOP)
        control_panel.addWidget(self.STOP_button)
        self.STOP_button.hide()

        self.LIVE_button = QPushButton("LIVE")
        self.LIVE_button.clicked.connect(self.LIVE_mode)
        control_panel.addWidget(self.LIVE_button)
        self.LIVE_button.hide()

        # Export Buttons
        self.png_button = QPushButton("Export PNG")
        self.png_button.clicked.connect(self.export_png)
        control_panel.addWidget(self.png_button)

        self.svg_button = QPushButton("Export SVG")
        self.svg_button.clicked.connect(self.export_svg)
        control_panel.addWidget(self.svg_button)

        self.csv_button = QPushButton("Export CSV")
        self.csv_button.clicked.connect(self.export_csv)
        control_panel.addWidget(self.csv_button)

        # Scan Button
        self.scan_button = QPushButton("Start Auto Scan")
        self.scan_button.clicked.connect(self.toggle_auto_scan)
        control_panel.addWidget(self.scan_button)

        # Algorithm Button
        self.algo_button = QPushButton("Algorithms")
        self.algo_button.clicked.connect(self.toggle_algorithm_panel)
        control_panel.addWidget(self.algo_button)

        # Subtraction Mode Button
        self.subtract_button = QPushButton("Subtraction Mode")
        self.subtract_button.clicked.connect(self.enter_subtraction_mode)
        control_panel.addWidget(self.subtract_button)

        # Scan labels
        self.counter_label = QLabel("Scans: 0")
        self.counter_label.setFixedHeight(40)
        self.counter_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.counter_label.hide()
        control_panel.addWidget(self.counter_label)

        self.time_label = QLabel("Time: 0 s")
        self.time_label.setFixedHeight(40)
        self.time_label.setStyleSheet("font-size: 20px;")
        self.time_label.hide()
        control_panel.addWidget(self.time_label)

        self.stack.addWidget(live_page)   # index 0

        # ---- Page 1: Subtraction view ----
        self.subtraction_widget = SubtractionWidget(on_back=self.exit_subtraction_mode, on_send_cmd=self.send_cmd)
        self.stack.addWidget(self.subtraction_widget)   # index 1

        # ----- Floating Algorithm Panel -----
        self.algo_panel = AlgorithmPanel(self)
        self.algo_panel.algorithms_changed.connect(self.heatmap.set_active_algorithms)
        self.algo_panel.hide()

        # ----- Timer -----
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial)
        self.timer.start(10)

    # ------------------------------------------------------------------ #
    #  Subtraction Mode                                                    #
    # ------------------------------------------------------------------ #

    def enter_subtraction_mode(self):
        self.algo_panel.hide()
        self.stack.setCurrentIndex(1)

    def exit_subtraction_mode(self):
        self.stack.setCurrentIndex(0)

    # ------------------------------------------------------------------ #
    #  Algorithm Panel                                                     #
    # ------------------------------------------------------------------ #

    def toggle_algorithm_panel(self):
        if self.algo_panel.isVisible():
            self.algo_panel.hide()
        else:
            self._position_algo_panel()
            self.algo_panel.show()
            self.algo_panel.raise_()

    def _position_algo_panel(self):
        heatmap_pos = self.heatmap.mapTo(self, QPoint(0, 0))
        self.algo_panel.move(heatmap_pos.x() + 10, heatmap_pos.y() + 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.algo_panel.isVisible():
            self._position_algo_panel()

    # ------------------------------------------------------------------ #
    #  Motion / Command Helpers                                            #
    # ------------------------------------------------------------------ #

    def send_cmd(self, cmd):
        if self.ser:
            self.ser.write((cmd + "\n").encode())

    def motion_control(self):
        self.HOME_button.show()
        self.STOP_button.show()
        self.LIVE_button.show()
        self.A8_button.show()

        self.png_button.hide()
        self.csv_button.hide()
        self.svg_button.hide()
        self.scan_button.hide()
        self.algo_button.hide()
        self.subtract_button.hide()

        self.motion_control_button.setText("Back")

        try:
            self.motion_control_button.clicked.disconnect()
        except TypeError:
            pass

        self.motion_control_button.clicked.connect(self.back_to_main)

    def HOME_execute(self):
        self.send_cmd("HOME")

    def LIVE_mode(self):
        self.send_cmd("L")

    def motion_STOP(self):
        self.send_cmd("S")

    def A8_motion(self):
        self.send_cmd("A8")

    def back_to_main(self):
        self.motion_control_button.setText("Motion Control")
        self.png_button.show()
        self.csv_button.show()
        self.svg_button.show()
        self.scan_button.show()
        self.algo_button.show()
        self.subtract_button.show()
        self.HOME_button.hide()
        self.STOP_button.hide()
        self.LIVE_button.hide()
        self.A8_button.hide()

        try:
            self.motion_control_button.clicked.disconnect()
        except TypeError:
            pass

        self.motion_control_button.clicked.connect(self.motion_control)

    # ------------------------------------------------------------------ #
    #  Scan Functionality                                                  #
    # ------------------------------------------------------------------ #

    def toggle_auto_scan(self):
        if not self.auto_scan:
            self.auto_scan = True
            self.scan_blocks = []
            self.scan_count = 0
            self.scan_elapsed_sec = 0

            self.send_cmd("A8")

            self.counter_label.setText("Scans: 0")
            self.time_label.setText("Time: 0 s")
            self.counter_label.show()
            self.time_label.show()

            self.session_folder = datetime.now().strftime("session_%Y-%m-%d_%H-%M-%S")
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

        self.send_cmd("L")

        self.counter_label.hide()
        self.time_label.hide()
        self.scan_button.setText("Start Auto Scan")
        self.label.setText("Live")

        if len(self.scan_blocks) > 0:
            surface = self.build_full_surface(GRID_ROWS, GRID_COLS)
            self.render_full_surface(surface)
            print("Full surface reconstruction saved.")

    def update_elapsed_time(self):
        self.scan_elapsed_sec += 1
        self.time_label.setText(f"Time: {self.scan_elapsed_sec} s")

        if self.scan_elapsed_sec >= self.max_scan_duration_sec:
            print("Auto scan finished (time limit reached)")
            self.stop_auto_scan()

    def generate_snake_positions(self, rows, cols):
        positions = []
        for r in range(rows):
            row_positions = [(r, c) for c in range(cols)]
            if r % 2 == 0:
                row_positions.reverse()
            positions.extend(row_positions)
        return positions

    def save_scan(self):
        adc = self.data.copy()
        if not self.calibrating and np.any(self.calibration):
            adc -= self.calibration

        mapped = self.map_to_millitesla(adc)
        self.scan_blocks.append(mapped.copy())

        surface = self.build_full_surface(GRID_ROWS, GRID_COLS)
        self.render_full_surface(surface)

        self.scan_count += 1
        self.counter_label.setText(f"Scans: {self.scan_count}")

    def build_full_surface(self, grid_rows, grid_cols):
        block_size = MAX_SIZE
        full_rows = grid_rows * block_size
        full_cols = grid_cols * block_size
        full_surface = np.full((full_rows, full_cols), np.nan)

        positions = self.generate_snake_positions(grid_rows, grid_cols)

        for idx, block in enumerate(self.scan_blocks):
            if idx >= len(positions):
                break
            grid_r, grid_c = positions[idx]
            start_r = grid_r * block_size
            start_c = grid_c * block_size
            full_surface[start_r:start_r + block_size,
                         start_c:start_c + block_size] = block
        return full_surface

    def render_full_surface(self, surface):
        rgb_image = np.zeros((*surface.shape, 3), dtype=np.uint8)
        for i in range(surface.shape[0]):
            for j in range(surface.shape[1]):
                value = surface[i, j]
                if np.isnan(value):
                    rgb_image[i, j] = [0, 0, 0]
                    continue

                clamped = max(min(value, MT_MAX), MT_MIN)
                ratio = (clamped - MT_MIN) / (MT_MAX - MT_MIN)
                hue = int((1 - ratio) * 240)
                color = QColor.fromHsv(hue, 255, 255)
                rgb_image[i, j] = [color.red(), color.green(), color.blue()]

        h, w, _ = rgb_image.shape
        image = QImage(rgb_image.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        scaled = image.scaled(
            w * 10,
            h * 10,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        scaled.save(os.path.join(self.session_folder, "FULL_SURFACE.png"))

    # ------------------------------------------------------------------ #
    #  Exports                                                             #
    # ------------------------------------------------------------------ #

    def export_png(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save PNG", "", "PNG Files (*.png)"
        )
        if filename:
            pixmap = self.grab()
            pixmap.save(filename)

    def export_svg(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save SVG", "", "SVG Files (*.svg)"
        )
        if filename:
            generator = QSvgGenerator()
            generator.setFileName(filename)
            generator.setSize(self.size())
            generator.setViewBox(QRect(0, 0, self.width(), self.height()))
            generator.setTitle("Magnetic Field Map")
            generator.setDescription("Generated by MagneticUI")
            painter = QPainter(generator)
            self.render(painter)
            painter.end()

    def export_csv(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "", "CSV Files (*.csv)"
        )
        if filename:
            adc = self.data.copy()
            if not self.calibrating and np.any(self.calibration):
                adc -= self.calibration

            mapped = self.map_to_millitesla(adc)
            combined = np.vstack((
                adc,
                np.full((1, MAX_SIZE), np.nan),
                mapped
            ))
            np.savetxt(filename, combined, delimiter=",", fmt="%.2f")

    # ------------------------------------------------------------------ #
    #  Serial Processing                                                   #
    # ------------------------------------------------------------------ #

    def read_serial(self):
        if DEMO_MODE:
            values = self.generate_demo_frame()
            line = ",".join(map(str, values.flatten()))
            self.process_frame(line)
            return

        if not self.ser:
            return

        if self.ser.in_waiting:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line and not any(line.startswith(s) for s in ["Ready", "Live", "FPS"]):
                self.process_frame(line)

    def generate_demo_frame(self):
        x = np.linspace(0, 3 * np.pi, MAX_SIZE)
        y = np.linspace(0, 3 * np.pi, MAX_SIZE)
        xv, yv = np.meshgrid(x, y)
        t = datetime.now().timestamp()
        wave = np.sin(xv + t * 0.5) + np.cos(yv + t * 0.3)
        normalized = (wave - wave.min()) / (wave.max() - wave.min())
        adc = ADC_QUIESCENT + (normalized - 0.5) * 40000
        noise = np.random.normal(0, 200, (MAX_SIZE, MAX_SIZE))
        return np.clip(adc + noise, 0, ADC_MAX).astype(int)

    def process_frame(self, line):
        parts = line.split(",")
        if len(parts) != 64:
            return

        try:
            values = np.array(list(map(float, parts)), dtype=np.float32)
        except ValueError:
            return

        values -= ADC_QUIESCENT
        self.data = values.reshape((MAX_SIZE, MAX_SIZE))

        if self.calibrating:
            self.calibration += self.data

        if PRINT_ADC_MT_IN_TERMINAL:
            mapped = self.map_to_millitesla(values)
            print("ADC (offset):", *np.round(values, 0))
            print("mT:", *np.round(mapped, 2))

        self.frame_complete()

    def frame_complete(self):
        if self.calibrating:
            self.calibration_count += 1
            if self.calibration_count >= self.max_calibration_frames:
                self.finish_calibration()

        mt = self.map_to_millitesla(self.data)
        self.heatmap.update_data(self.data, self.calibration, self.calibrating)

        # Feed subtraction widget if it's active
        if self.stack.currentIndex() == 1:
            adc = self.data.copy()
            if not self.calibrating and np.any(self.calibration):
                adc -= self.calibration
            self.subtraction_widget.update_current(self.map_to_millitesla(adc))

    # ------------------------------------------------------------------ #
    #  Calibration                                                         #
    # ------------------------------------------------------------------ #

    def start_calibration(self):
        self.calibration[:] = 0
        self.calibration_count = 0
        self.calibrating = True
        self.label.setText("Calibrating...")

    def finish_calibration(self):
        self.calibration /= self.max_calibration_frames
        self.calibrating = False
        self.label.setText("Calibrated")

    # ------------------------------------------------------------------ #
    #  Utilities                                                           #
    # ------------------------------------------------------------------ #

    def map_to_millitesla(self, adc_values):
        adc_values = np.clip(adc_values, ADC_MIN, ADC_MAX)
        ratio = (adc_values - ADC_MIN) / (ADC_MAX - ADC_MIN)
        return ratio * (MT_MAX - MT_MIN) + MT_MIN

    def classify_field(self, avg):
        if abs(avg) < 10:
            return "LOW"
        elif abs(avg) < 30:
            return "MEDIUM"
        else:
            return "HIGH"