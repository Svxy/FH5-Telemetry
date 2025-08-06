# FH5 Telemetry - by SneakyDev
# View and Analyze Forza Horizon 5 Telemetry Data with Live Charts and CSV Logging
# Version: 1.0.0.5
# Date: 2025-07-05
# License: MIT

# This script captures Forza Horizon 5 telemetry data via UDP and visualizes it live with interactive charts.
# It supports multiple telemetry categories (engine, suspension, braking, input, etc.), real-time data logging to CSV,
# and replaying logged sessions with timeline scrolling.
# The UI and general functionality are sort of inspired by my Snap-On Versus Edge scan tool, but with a focus on FH5 telemetry.

# Credit to Jasperan for the original concept and core logic.
# https://github.com/jasperan/forza-horizon-5-telemetry-listener

# How it works:
# - Listens for UDP packets sent by FH5 on port 5607.
# - Parses raw binary data into structured properties.
# - Buffers incoming data and updates live charts at regular intervals (80ms).
# - Logs telemetry timestamps to CSV files when enabled.
# - Allows users to open saved CSV files to analyze logged data.

# Usage:
# 1. Run this script or use compiled executable provided on GitHub.
# 2. Ensure FH5 is running with telemetry output on port 5607.
# 2. Click "Start" to begin capturing and viewing live telemetry.
# 3. Optionally, toggle data logging to save to CSV files.
# 4. Use "Stop" to halt data capture safely.
# 5. Open saved logs via "Open Log" button to replay and analyze past sessions.

# Requirements:
# - Python 3.12+
# - PySide6
# - Forza Horizon 5

import sys
import socket
import threading
import traceback
import logging
from datetime import datetime
from collections import deque
from PySide6.QtCore import Qt, Signal, QObject, QMargins, QPointF, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTabWidget, QLabel, QTextEdit, QLineEdit, QGridLayout, QSlider, QFileDialog
)
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtGui import QPainter
from struct import unpack
import csv

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("telemetry.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger()

class ForzaDataPacket:
    sled_props = [
        'is_race_on', 'timestamp_ms',
        'engine_max_rpm', 'engine_idle_rpm', 'current_engine_rpm',
        'acceleration_x', 'acceleration_y', 'acceleration_z',
        'velocity_x', 'velocity_y', 'velocity_z',
        'angular_velocity_x', 'angular_velocity_y', 'angular_velocity_z',
        'yaw', 'pitch', 'roll',
        'norm_suspension_travel_FL', 'norm_suspension_travel_FR',
        'norm_suspension_travel_RL', 'norm_suspension_travel_RR',
        'tire_slip_ratio_FL', 'tire_slip_ratio_FR',
        'tire_slip_ratio_RL', 'tire_slip_ratio_RR',
        'wheel_rotation_speed_FL', 'wheel_rotation_speed_FR',
        'wheel_rotation_speed_RL', 'wheel_rotation_speed_RR',
        'wheel_on_rumble_strip_FL', 'wheel_on_rumble_strip_FR',
        'wheel_on_rumble_strip_RL', 'wheel_on_rumble_strip_RR',
        'wheel_in_puddle_FL', 'wheel_in_puddle_FR',
        'wheel_in_puddle_RL', 'wheel_in_puddle_RR',
        'surface_rumble_FL', 'surface_rumble_FR',
        'surface_rumble_RL', 'surface_rumble_RR',
        'tire_slip_angle_FL', 'tire_slip_angle_FR',
        'tire_slip_angle_RL', 'tire_slip_angle_RR',
        'tire_combined_slip_FL', 'tire_combined_slip_FR',
        'tire_combined_slip_RL', 'tire_combined_slip_RR',
        'suspension_travel_meters_FL', 'suspension_travel_meters_FR',
        'suspension_travel_meters_RL', 'suspension_travel_meters_RR',
        'car_ordinal', 'car_class', 'car_performance_index',
        'drivetrain_type', 'num_cylinders'
    ]

    dash_props = [
        'position_x', 'position_y', 'position_z',
        'speed', 'power', 'torque',
        'tire_temp_FL', 'tire_temp_FR',
        'tire_temp_RL', 'tire_temp_RR',
        'boost', 'fuel', 'dist_traveled',
        'best_lap_time', 'last_lap_time',
        'cur_lap_time', 'cur_race_time',
        'lap_no', 'race_pos',
        'accel', 'brake', 'clutch', 'handbrake',
        'gear', 'steer',
        'norm_driving_line', 'norm_ai_brake_diff'
    ]

    dash_format = '<iIfffffffffffffffffffffffffffffffffffffffffffffffffffiiiiifffffffffffffffffHBBBBBBbbb'

    @classmethod
    def get_props(cls):
        return cls.sled_props + cls.dash_props

    def __init__(self, data: bytes):
        if len(data) < 232:
            raise ValueError("Incomplete packet received")

        patched_data = data[:232] + data[244:323]
        try:
            vals = unpack(self.dash_format, patched_data)
        except Exception as e:
            raise ValueError(f"Unpack failed: {e}")

        for prop_name, prop_value in zip(self.get_props(), vals):
            setattr(self, prop_name, prop_value)

    def to_dict(self):
        return {prop: getattr(self, prop) for prop in self.get_props()}

class TelemetryReceiver(QObject):
    data_received = Signal(dict)
    log_message = Signal(str)

    def __init__(self, ip="0.0.0.0", port=5607):
        super().__init__()
        self.ip = ip
        self.port = port
        self._running = False
        self.sock = None
        self.thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        log.info(f"Started UDP listener on {self.ip}:{self.port}")
        self.log_message.emit(f"Started UDP listener on {self.ip}:{self.port}")

    def stop(self):
        self._running = False
        try:
            if self.sock:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
        except Exception:
            pass
        log.info("Stopped UDP listener")
        self.log_message.emit("Stopped UDP listener")

    def _listen_loop(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.ip, self.port))
            self.sock.settimeout(1.0)
        except Exception as e:
            log.error(f"Socket error: {e}")
            self.log_message.emit(f"Socket error: {e}")
            self._running = False
            return

        while self._running:
            try:
                data, addr = self.sock.recvfrom(1024)
                packet = ForzaDataPacket(data)
                self.data_received.emit(packet.to_dict())
            except socket.timeout:
                continue
            except OSError as e:
                if not self._running:
                    break
                log.error(f"Recv OSError: {e}")
                self.log_message.emit(f"Recv OSError: {e}")
            except Exception as e:
                log.error(f"Recv error: {e}\n{traceback.format_exc()}")
                self.log_message.emit(f"Recv error: {e}")

