import sys # a
import os
from datetime import datetime
import numpy as np
import serial
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QSizePolicy, QHBoxLayout
)
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtCore import (
    QTimer, QRectF, QRect, Qt, QPointF
)
from PyQt6.QtGui import QPainter, QColor, QLinearGradient


# -------------------- CONFIG --------------------
MAX_SIZE = 8
MAX_VALUE = 660.0
COM_PORT = "COM8"
BAUD_RATE = 250000
PRINT_ADC_MT_IN_TERMINAL = 0;
GRID_ROWS = 4;
GRID_COLS = 4;

from PyQt6.QtWidgets import QWidget, QSizePolicy

# Heatmap Rendering
class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibration = np.zeros((MAX_SIZE, MAX_SIZE))
        self.calibrating = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

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

        # Same mapping logic
        adjusted = np.clip(adc - 50, 0, 1650)
        lower = adjusted < 600
        middle = (adjusted >= 600) & (adjusted <= 850)
        upper = adjusted > 850
        mapped = np.zeros_like(adjusted, dtype=float)
        mapped[lower] = -45 - (adjusted[lower] / 600) * 45
        mapped[middle] = -90
        mapped[upper] = -90 - ((adjusted[upper] - 850) / (1650 - 850)) * 45

        # tesla val text mods
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)

        # painter.setPen(QColor(0,0,0))
        # painter.setPen(QColor(255,255,255))

        for i in range(MAX_SIZE):
            for j in range(MAX_SIZE):

                value = mapped[i][j]

                min_val = -135
                max_val = -45
                clamped = max(min(value, max_val), min_val)
                ratio = (max_val - clamped) / (max_val - min_val)
                hue = int((1 - ratio) * 240)

                color = QColor.fromHsv(hue, 255, 255)
                painter.setBrush(color)

                painter.drawRect(
                    QRectF(
                        offset_x + j * tile_size,
                        offset_y + i * tile_size,
                        tile_size,
                        tile_size
                    )
                )

                #display tesla val in tile
                rect = QRectF(offset_x + j*tile_size,
                            offset_y + i*tile_size,
                            tile_size,
                            tile_size)
                
                painter.drawText(
                    rect,
                    Qt.AlignmentFlag.AlignCenter,
                    f"{value:.0f}"
                )
          


        # ---------- Gradient Legend Bar ----------

        bar_width = 30
        bar_height = size
        bar_x = offset_x + size + 40
        bar_y = offset_y

        # Create vertical gradient (top = -45, bottom = -135)
        gradient = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_height)

        min_val = -135
        max_val = -45

        # Add color stops using same HSV logic
        for i in range(0, 101):
            ratio = i / 100

            value = max_val - ratio * (max_val - min_val)

            clamped = max(min(value, max_val), min_val)
            hue = int((1 - ((max_val - clamped) / (max_val - min_val))) * 240)
            color = QColor.fromHsv(hue, 255, 255)

            gradient.setColorAt(ratio, color)

        painter.setBrush(gradient)
        painter.drawRect(QRectF(bar_x, bar_y, bar_width, bar_height))

        # Draw border
        painter.setBrush(Qt.BrushStyle.NoBrush)



        painter.drawRect(QRectF(bar_x, bar_y, bar_width, bar_height))

        # ---------- Labels ----------

        painter.drawText(
            QRectF(bar_x + 40, bar_y - 5, 60, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "-45"
        )

        painter.drawText(
            QRectF(bar_x + 40, bar_y + bar_height - 20, 60, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "-135"
        )
        

# Main UI + Functionality
class MagneticGUI(QWidget):
    def __init__(self, port=COM_PORT, baudrate=BAUD_RATE):
        super().__init__()

        self.setWindowTitle("Magnetic Tile Viewer")
        self.resize(1000, 600)

        # saves screen captures for final output image
        self.scan_blocks = [];

        # dark theme styling
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
        self.scan_interval_ms = 4000 # interval scans in s
        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self.save_scan)
        self.scan_count = 0
        self.max_scan_duration_sec = 60  # duration in seconds
        self.scan_elapsed_timer = QTimer()
        self.scan_elapsed_timer.timeout.connect(self.update_elapsed_time)
        self.scan_elapsed_sec = 0

        # ----- UI -----
        self.label = QLabel("Live")
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # Heatmap on left
        self.heatmap = HeatmapWidget()
        main_layout.addWidget(self.heatmap, stretch=5)

        # Control panel on right
        control_panel = QVBoxLayout()
        main_layout.addLayout(control_panel, stretch=1)

        self.calib_button = QPushButton("Calibrate")
        self.calib_button.clicked.connect(self.start_calibration)
        control_panel.addWidget(self.calib_button)


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

        # Labels for # of Scans and Time Elapsed
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


        # ----- Timer -----
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial)
        self.timer.start(1)
    
    # Scan Mode Stuff
    #-------------------------------------------------------
    def toggle_auto_scan(self):
        if not self.auto_scan:
            self.auto_scan = True

            self.scan_blocks = []

            # Reset counters
            self.scan_count = 0
            self.scan_elapsed_sec = 0
            self.counter_label.setText("Scans: 0")
            self.time_label.setText("Time: 0 s")

            self.counter_label.show()
            self.time_label.show()

            # Create session folder
            self.session_folder = datetime.now().strftime("session_%Y-%m-%d_%H-%M-%S")
            os.makedirs(self.session_folder, exist_ok=True)

            # Start timers
            self.scan_timer.start(self.scan_interval_ms)
            self.scan_elapsed_timer.start(1000)  # 1 second updates

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

        # surface building
        if len(self.scan_blocks) > 0:

            # cnc grid sizeeeeee
            grid_rows = GRID_ROWS
            grid_cols = GRID_COLS

            surface = self.build_full_surface(grid_rows, grid_cols)
            self.render_full_surface(surface)

            print("Full surface reconstruction saved.")

    def update_elapsed_time(self):
        self.scan_elapsed_sec += 1
        self.time_label.setText(f"Time: {self.scan_elapsed_sec} s")

        if self.scan_elapsed_sec >= self.max_scan_duration_sec:
            print("Auto scan finished (time limit reached)")
            self.stop_auto_scan()

    def generate_snail_positions(self, rows, cols):
        positions = []
        left = 0
        right = cols - 1
        bottom = rows - 1
        top = 0

        while left <= right and top <= bottom:

            for r in range(bottom, top-1, -1):
                positions.append((r, left))
            left += 1

            for c in range(left, right+1):
                positions.append((top, c))
            top += 1

            if left <= right:
                for r in range(top, bottom+1):
                    positions.append((r, right))
                right -= 1

            if top <= bottom:
                for c in range(right, left-1, -1):
                    positions.append((bottom, c))
                bottom -= 1

        return positions


    def save_scan(self):

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # saving each png individually
        #png_path = os.path.join(self.session_folder, f"{timestamp}.png")
        #pixmap = self.heatmap.grab()
        #pixmap.save(png_path)

        adc = self.data.copy()

        if not self.calibrating and np.any(self.calibration):
            adc -= self.calibration

        mapped = self.map_to_millitesla(adc)
        self.scan_blocks.append(mapped.copy())

        surface = self.build_full_surface(GRID_ROWS, GRID_COLS)
        self.render_full_surface(surface)

        # Stack raw + blank line + mapped
        # combined = np.vstack((
        #     adc,
        #     np.full((1, MAX_SIZE), np.nan),
        #     mapped
        # ))

        # csv_path = os.path.join(self.session_folder, f"{timestamp}.csv")
        # np.savetxt(csv_path, combined, delimiter=",", fmt="%.2f")

        # print(f"Saved PNG + CSV @ {timestamp}")

        self.scan_count += 1
        self.counter_label.setText(f"Scans: {self.scan_count}")


    # def save_scan(self):

    #     timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    #     # png
    #     png_path = os.path.join(self.session_folder, f"{timestamp}.png")
    #     pixmap = self.grab()
    #     pixmap.save(png_path)

    #     # csv
    #     adc = self.data.copy()

    #     if not self.calibrating and np.any(self.calibration):
    #         adc -= self.calibration

    #     mapped = self.map_to_millitesla(adc)

    #     # Stack raw + blank line + mapped
    #     combined = np.vstack((
    #         adc,
    #         np.full((1, MAX_SIZE), np.nan),
    #         mapped
    #     ))

    #     csv_path = os.path.join(self.session_folder, f"{timestamp}.csv")
    #     np.savetxt(csv_path, combined, delimiter=",", fmt="%.2f")

    #     print(f"Saved PNG + CSV @ {timestamp}")

    #     self.scan_count += 1
    #     self.counter_label.setText(f"Scans: {self.scan_count}")


    def build_full_surface(self, grid_rows, grid_cols):

        block_size = MAX_SIZE  # 8

        full_rows = grid_rows * block_size
        full_cols = grid_cols * block_size

        full_surface = np.full((full_rows, full_cols), np.nan)

        positions = self.generate_snail_positions(grid_rows, grid_cols)

        for idx, block in enumerate(self.scan_blocks):

            if idx >= len(positions):
                break

            grid_r, grid_c = positions[idx]

            start_r = grid_r * block_size
            start_c = grid_c * block_size

            full_surface[start_r:start_r+block_size,
                        start_c:start_c+block_size] = block

        return full_surface
    

    def render_full_surface(self, surface):

        min_val = -135
        max_val = -45

        normalized = (max_val - surface) / (max_val - min_val)
        normalized = np.clip(normalized, 0, 1)

        hue = (1 - normalized) * 240

        rgb_image = np.zeros((*surface.shape, 3), dtype=np.uint8)

        for i in range(surface.shape[0]):
            for j in range(surface.shape[1]):

                value = surface[i, j]

                if np.isnan(value):
                    rgb_image[i, j] = [0, 0, 0]   # black for unscanned
                    continue

                clamped = max(min(value, max_val), min_val)
                ratio = (max_val - clamped) / (max_val - min_val)
                hue = int((1 - ratio) * 240)

                color = QColor.fromHsv(hue, 255, 255)
                rgb_image[i,j] = [color.red(), color.green(), color.blue()]

        from PyQt6.QtGui import QImage

        h, w, _ = rgb_image.shape
        image = QImage(rgb_image.data, w, h, 3*w, QImage.Format.Format_RGB888)

        scaled = image.scaled(
            w * 10,
            h * 10,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation
        )

        scaled.save(os.path.join(self.session_folder, "FULL_SURFACE.png"))

    # Exports
    #--------------------------------------------------------
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

            # stack adc and sensitivity data
            combined = np.vstack((
                adc,
                np.full((1, MAX_SIZE), np.nan),
                mapped
            ))
            np.savetxt(filename, combined, delimiter=",", fmt="%.2f")


    # serial reading
    #--------------------------------------------------------
    def read_serial(self):
        if not self.ser:
            return

        if self.ser.in_waiting:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line:
                self.process_frame(line)

    def process_frame(self, line):
        parts = line.split(",")

        if len(parts) != 64:
            return

        try:
            values = np.array(list(map(int, parts)))
        except ValueError:
            return
        

        self.data = values.reshape((MAX_SIZE, MAX_SIZE))

        # Accumulate calibration if active
        if self.calibrating:
            self.calibration += self.data

        # Printing Data in Terminal
        if(PRINT_ADC_MT_IN_TERMINAL):
            mapped_row = self.map_to_millitesla(values)
            mapped_row_rounded = np.round(mapped_row, 1)

            print("ADC:", *values)
            print("mV/mT:", *mapped_row_rounded)

        self.frame_complete()

    # frame processing
    #------------------------------------------------------------------
    def frame_complete(self):

        if self.calibrating:
            self.calibration_count += 1

            if self.calibration_count >= self.max_calibration_frames:
                self.finish_calibration()

        # Compute mapped Tesla for logging only
        mapped = self.map_to_millitesla(self.data)
        avg = np.mean(mapped)

        level = self.classify_field(avg)

        # print(f"Avg: {avg:.1f} mT | {level}")

        self.heatmap.update_data(self.data, self.calibration, self.calibrating)  # repaint GUI

    # calibration
    #-------------------------------------------------------
    def start_calibration(self):
        self.calibration[:] = 0
        self.calibration_count = 0
        self.calibrating = True
        self.label.setText("Calibrating...")

    def finish_calibration(self):
        self.calibration /= self.max_calibration_frames
        self.calibrating = False
        self.label.setText("Calibrated")

    # ADC to Tesla Conversion
    #-----------------------------------------------------------
    def map_to_millitesla(self, adc_values):

        adjusted = np.clip(adc_values - 50, 0, 1650)

        # Piecewise mapping cleaned up
        lower = adjusted < 600
        middle = (adjusted >= 600) & (adjusted <= 850)
        upper = adjusted > 850

        result = np.zeros_like(adjusted, dtype=float)

        # 0 → 600 maps -45 → -90
        result[lower] = -45 - (adjusted[lower] / 600) * 45

        # 600 → 850 saturates at -90
        result[middle] = -90

        # 850 → 1650 maps -90 → -135
        result[upper] = -90 - ((adjusted[upper] - 850) / (1650 - 850)) * 45

        return result

    def classify_field(self, avg):
        if avg > -75:
            return "LOW"
        elif -105 <= avg <= -75:
            return "MEDIUM"
        else:
            return "HIGH"



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MagneticGUI()
    window.show()
    sys.exit(app.exec())