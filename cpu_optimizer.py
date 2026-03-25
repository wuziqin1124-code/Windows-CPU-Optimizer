import sys
import time
import threading
import ctypes
import psutil

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QSystemTrayIcon, QMenu, QAction,
    QComboBox, QListWidget, QStyle, QMessageBox,
    QFrame, QGroupBox, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal, QMutex, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_INFORMATION = 0x0400

PRIORITY_CLASSES = {
    "HIGH": 0x00000080,
    "LOW": 0x00000040,
    "NORMAL": 0x00000020,
}

CRITICAL_PROCESSES = {
    'system', 'idle', 'svchost.exe', 'csrss.exe', 'wininit.exe',
    'services.exe', 'lsass.exe', 'smss.exe', 'winlogon.exe',
    'dwm.exe', 'explorer.exe', 'conhost.exe', 'taskhostw.exe',
    'fontdrvhost.exe', 'sihost.exe', 'ctfmon.exe'
}


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def get_foreground_pid():
    hwnd = user32.GetForegroundWindow()
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def set_priority(pid, level):
    try:
        handle = kernel32.OpenProcess(
            PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION,
            False,
            pid
        )
        if handle:
            kernel32.SetPriorityClass(handle, PRIORITY_CLASSES[level])
            kernel32.CloseHandle(handle)
    except:
        pass