class TelemetryChart(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.title = title

        layout = QVBoxLayout(self)
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.chart_view)

        self.chart = QChart()
        self.chart.setTitle(self.title.replace('_', ' ').title())
        self.chart.legend().hide()
        self.chart_view.setChart(self.chart)

        self.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.chart.setMargins(QMargins(0, 0, 0, 0))

        self.series = QLineSeries()
        self.chart.addSeries(self.series)

        self.axis_x = QValueAxis()
        self.axis_x.setLabelFormat("%d")
        self.axis_x.setTitleText("Sample #")
        self.axis_x.setTickCount(5)
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.series.attachAxis(self.axis_x)

        self.axis_y = QValueAxis()
        self.axis_y.setLabelFormat("%.2f")
        self.axis_y.setTitleText(self.title.replace('_', ' ').title())
        self.axis_y.setTickCount(6)
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        self.series.attachAxis(self.axis_y)

        self.buffer_len = 150
        self.data = deque(maxlen=self.buffer_len)

    def set_buffer_len(self, length):
        self.buffer_len = length
        old_data = list(self.data)[-length:]
        self.data = deque(old_data, maxlen=self.buffer_len)

    def add_values(self, vals):
        self.data.extend(vals)
        points = [QPointF(i, v) for i, v in enumerate(self.data)]
        self.series.replace(points)

        if self.data:
            mn, mx = min(self.data), max(self.data)
            if mn == mx:
                mn -= 0.1
                mx += 0.1
            self.axis_y.setRange(mn, mx)
            self.axis_x.setRange(0, len(self.data))

class ForzaTelemetryApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FH5 Telemetry")
        self.setStyleSheet("background-color: #121212; color: #808080;")

        self.receiver = TelemetryReceiver(ip="0.0.0.0", port=5607)
        self.receiver.data_received.connect(self.buffer_data)
        self.receiver.log_message.connect(self.log)

        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self._setup_charts()

        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumHeight(120)
        self._auto_scroll = True
        self.log_panel.setStyleSheet("background-color: #222; color: #ccc; font-family: Consolas; font-size: 11px;")
        main_layout.addWidget(self.log_panel)

        controls = QHBoxLayout()
        main_layout.addLayout(controls)

        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.start)
        controls.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False)
        controls.addWidget(self.btn_stop)

        self.btn_toggle_log = QPushButton("Start Data Log")
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.clicked.connect(self.toggle_logging)
        controls.addWidget(self.btn_toggle_log)

        controls.addStretch()

        label = QLabel("Sample Length:")
        label.setAlignment(Qt.AlignLeft)
        controls.addWidget(label)
        self.buffer_len_input = QLineEdit("150")
        self.buffer_len_input.setFixedWidth(60)
        self.buffer_len_input.setPlaceholderText("Buf Len")
        controls.addWidget(self.buffer_len_input)

        self.btn_set_buflen = QPushButton("Apply")
        self.btn_set_buflen.clicked.connect(self.update_buffer_len)
        controls.addWidget(self.btn_set_buflen)

        controls.addStretch()

        self.btn_clear_logs = QPushButton("Clear Logs")
        self.btn_clear_logs.clicked.connect(self.log_panel.clear)
        controls.addWidget(self.btn_clear_logs)
        
        self.btn_open_log = QPushButton("Open Log")
        self.btn_open_log.clicked.connect(self.open_log_file)
        controls.addWidget(self.btn_open_log)

        self.sample_count = 0
        self.data_buffer = {k: deque() for k in self.charts.keys()}

        self.update_timer = QTimer(self)
        self.update_timer.setInterval(80)
        self.update_timer.timeout.connect(self.flush_data_buffer)

        self.logging_enabled = False
        self.log_file = None
        self.csv_writer = None
        self.csv_lock = threading.Lock()

    def _setup_charts(self):
        self.categories = {
            "Engine / Speed": [
                'current_engine_rpm', 'engine_idle_rpm', 'power', 'torque', 'speed', 'boost'
            ],
            "Suspension": [
                'norm_suspension_travel_FL', 'norm_suspension_travel_FR',
                'norm_suspension_travel_RL', 'norm_suspension_travel_RR',
                'suspension_travel_meters_FL', 'suspension_travel_meters_FR',
                'suspension_travel_meters_RL', 'suspension_travel_meters_RR'
            ],
            "Braking / Controls": [
                'accel','brake', 'clutch', 'handbrake', 'gear', 'steer'
            ],
            "Wheel / Tire": [
                'tire_slip_ratio_FL', 'tire_slip_ratio_FR',
                'tire_slip_ratio_RL', 'tire_slip_ratio_RR',
                'tire_temp_FL', 'tire_temp_FR',
                'tire_temp_RL', 'tire_temp_RR'
            ],
            "Position / Acceleration": [
                'position_x', 'position_z', 'acceleration_x', 'acceleration_z', 'velocity_x', 'velocity_z'
            ]
        }

        self.charts = {}
        for cat, keys in self.categories.items():
            tab = QWidget()
            grid = QGridLayout(tab)
            grid.setSpacing(5)
            grid.setContentsMargins(5, 5, 5, 5)
            cols = 2
            for idx, key in enumerate(keys):
                row = idx // cols
                col = idx % cols
                chart = TelemetryChart(key)
                self.charts[key] = chart
                grid.addWidget(chart, row, col)
            self.tabs.addTab(tab, cat)

    def buffer_data(self, data: dict):
        self.sample_count += 1

        def scale_controls(val): return val * 100 / 255
        def norm_steer(val): return val * 100 / 127
        def to_mph(val): return val * 2.23694
        def to_hp(val): return val / 745.7
        def clamp_zero(val): return max(val, 0)

        patch_map = {
            'accel': scale_controls,
            'brake': scale_controls,
            'clutch': scale_controls,
            'handbrake': scale_controls,
            'steer': norm_steer,
            'speed': to_mph,
            'power': to_hp,
            'torque': clamp_zero,
            'boost': clamp_zero
        }

        raw_snapshot = {}
        minmax_info = []

        for key, val in data.items():
            if key in self.data_buffer and isinstance(val, (int, float)):
                fixed_val = patch_map[key](val) if key in patch_map else val
                self.data_buffer[key].append(fixed_val)
                raw_snapshot[key] = fixed_val
                minmax_info.append(f"{key} = {fixed_val:.2f}")

        if self.logging_enabled:
            self._log_to_file(raw_snapshot)

        if self.sample_count % 100 == 0:
            timestamp = datetime.now().strftime("%H:%M:%S")
            race_on = data.get('is_race_on', False)
            log.info(f"[{timestamp}] Sample {self.sample_count}, Race On: {race_on}")
            for line in minmax_info:
                log.info(f"  {line}")
            self.log(f"[{timestamp}] Sample {self.sample_count}, Race On: {race_on}\n" + "\n".join(minmax_info))

    def _log_to_file(self, data_dict):
        with self.csv_lock:
            if self.csv_writer:
                # Write a row with timestamp and all keys in data_buffer
                row = [datetime.now().isoformat()]
                for key in self.data_buffer.keys():
                    row.append(data_dict.get(key, ''))
                self.csv_writer.writerow(row)
                self.log_file.flush()

    def update_buffer_len(self):
        try:
            val = int(self.buffer_len_input.text())
            if val <= 0:
                raise ValueError
        except ValueError:
            self.log("Invalid buffer length. Must be a positive integer.")
            return

        for chart in self.charts.values():
            chart.set_buffer_len(val)
        self.log(f"Chart buffer length set to {val}")

    def open_log_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Log CSV", ".", "CSV Files (*.csv)")
        if not path:
            return

        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.replay_data = list(reader)
                self.replay_index = 0

                for chart in self.charts.values():
                    chart.data.clear()

                if not hasattr(self, 'slider'):
                    self.slider = QSlider(Qt.Horizontal)
                    self.slider.setMinimum(0)
                    self.slider.setMaximum(len(self.replay_data) - 1)
                    self.slider.valueChanged.connect(self.update_replay_frame)
                    self.layout().insertWidget(2, self.slider)
                else:
                    self.slider.setMaximum(len(self.replay_data) - 1)
                    self.slider.setValue(0)

                self.log(f"Loaded {len(self.replay_data)} frames from {path}")

        except Exception as e:
            self.log(f"Failed to read log file: {e}")

    def flush_data_buffer(self):
        for key, vals in self.data_buffer.items():
            if vals:
                chart = self.charts.get(key)
                if chart:
                    chart.add_values(list(vals))
                vals.clear()
                
    def update_replay_frame(self, index):
        if not hasattr(self, 'replay_data') or index >= len(self.replay_data):
            return

        window_size = 150
        start = max(0, index - window_size + 1)
        end = index + 1

        for key, chart in self.charts.items():
            # Extract windowed data for this key from replay_data
            try:
                # Slice replay frames in window
                vals = []
                for i in range(start, end):
                    frame_val = self.replay_data[i].get(key, '')
                    vals.append(float(frame_val) if frame_val else 0.0)

                chart.data = deque(vals, maxlen=window_size)
                chart.add_values(list(chart.data))
                # Lock y-axis range to fit data, pad slightly if flat
                mn, mx = min(chart.data), max(chart.data)
                if mn == mx:
                    mn -= 0.1
                    mx += 0.1
                chart.axis_y.setRange(mn, mx)
                chart.axis_x.setRange(0, len(chart.data) - 1)

            except ValueError:
                continue

    def start(self):
        self.receiver.start()
        self.update_timer.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        log.info("Telemetry capture started.")
        self.log("Telemetry capture started.")

    def stop(self):
        self.receiver.stop()
        self.update_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        log.info("Telemetry capture stopped.")
        self.log("Telemetry capture stopped.")
        if self.logging_enabled:
            self._stop_logging()

        for chart in self.charts.values():
            chart.data.clear()
            chart.add_values([])

    def toggle_logging(self, checked):
        if checked:
            self._start_logging()
            self.btn_toggle_log.setText("Stop Data Log")
        else:
            self._stop_logging()
            self.btn_toggle_log.setText("Start Data Log")

    def _start_logging(self):
        if self.logging_enabled:
            return
        try:
            filename = f"telemetry_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self.log_file = open(filename, 'w', newline='', encoding='utf-8')
            self.csv_writer = csv.writer(self.log_file)
            headers = ['timestamp'] + list(self.data_buffer.keys())
            self.csv_writer.writerow(headers)
            self.logging_enabled = True
            self.log(f"Data logging started: {filename}")
            log.info(f"Data logging started: {filename}")
        except Exception as e:
            self.log(f"Failed to start logging: {e}")
            log.error(f"Failed to start logging: {e}")

    def _stop_logging(self):
        if not self.logging_enabled:
            return
        try:
            with self.csv_lock:
                self.log_file.close()
                self.log_file = None
                self.csv_writer = None
                self.logging_enabled = False
            self.log("Data logging stopped.")
            log.info("Data logging stopped.")
        except Exception as e:
            self.log(f"Failed to stop logging: {e}")
            log.error(f"Failed to stop logging: {e}")

    def log(self, msg):
        self.log_panel.append(msg)
        self.log_panel.ensureCursorVisible()

    def closeEvent(self, event):
        self.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ForzaTelemetryApp()
    window.showMaximized()
    sys.exit(app.exec())