import sys
import json
import socket
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, QLineEdit, QMessageBox, QFrame,
    QMenuBar, QMenu, QFileDialog, QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QPushButton as QtPushButton
)
from PySide6.QtGui import QPixmap, QAction
from PySide6.QtCore import Qt
from functools import partial

class ConfigEditor(QDialog):
    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置文件修改器")
        self.setMinimumSize(600, 400)
        self.config_path = config_path

        self.layout = QVBoxLayout(self)
        self.table = QTableWidget(self)
        self.layout.addWidget(self.table)

        self.save_btn = QtPushButton("保存修改", self)
        self.layout.addWidget(self.save_btn)
        self.save_btn.clicked.connect(self.save_changes)

        self.load_config()

    def load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            self.buttons = self.data.get("buttons", [])
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取配置失败: {e}")
            self.close()
            return

        self.table.setRowCount(len(self.buttons))
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["名称", "指令文本", "X 坐标", "Y 坐标"])

        for row, item in enumerate(self.buttons):
            self.table.setItem(row, 0, QTableWidgetItem(item.get("name", "")))
            try:
                text_value = bytes.fromhex(item.get("command", "")).decode("utf-8")
            except Exception:
                text_value = ""
            self.table.setItem(row, 1, QTableWidgetItem(text_value))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.get("x", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(str(item.get("y", ""))))

    def save_changes(self):
        for row in range(self.table.rowCount()):
            self.buttons[row]["name"] = self.table.item(row, 0).text()
            # 将文本自动转为十六进制命令
            try:
                self.buttons[row]["command"] = self.table.item(row, 1).text().encode("utf-8").hex().upper()
            except Exception:
                self.buttons[row]["command"] = ""
            self.buttons[row]["x"] = int(self.table.item(row, 2).text())
            self.buttons[row]["y"] = int(self.table.item(row, 3).text())

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "成功", "配置已保存")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("导播控制台")
        self.setFixedSize(768, 1152)

        if getattr(sys, 'frozen', False):
            self.script_dir = os.path.dirname(sys.executable)
        else:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))

        self.conf_path = os.path.join(self.script_dir, "conf_unified.json")
        self.button_list = []

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.menu_bar = self.menuBar()
        self.connection_menu = self.menu_bar.addMenu("连接记录")
        self.config_menu = self.menu_bar.addMenu("配置文件")
        self.load_connection_history()
        self.add_config_menu_actions()

        self.top_bar = QFrame(self.central_widget)
        self.top_bar.setGeometry(0, 0, 768, 45)
        self.top_bar.setStyleSheet("background-color: white;")

        bg_path = os.path.join(self.script_dir, "background.png")
        self.bg_label = QLabel(self.central_widget)
        self.bg_label.setGeometry(0, 45, 768, 1107)
        self.bg_pixmap = QPixmap(bg_path)
        if not self.bg_pixmap.isNull():
            self.bg_label.setPixmap(self.bg_pixmap.scaled(768, 1107))
        else:
            QMessageBox.warning(self, "错误", f"背景图片未能加载：{bg_path}")

        self.sock = None
        self.active_button = None

        self.ip_input = QLineEdit(self.central_widget)
        self.ip_input.setPlaceholderText("设备IP")
        self.ip_input.setGeometry(20, 10, 150, 30)

        self.port_input = QLineEdit(self.central_widget)
        self.port_input.setPlaceholderText("端口")
        self.port_input.setGeometry(180, 10, 80, 30)

        self.connect_btn = QPushButton("连接串口", self.central_widget)
        self.connect_btn.setGeometry(270, 10, 100, 30)
        self.connect_btn.clicked.connect(self.toggle_connection)

        self.status_light = QLabel(self.central_widget)
        self.status_light.setGeometry(380, 15, 20, 20)
        self.set_status_light(False)

        self.default_style = (
            "background-color: #f0f0f0;"
            "border: 1px solid #555;"
            "border-radius: 4px;"
            "font-size: 14px;"
        )

        self.active_style = "background-color: lightblue; border: 1px solid #555; border-radius: 4px; font-size: 14px;"

        self.load_buttons()

        # 🧪 调试命令输入框
        self.debug_input = QLineEdit(self.central_widget)
        self.debug_input.setPlaceholderText("输入调试命令，例如 CAM1.")
        self.debug_input.setGeometry(480, 10, 200, 30)

        self.debug_send_btn = QPushButton("发送", self.central_widget)
        self.debug_send_btn.setGeometry(690, 10, 60, 30)
        self.debug_send_btn.clicked.connect(self.send_debug_command)

    def set_status_light(self, connected: bool):
        color = "green" if connected else "red"
        self.status_light.setStyleSheet(f"background-color: {color}; border-radius: 10px;")

    def toggle_connection(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                print(f"关闭连接出错: {e}")
            self.sock = None
            self.set_status_light(False)
            self.connect_btn.setText("连接串口")
            # 重置所有按钮
            for btn in self.button_list:
                btn.setChecked(False)
                btn.setStyleSheet(self.default_style)
            self.active_button = None
        else:
            ip = self.ip_input.text().strip()
            port = self.port_input.text().strip()
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(10)
                self.sock.connect((ip, int(port)))
                self.set_status_light(True)
                self.connect_btn.setText("断开连接")
                self.save_connection_history(ip, port)
            except Exception as e:
                QMessageBox.critical(self, "连接失败", str(e))
                self.sock = None
                self.set_status_light(False)

    def load_connection_history(self):
        self.history_path = os.path.join(self.script_dir, "history.json")
        self.connection_menu.clear()
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                for entry in history.get("records", []):
                    ip = entry.get("ip", "")
                    port = entry.get("port", "")
                    action = QAction(f"{ip}:{port}", self)
                    action.triggered.connect(lambda _, ip=ip, port=port: self.fill_connection(ip, port))
                    self.connection_menu.addAction(action)
            except Exception as e:
                print(f"加载连接历史失败: {e}")

    def save_connection_history(self, ip, port):
        records = []
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, 'r', encoding='utf-8') as f:
                    records = json.load(f).get("records", [])
            except Exception:
                pass
        new_record = {"ip": ip, "port": port}
        if new_record not in records:
            records.append(new_record)
        with open(self.history_path, 'w', encoding='utf-8') as f:
            json.dump({"records": records}, f, indent=2, ensure_ascii=False)
        self.load_connection_history()

    def fill_connection(self, ip, port):
        self.ip_input.setText(ip)
        self.port_input.setText(port)

    def add_config_menu_actions(self):
        load_action = QAction("加载配置文件", self)
        load_action.triggered.connect(self.select_config_file)
        self.config_menu.addAction(load_action)

        edit_action = QAction("配置文件修改器", self)
        edit_action.triggered.connect(self.edit_config_file)
        self.config_menu.addAction(edit_action)

    def select_config_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择配置文件", self.script_dir, "JSON 文件 (*.json)")
        if file_path:
            self.conf_path = file_path
            self.load_buttons()

    def edit_config_file(self):
        editor = ConfigEditor(self.conf_path, self)
        if editor.exec():
            self.load_buttons()

    def load_buttons(self):
        try:
            with open(self.conf_path, "r", encoding="utf-8") as f:
                button_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "配置文件读取错误", str(e))
            return

        for btn in self.button_list:
            btn.deleteLater()
        self.button_list.clear()

        for item in button_data.get("buttons", []):
            name = item.get("name", "未命名")
            cmd = item.get("command", "")
            x = item.get("x", 100)
            y = item.get("y", 100)

            btn = QPushButton(name, self.central_widget)
            btn.setGeometry(x, y, 120, 40)
            btn.setCheckable(True)
            btn.setStyleSheet(self.default_style)
            btn.clicked.connect(partial(self.send_command, cmd, btn))
            btn.show()
            self.button_list.append(btn)

    def send_debug_command(self):
        if not self.sock:
            QMessageBox.warning(self, "未连接", "请先连接设备")
            return
        text = self.debug_input.text().strip()
        if not text:
            QMessageBox.warning(self, "无输入", "请输入要发送的文本指令")
            return
        try:
            hex_data = text.encode("utf-8").hex().upper()
            self.sock.send(bytes.fromhex(hex_data))
        except Exception as e:
            QMessageBox.critical(self, "发送失败", str(e))

    def send_command(self, hex_command, button):
        if not self.sock:
            button.setChecked(False)
            button.setStyleSheet(self.default_style)
            QMessageBox.warning(self, "未连接", "请先连接设备")
            return

        if self.active_button and self.active_button != button:
            self.active_button.setChecked(False)
            self.active_button.setStyleSheet(self.default_style)

        self.active_button = button
        button.setChecked(True)
        button.setStyleSheet(self.active_style)

        try:
            self.sock.send(bytes.fromhex(hex_command))
        except Exception as e:
            QMessageBox.critical(self, "发送失败", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