def set_affinity(pid, cpu_count):
    try:
        p = psutil.Process(pid)
        cores = list(range(cpu_count // 2))
        if cores:
            p.cpu_affinity(cores)
    except:
        pass


class Optimizer(threading.Thread):
    def __init__(self, window):
        super().__init__()
        self.daemon = True
        self.window = window
        self.running = True
        self.current_pid = None
        self.pid_mutex = QMutex()

    def run(self):
        last_process_update = 0

        while self.running:
            if not self.window.optimizing:
                time.sleep(0.5)
                continue

            try:
                mode = self.window.mode
                fg_pid = get_foreground_pid()

                self.pid_mutex.lock()
                pid_changed = fg_pid != self.current_pid
                if pid_changed:
                    self.current_pid = fg_pid
                self.pid_mutex.unlock()

                current_time = time.time()

                if pid_changed:
                    if mode == "激进模式":
                        set_priority(fg_pid, "HIGH")
                        self.reduce_others(fg_pid, "LOW")

                    elif mode == "平衡模式":
                        set_priority(fg_pid, "HIGH")
                        self.reduce_others(fg_pid, "NORMAL")

                    elif mode == "绑核模式":
                        set_priority(fg_pid, "HIGH")
                        set_affinity(fg_pid, psutil.cpu_count())
                        self.reduce_others(fg_pid, "LOW")

                    try:
                        name = psutil.Process(fg_pid).name()
                    except:
                        name = "Unknown"

                    cpu_total = psutil.cpu_percent(interval=None)

                    try:
                        proc = psutil.Process(fg_pid)
                        proc.cpu_percent()
                        time.sleep(0.1)
                        cpu_proc = proc.cpu_percent()
                    except:
                        cpu_proc = 0

                    self.window.update_signal.emit(name, cpu_total, cpu_proc, fg_pid)

                if current_time - last_process_update >= 2:
                    self.update_process_list()
                    last_process_update = current_time

                time.sleep(0.5)

            except Exception as e:
                print("Error:", e)

    def reduce_others(self, fg_pid, level):
        for p in psutil.process_iter(['pid', 'name']):
            try:
                if p.info['name'].lower() in CRITICAL_PROCESSES:
                    continue
                if p.info['pid'] != fg_pid:
                    set_priority(p.info['pid'], level)
            except:
                continue

    def update_process_list(self):
        procs = []
        for p in psutil.process_iter(['name', 'cpu_percent', 'pid']):
            try:
                procs.append((p.info['name'], p.info['cpu_percent'], p.info['pid']))
            except:
                continue

        procs = sorted(procs, key=lambda x: x[1], reverse=True)[:8]
        self.window.process_update_signal.emit(procs)


class Window(QWidget):

    update_signal = pyqtSignal(str, float, float, int)
    process_update_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()

        if not is_admin():
            QMessageBox.warning(
                self,
                "权限不足",
                "此工具需要管理员权限运行。\n请右键选择「以管理员身份运行」。"
            )

        self.setWindowTitle("CPU Optimizer Pro")
        self.resize(560, 520)
        self.setMinimumSize(520, 480)
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                font-family: "Segoe UI", Microsoft YaHei, sans-serif;
            }
        """)

        self.optimizing = False
        self.mode = "平衡模式"

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title_label = QLabel("CPU Optimizer Pro")
        title_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; padding: 10px;")
        main_layout.addWidget(title_label)

        status_frame = self.create_status_group()
        main_layout.addWidget(status_frame)

        control_frame = self.create_control_group()
        main_layout.addWidget(control_frame)

        process_frame = self.create_process_group()
        main_layout.addWidget(process_frame)

        main_layout.addStretch()
        self.setLayout(main_layout)

        self.update_signal.connect(self.update_status)
        self.process_update_signal.connect(self.update_process_list)

        self.init_tray()

        self.optimizer = Optimizer(self)
        self.optimizer.start()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_cpu_display)
        self.update_timer.start(1000)

    def create_status_group(self):
        frame = QFrame()
        frame.setMinimumHeight(160)
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                padding: 15px;
                border: 1px solid #ddd;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)

        self.status_label = QLabel("未启动")
        self.status_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(self.status_label)

        self.process_name_label = QLabel("前台进程：--")
        self.process_name_label.setFont(QFont("Segoe UI", 11))
        layout.addWidget(self.process_name_label)

        self.pid_label = QLabel("PID：--")
        self.pid_label.setFont(QFont("Segoe UI", 10))
        self.pid_label.setStyleSheet("color: #95a5a6;")
        layout.addWidget(self.pid_label)

        cpu_layout = QHBoxLayout()

        self.total_cpu_label = QLabel("系统 CPU：--%")
        self.total_cpu_label.setFont(QFont("Segoe UI", 10))
        cpu_layout.addWidget(self.total_cpu_label)

        cpu_layout.addStretch()

        self.proc_cpu_label = QLabel("前台 CPU：--%")
        self.proc_cpu_label.setFont(QFont("Segoe UI", 10))
        cpu_layout.addWidget(self.proc_cpu_label)

        layout.addLayout(cpu_layout)

        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        self.cpu_progress.setTextVisible(True)
        self.cpu_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 5px;
                text-align: center;
                background-color: #ecf0f1;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2ecc71
                );
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.cpu_progress)

        frame.setLayout(layout)
        return frame

    def create_control_group(self):
        frame = QFrame()
        frame.setMinimumHeight(70)
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                padding: 15px;
                border: 1px solid #ddd;
            }
        """)

        layout = QHBoxLayout()
        layout.setSpacing(15)

        self.btn = QPushButton("开始优化")
        self.btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.btn.setFixedSize(120, 40)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.btn.clicked.connect(self.toggle_opt)
        layout.addWidget(self.btn)

        self.mode_box = QComboBox()
        self.mode_box.setFont(QFont("Segoe UI", 11))
        self.mode_box.setFixedSize(140, 35)
        self.mode_box.addItems(["平衡模式", "激进模式", "绑核模式"])
        self.mode_box.currentTextChanged.connect(self.change_mode)
        self.mode_box.setStyleSheet("""
            QComboBox {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 5px 10px;
                background-color: white;
            }
            QComboBox:hover {
                border-color: #3498db;
            }
        """)
        layout.addWidget(self.mode_box)

        layout.addStretch()

        self.mode_desc_label = QLabel("前台 HIGH / 后台 NORMAL")
        self.mode_desc_label.setFont(QFont("Segoe UI", 9))
        self.mode_desc_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(self.mode_desc_label)

        frame.setLayout(layout)
        return frame

    def create_process_group(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                padding: 15px;
                border: 1px solid #ddd;
            }
        """)

        layout = QVBoxLayout()

        title = QLabel("Top 进程")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)

        self.process_table = QTableWidget()
        self.process_table.setMinimumHeight(180)
        self.process_table.setColumnCount(3)
        self.process_table.setHorizontalHeaderLabels(["进程名", "PID", "CPU %"])
        self.process_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.process_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.process_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.process_table.setColumnWidth(1, 80)
        self.process_table.setColumnWidth(2, 80)
        self.process_table.setFont(QFont("Segoe UI", 10))
        self.process_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                gridline-color: #ecf0f1;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
        """)
        self.process_table.setAlternatingRowColors(True)
        self.process_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.process_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.process_table.verticalHeader().setDefaultSectionSize(32)
        self.process_table.verticalHeader().setVisible(False)
        layout.addWidget(self.process_table)

        frame.setLayout(layout)
        return frame

    def update_cpu_display(self):
        if self.optimizing:
            cpu_total = psutil.cpu_percent(interval=None)
            self.cpu_progress.setValue(int(cpu_total))

    def toggle_opt(self):
        self.optimizing = not self.optimizing
        if self.optimizing:
            self.btn.setText("停止优化")
            self.btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
                QPushButton:pressed {
                    background-color: #a93226;
                }
            """)
            self.status_label.setText("运行中")
            self.status_label.setStyleSheet("color: #27ae60;")
        else:
            self.btn.setText("开始优化")
            self.btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background-color: #2ecc71;
                }
                QPushButton:pressed {
                    background-color: #1e8449;
                }
            """)
            self.status_label.setText("已停止")
            self.status_label.setStyleSheet("color: #e74c3c;")

    def change_mode(self, mode):
        self.mode = mode
        desc_map = {
            "平衡模式": "前台 HIGH / 后台 NORMAL",
            "激进模式": "前台 HIGH / 后台 LOW",
            "绑核模式": "前台 HIGH + 绑前半核 / 后台 LOW"
        }
        self.mode_desc_label.setText(desc_map.get(mode, ""))

    def update_status(self, name, total, proc, pid):
        self.process_name_label.setText(f"前台进程：{name}")
        self.pid_label.setText(f"PID：{pid}")
        self.total_cpu_label.setText(f"系统 CPU：{total:.1f}%")
        self.proc_cpu_label.setText(f"前台 CPU：{proc:.1f}%")
        self.cpu_progress.setValue(int(total))

    def update_process_list(self, procs):
        self.process_table.setRowCount(len(procs))
        for i, (name, cpu, pid) in enumerate(procs):
            self.process_table.setItem(i, 0, QTableWidgetItem(name))
            self.process_table.setItem(i, 1, QTableWidgetItem(str(pid)))
            self.process_table.setItem(i, 2, QTableWidgetItem(f"{cpu:.1f}%"))

            if cpu > 50:
                color = "#e74c3c"
            elif cpu > 20:
                color = "#f39c12"
            else:
                color = "#2ecc71"
            self.process_table.item(i, 2).setForeground(QColor(color))

    def init_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)

        menu = QMenu()

        show_action = QAction("打开", self)
        quit_action = QAction("退出", self)

        show_action.triggered.connect(self.show_window)
        quit_action.triggered.connect(self.exit_app)

        menu.addAction(show_action)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)

        self.tray.show()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_window()

    def show_window(self):
        self.show()
        self.activateWindow()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def exit_app(self):
        self.optimizer.running = False
        self.tray.hide()
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    win = Window()
    win.show()

    sys.exit(app.exec_())