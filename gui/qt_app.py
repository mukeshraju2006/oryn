"""Modern Qt desktop interface for Oryn.

The interface is intentionally thin: cloud persistence stays in CloudClient,
while VS Code and browser behavior remain in their existing adapters.
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError

from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QInputDialog,
    QAbstractItemView,
)

try:
    from oryn.cloud.client import CloudClient
    from oryn.cloud.session import SESSION_FILE, load_token, save_token
    from oryn.core.snapshot import Snapshot
    from oryn.applications.vscode.adapter import VSCodeAdapter
    from oryn.applications.browsers.adapter import BrowserAdapter
except ImportError:
    from .cloud.client import CloudClient
    from .cloud.session import SESSION_FILE, load_token, save_token
    from .core.snapshot import Snapshot
    from .applications.vscode.adapter import VSCodeAdapter
    from .applications.browsers.adapter import BrowserAdapter


APP_STYLE = """
* { font-family: Inter, 'Segoe UI', sans-serif; font-size: 13px; }
QMainWindow, QWidget#root, QWidget#page { background: #0b0e14; color: #eef1f8; }
QWidget#sidebar { background: #0e121a; border-right: 1px solid #202634; }
QWidget#topbar { background: #0b0e14; border-bottom: 1px solid #202634; }
QLabel { color: #eef1f8; background: transparent; }
QLabel#muted { color: #8b95a9; }
QLabel#eyebrow { color: #8b95a9; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; }
QLabel#brand { font-size: 23px; font-weight: 800; letter-spacing: -0.8px; }
QLabel#pageTitle { font-size: 28px; font-weight: 750; letter-spacing: -0.8px; }
QLabel#heroTitle { font-size: 24px; font-weight: 750; }
QLabel#metric { font-size: 29px; font-weight: 750; letter-spacing: -0.7px; }
QLabel#metricLabel { color: #8b95a9; font-size: 11px; font-weight: 650; }
QLabel#small { color: #8b95a9; font-size: 11px; }
QFrame#card, QFrame#metricCard, QFrame#hero, QFrame#authCard {
    background: #121722; border: 1px solid #242c3b; border-radius: 14px;
}
QFrame#hero { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #171d2c, stop:0.65 #15192a, stop:1 #211a35); border: 1px solid #34304f; }
QPushButton {
    background: #171d29; color: #dbe2ef; border: 1px solid #2a3344;
    border-radius: 9px; padding: 10px 14px; font-weight: 600;
}
QPushButton:hover { background: #20283a; border-color: #414c63; }
QPushButton:disabled { color: #697386; background: #141923; border-color: #222a37; }
QPushButton#primary { background: #8875ff; color: white; border: 1px solid #8875ff; }
QPushButton#primary:hover { background: #9a8aff; }
QPushButton#nav { background: transparent; border: none; color: #8994a9; text-align: left; padding: 12px 14px; border-radius: 9px; font-weight: 600; }
QPushButton#nav:hover { background: #171e2b; color: #f2f4fb; }
QPushButton#navActive { background: #24213a; color: #c6bcff; border: 1px solid #383253; text-align: left; padding: 12px 14px; border-radius: 9px; font-weight: 700; }
QLineEdit, QComboBox {
    background: #0d1119; color: #f1f3fa; border: 1px solid #2b3445;
    border-radius: 9px; padding: 11px 12px; selection-background-color: #5548a5;
}
QLineEdit:focus, QComboBox:focus { border-color: #8875ff; }
QComboBox QAbstractItemView { background: #151b27; color: #eef1f8; selection-background-color: #383253; border: 1px solid #2b3445; }
QTableWidget { background: #121722; color: #e6eaf3; border: none; gridline-color: #222a38; selection-background-color: #282443; selection-color: #ffffff; }
QHeaderView::section { background: #151b26; color: #8b95a9; border: none; border-bottom: 1px solid #293143; padding: 12px; font-size: 10px; font-weight: 700; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #202735; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 9px 4px; border-bottom: 1px solid #202735; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #0b0e14; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #30394a; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
            detail = payload.get("detail") or payload.get("message")
            if detail:
                return f"API error {exc.code}: {detail}"
        except (ValueError, AttributeError):
            pass
        return f"API request failed (HTTP {exc.code})."
    if isinstance(exc, URLError):
        return "Could not reach Oryn Cloud. Check your connection and API URL."
    return str(exc) or exc.__class__.__name__


class Task(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, function, report_progress=False):
        super().__init__()
        self.function = function
        self.report_progress = report_progress

    def run(self):
        try:
            result = self.function(self.progress.emit) if self.report_progress else self.function()
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(error_message(exc))


def run_task(owner, function, on_success, on_error, on_progress=None):
    task = Task(function, report_progress=on_progress is not None)
    owner._tasks.add(task)
    task.succeeded.connect(on_success)
    task.failed.connect(on_error)
    if on_progress is not None:
        task.progress.connect(on_progress)
    task.finished.connect(lambda task=task: owner._tasks.discard(task))
    task.start()
    return task


def make_label(text, object_name=None, muted=False):
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    elif muted:
        label.setObjectName("muted")
    return label


def make_card():
    card = QFrame()
    card.setObjectName("card")
    return card


class AuthView(QWidget):
    authenticated = Signal(object)

    def __init__(self):
        super().__init__()
        self._tasks = set()
        self.client = CloudClient()
        self.register_mode = False
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        brand_panel = QWidget()
        brand_panel.setMinimumWidth(360)
        brand_panel.setMaximumWidth(470)
        brand_panel.setStyleSheet("background:#0e121a;border-right:1px solid #202634;")
        brand = QVBoxLayout(brand_panel)
        brand.setContentsMargins(42, 44, 42, 40)
        brand.addWidget(make_label("◈  ORYN", "brand"))
        brand.addSpacing(68)
        brand.addWidget(make_label("YOUR WORK,\nRIGHT WHERE\nYOU LEFT IT.", "pageTitle"))
        brand.addSpacing(16)
        brand.addWidget(make_label("A persistent workspace layer for developers.", muted=True))
        brand.addSpacing(34)
        for mark, title, detail in [
            ("01", "Capture your context", "Save editor state, project details and browser URLs."),
            ("02", "Keep it in sync", "Your workspace snapshots follow your Oryn account."),
            ("03", "Pick up anywhere", "Restore a saved session when you return."),
        ]:
            row = QHBoxLayout()
            badge = QLabel(mark)
            badge.setFixedSize(38, 38)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet("background:#24213a;color:#c6bcff;border-radius:10px;font-weight:700;")
            text_col = QVBoxLayout()
            text_col.addWidget(make_label(title))
            text_col.addWidget(make_label(detail, muted=True))
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addLayout(text_col, 1)
            brand.addLayout(row)
            brand.addSpacing(18)
        brand.addStretch(1)
        brand.addWidget(make_label("PRIVATE BY DESIGN  ·  BUILT FOR YOUR FLOW", "eyebrow"))
        root.addWidget(brand_panel)

        right = QWidget()
        center = QVBoxLayout(right)
        center.setContentsMargins(34, 30, 34, 30)
        center.addStretch(1)
        card = QFrame()
        card.setObjectName("authCard")
        card.setMaximumWidth(460)
        form = QVBoxLayout(card)
        form.setContentsMargins(34, 32, 34, 30)
        form.setSpacing(13)

        self.form_title = make_label("Welcome back", "heroTitle")
        self.form_subtitle = make_label("Sign in to continue to your workspaces.", muted=True)
        form.addWidget(self.form_title)
        form.addWidget(self.form_subtitle)
        form.addSpacing(10)
        form.addWidget(make_label("EMAIL", "eyebrow"))
        self.email = QLineEdit()
        self.email.setPlaceholderText("you@company.com")
        self.email.setClearButtonEnabled(True)
        form.addWidget(self.email)
        form.addWidget(make_label("PASSWORD", "eyebrow"))
        self.password = QLineEdit()
        self.password.setPlaceholderText("Enter your password")
        self.password.setEchoMode(QLineEdit.Password)
        form.addWidget(self.password)

        self.confirm_label = make_label("CONFIRM PASSWORD", "eyebrow")
        self.confirm_password = QLineEdit()
        self.confirm_password.setPlaceholderText("Repeat your password")
        self.confirm_password.setEchoMode(QLineEdit.Password)
        form.addWidget(self.confirm_label)
        form.addWidget(self.confirm_password)

        self.submit_button = QPushButton("Sign in  →")
        self.submit_button.setObjectName("primary")
        self.submit_button.clicked.connect(self.submit)
        form.addWidget(self.submit_button)
        self.message = make_label("", muted=True)
        self.message.setWordWrap(True)
        form.addWidget(self.message)

        toggle = QHBoxLayout()
        self.toggle_text = make_label("New to Oryn?", muted=True)
        self.toggle_button = QPushButton("Create account")
        self.toggle_button.clicked.connect(self.toggle_mode)
        toggle.addWidget(self.toggle_text)
        toggle.addStretch(1)
        toggle.addWidget(self.toggle_button)
        form.addLayout(toggle)
        center.addWidget(card, 0, Qt.AlignHCenter)
        center.addStretch(1)
        root.addWidget(right, 1)
        self._apply_mode()

    def _apply_mode(self):
        self.confirm_label.setVisible(self.register_mode)
        self.confirm_password.setVisible(self.register_mode)
        if self.register_mode:
            self.form_title.setText("Create your account")
            self.form_subtitle.setText("One account for your saved workspaces.")
            self.submit_button.setText("Create account  →")
            self.toggle_text.setText("Already have an account?")
            self.toggle_button.setText("Sign in")
        else:
            self.form_title.setText("Welcome back")
            self.form_subtitle.setText("Sign in to continue to your workspaces.")
            self.submit_button.setText("Sign in  →")
            self.toggle_text.setText("New to Oryn?")
            self.toggle_button.setText("Create account")
        self.message.setText("")

    def toggle_mode(self):
        self.register_mode = not self.register_mode
        self._apply_mode()

    def submit(self):
        email = self.email.text().strip()
        password = self.password.text()
        if not email or not password:
            self.message.setText("Enter your email and password.")
            return
        if self.register_mode and password != self.confirm_password.text():
            self.message.setText("The passwords do not match.")
            return
        if self.register_mode and len(password) < 8:
            self.message.setText("Use a password with at least 8 characters.")
            return

        self.submit_button.setEnabled(False)
        self.message.setText("Connecting to Oryn Cloud…")
        client = CloudClient()
        register_mode = self.register_mode

        def operation(progress):
            if register_mode:
                progress("Creating your Oryn account…")
                client.register(email, password)
            progress("Authenticating with Oryn Cloud…")
            client.login(email, password)
            return client

        def success(authed_client):
            self.submit_button.setEnabled(True)
            try:
                save_token(authed_client.token)
            except OSError:
                # A disk permission issue should not discard a valid live
                # session; the user can still work until the app closes.
                self.message.setText("Signed in. This device could not persist the session, so you may need to sign in again.")
            self.authenticated.emit(authed_client)

        def failure(message):
            self.submit_button.setEnabled(True)
            self.message.setText(message)

        run_task(self, operation, success, failure, on_progress=self.message.setText)


class SnapshotChart(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.snapshots = []

    def set_snapshots(self, snapshots):
        self.snapshots = snapshots or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#121722"))
        left, right, top, bottom = 24, self.width() - 18, 16, self.height() - 30
        chart_h = max(60, bottom - top)
        days = [(datetime.now().date() - timedelta(days=6-i)) for i in range(7)]
        counts = {day: 0 for day in days}
        for snap in self.snapshots:
            raw = str(snap.get("created_at", ""))
            try:
                date = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
                if date in counts:
                    counts[date] += 1
            except (ValueError, TypeError):
                continue
        max_count = max(counts.values(), default=0) or 1
        plot_w = max(120, right - left)
        step = plot_w / 7
        painter.setPen(QPen(QColor("#252d3b"), 1))
        for line in range(4):
            y = top + chart_h * line / 3
            painter.drawLine(left, int(y), right, int(y))
        for i, day in enumerate(days):
            count = counts[day]
            bar_w = min(28, step * 0.46)
            bar_h = (chart_h - 8) * count / max_count if count else 3
            x = left + i * step + (step - bar_w) / 2
            y = bottom - bar_h
            color = QColor("#8b79ff" if count else "#252d3b")
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 4, 4)
            painter.setPen(QPen(QColor("#8b95a9")))
            painter.setFont(QFont("Inter", 9))
            painter.drawText(QRectF(left + i * step - 4, bottom + 7, step + 8, 18),
                             Qt.AlignHCenter | Qt.AlignTop, day.strftime("%a"))
        if not self.snapshots:
            painter.setPen(QPen(QColor("#8b95a9")))
            painter.drawText(self.rect(), Qt.AlignCenter, "Your snapshot activity will appear here")
        painter.end()


class DashboardView(QWidget):
    logged_out = Signal()
    session_expired = Signal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client
        self._tasks = set()
        self.workspaces = []
        self.snapshots = []
        self.workspace_id = None
        self.busy = False
        self._build()
        self.load_workspaces()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 24, 18, 18)
        side.setSpacing(8)
        side.addWidget(make_label("◈  ORYN", "brand"))
        side.addWidget(make_label("WORKSPACE CONTINUITY", "eyebrow"))
        side.addSpacing(24)
        self.nav_overview = QPushButton("▦   Overview")
        self.nav_overview.setObjectName("navActive")
        self.nav_workspaces = QPushButton("◫   Workspaces")
        self.nav_workspaces.setObjectName("nav")
        self.nav_snapshots = QPushButton("◷   Snapshots")
        self.nav_snapshots.setObjectName("nav")
        for button in (self.nav_overview, self.nav_workspaces, self.nav_snapshots):
            button.setCursor(Qt.PointingHandCursor)
            side.addWidget(button)
        side.addSpacing(24)
        side.addWidget(make_label("CURRENT WORKSPACE", "eyebrow"))
        self.workspace_combo = QComboBox()
        self.workspace_combo.setMinimumWidth(180)
        self.workspace_combo.currentIndexChanged.connect(self.on_workspace_changed)
        side.addWidget(self.workspace_combo)
        self.new_workspace_button = QPushButton("+  New workspace")
        self.new_workspace_button.clicked.connect(self.create_workspace)
        side.addWidget(self.new_workspace_button)
        side.addStretch(1)
        side.addWidget(make_label("CLOUD CONNECTION", "eyebrow"))
        connection = QFrame()
        connection.setStyleSheet("background:#121a20;border:1px solid #24443b;border-radius:10px;")
        conn = QHBoxLayout(connection)
        conn.setContentsMargins(10, 9, 10, 9)
        dot = QLabel("●")
        dot.setStyleSheet("color:#50d6a0;")
        conn.addWidget(dot)
        conn.addWidget(make_label("API endpoint configured", muted=True))
        side.addWidget(connection)
        self.logout_button = QPushButton("↪   Sign out")
        self.logout_button.clicked.connect(self.logout)
        side.addWidget(self.logout_button)
        root.addWidget(side)

        main = QWidget()
        main.setObjectName("root")
        main_col = QVBoxLayout(main)
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)
        top = QWidget()
        top.setObjectName("topbar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(30, 16, 30, 16)
        top_layout.addWidget(make_label("Workspace / Overview", muted=True))
        top_layout.addStretch(1)
        self.api_label = make_label(self.client.base_url, "small")
        top_layout.addWidget(self.api_label)
        self.refresh_button = QPushButton("↻  Refresh")
        self.refresh_button.clicked.connect(self.load_workspaces)
        top_layout.addWidget(self.refresh_button)
        main_col.addWidget(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("page")
        page = QVBoxLayout(content)
        page.setContentsMargins(30, 28, 30, 30)
        page.setSpacing(20)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.addWidget(make_label("Workspace overview", "pageTitle"))
        title_col.addWidget(make_label("A clear view of what you've saved and what you can restore.", muted=True))
        title_row.addLayout(title_col)
        title_row.addStretch(1)
        self.capture_button = QPushButton("＋  Capture workspace")
        self.capture_button.setObjectName("primary")
        self.capture_button.clicked.connect(self.capture_workspace)
        title_row.addWidget(self.capture_button, 0, Qt.AlignBottom)
        page.addLayout(title_row)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(26, 23, 26, 23)
        hero_text = QVBoxLayout()
        hero_text.addWidget(make_label("YOUR CONTEXT, PRESERVED", "eyebrow"))
        hero_text.addWidget(make_label("Pick up where you left off.", "heroTitle"))
        hero_text.addWidget(make_label("Capture the state of your workspace. Restore it when you're ready to return.", muted=True))
        hero_layout.addLayout(hero_text, 1)
        self.restore_button = QPushButton("Restore selected snapshot  →")
        self.restore_button.clicked.connect(self.restore_snapshot)
        hero_layout.addWidget(self.restore_button, 0, Qt.AlignVCenter)
        page.addWidget(hero)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        self.metric_workspaces = self._metric(metrics, 0, "WORKSPACES", "0", "Across your account", "◫")
        self.metric_snapshots = self._metric(metrics, 1, "SNAPSHOTS", "0", "In selected workspace", "◷")
        self.metric_apps = self._metric(metrics, 2, "APP TYPES", "0", "Represented in snapshots", "⌘")
        self.metric_latest = self._metric(metrics, 3, "LATEST CAPTURE", "—", "No capture yet", "↻")
        page.addLayout(metrics)

        middle = QHBoxLayout()
        middle.setSpacing(14)
        chart_card = make_card()
        chart_col = QVBoxLayout(chart_card)
        chart_col.setContentsMargins(18, 17, 18, 15)
        header = QHBoxLayout()
        header.addWidget(make_label("Snapshot activity", "heroTitle"))
        header.addStretch(1)
        header.addWidget(make_label("LAST 7 DAYS", "eyebrow"))
        chart_col.addLayout(header)
        chart_col.addWidget(make_label("Actual captures for the selected workspace", muted=True))
        self.chart = SnapshotChart()
        chart_col.addWidget(self.chart)
        middle.addWidget(chart_card, 3)

        activity_card = make_card()
        activity_col = QVBoxLayout(activity_card)
        activity_col.setContentsMargins(18, 17, 18, 15)
        activity_col.addWidget(make_label("Activity", "heroTitle"))
        activity_col.addWidget(make_label("Recent actions on this device", muted=True))
        self.activity = QListWidget()
        self.activity.setMinimumWidth(235)
        activity_col.addWidget(self.activity, 1)
        middle.addWidget(activity_card, 2)
        page.addLayout(middle)

        table_card = make_card()
        table_col = QVBoxLayout(table_card)
        table_col.setContentsMargins(18, 17, 18, 16)
        table_head = QHBoxLayout()
        table_head.addWidget(make_label("Recent snapshots", "heroTitle"))
        table_head.addStretch(1)
        self.snapshot_count_label = make_label("0 records", muted=True)
        table_head.addWidget(self.snapshot_count_label)
        table_col.addLayout(table_head)
        table_col.addWidget(make_label("Select a snapshot to restore that saved state.", muted=True))
        self.snapshot_table = QTableWidget(0, 4)
        self.snapshot_table.setHorizontalHeaderLabels(["SNAPSHOT", "APPLICATION", "CAPTURED", "FORMAT"])
        self.snapshot_table.verticalHeader().setVisible(False)
        self.snapshot_table.setShowGrid(False)
        self.snapshot_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.snapshot_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.snapshot_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.snapshot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.snapshot_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.snapshot_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.snapshot_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.snapshot_table.setMinimumHeight(190)
        self.snapshot_table.itemSelectionChanged.connect(self._selection_changed)
        table_col.addWidget(self.snapshot_table)
        page.addWidget(table_card)

        self.status_label = make_label("Ready", muted=True)
        page.addWidget(self.status_label)
        scroll.setWidget(content)
        main_col.addWidget(scroll, 1)
        root.addWidget(main, 1)

        self.nav_workspaces.clicked.connect(self.workspace_combo.setFocus)
        self.nav_snapshots.clicked.connect(self.snapshot_table.setFocus)
        self.nav_overview.clicked.connect(lambda: self.status_label.setText("Overview"))

    def _metric(self, layout, col, title, value, note, icon):
        card = QFrame()
        card.setObjectName("metricCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(17, 15, 17, 16)
        head = QHBoxLayout()
        head.addWidget(make_label(title, "metricLabel"))
        head.addStretch(1)
        glyph = make_label(icon)
        glyph.setStyleSheet("color:#b5aaff;font-size:18px;font-weight:700;")
        head.addWidget(glyph)
        box.addLayout(head)
        value_label = make_label(value, "metric")
        box.addWidget(value_label)
        note_label = make_label(note, "small")
        box.addWidget(note_label)
        layout.addWidget(card, 0, col)
        return value_label, note_label

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M")
        self.activity.insertItem(0, QListWidgetItem(f"{timestamp}   {message}"))
        while self.activity.count() > 12:
            self.activity.takeItem(self.activity.count() - 1)
        self.status_label.setText(message)

    def _task(self, function, success, activity, on_progress=None):
        self._set_busy(True)
        def done(result):
            self._set_busy(False)
            success(result)
        def failed(message):
            self._set_busy(False)
            self._log(message)
            if message.startswith("API error 401:"):
                try:
                    if SESSION_FILE.exists():
                        SESSION_FILE.unlink()
                except OSError:
                    pass
                self.session_expired.emit("Your saved session is no longer valid. Sign in again.")
                return
            QMessageBox.warning(self, "Oryn", message)
        self._log(activity)
        run_task(self, function, done, failed, on_progress=on_progress)

    def _set_busy(self, busy):
        self.busy = busy
        self.capture_button.setEnabled(not busy)
        self.restore_button.setEnabled(
            not busy and bool(self.snapshot_table.selectedItems())
        )
        self.refresh_button.setEnabled(not busy)
        self.new_workspace_button.setEnabled(not busy)
        self.workspace_combo.setEnabled(not busy)
        self.logout_button.setEnabled(not busy)

    def load_workspaces(self):
        if self.busy:
            return
        self._task(self.client.list_workspaces, self._workspaces_loaded, "Refreshing cloud workspaces…")

    def _workspaces_loaded(self, workspaces):
        previous_id = self.workspace_id
        self.workspaces = workspaces or []
        self.workspace_combo.blockSignals(True)
        self.workspace_combo.clear()
        selected_index = 0
        for index, workspace in enumerate(self.workspaces):
            self.workspace_combo.addItem(workspace.get("name", "Untitled workspace"), workspace.get("id"))
            if workspace.get("id") == previous_id:
                selected_index = index
        self.workspace_combo.setCurrentIndex(selected_index if self.workspaces else -1)
        self.workspace_combo.blockSignals(False)
        self.workspace_id = self.workspace_combo.currentData()
        self.metric_workspaces[0].setText(str(len(self.workspaces)))
        self._log(f"{len(self.workspaces)} workspace(s) loaded")
        if self.workspace_id is not None:
            self.load_snapshots()
        else:
            self.snapshots = []
            self._render_snapshots()
            self._update_metrics()

    def on_workspace_changed(self, index):
        if index < 0:
            self.workspace_id = None
            self.snapshots = []
            self._render_snapshots()
            self._update_metrics()
            return
        self.workspace_id = self.workspace_combo.itemData(index)
        self.load_snapshots()

    def load_snapshots(self):
        if self.busy or self.workspace_id is None:
            return
        workspace_id = self.workspace_id
        self._task(lambda: self.client.list_snapshots(workspace_id), self._snapshots_loaded, "Loading snapshots…")

    def _snapshots_loaded(self, snapshots):
        self.snapshots = snapshots or []
        self._render_snapshots()
        self._update_metrics()
        self.chart.set_snapshots(self.snapshots)
        self._log(f"{len(self.snapshots)} snapshot(s) loaded")

    def _render_snapshots(self):
        self.snapshot_table.setRowCount(0)
        for snapshot in self.snapshots:
            row = self.snapshot_table.rowCount()
            self.snapshot_table.insertRow(row)
            number = snapshot.get("snapshot_number", snapshot.get("id", "?"))
            application = str(snapshot.get("application") or "workspace").replace("_", " ").title()
            created = self._format_date(snapshot.get("created_at"))
            version = snapshot.get("version", "—")
            values = [f"Snapshot {number}", application, created, f"v{version}"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.UserRole, snapshot.get("id"))
                self.snapshot_table.setItem(row, col, item)
        self.snapshot_count_label.setText(f"{len(self.snapshots)} record(s)")
        if self.snapshot_table.rowCount():
            self.snapshot_table.selectRow(0)
        self._selection_changed()

    @staticmethod
    def _format_date(value):
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%b %d, %Y · %H:%M")
        except (ValueError, TypeError):
            return str(value)[:16].replace("T", " ")

    def _update_metrics(self):
        self.metric_snapshots[0].setText(str(len(self.snapshots)))
        app_types = {str(item.get("application") or "workspace") for item in self.snapshots}
        self.metric_apps[0].setText(str(len(app_types)))
        if self.snapshots:
            latest = self.snapshots[0]
            self.metric_latest[0].setText(self._format_date(latest.get("created_at")).split(" · ")[0])
            self.metric_latest[1].setText("Most recent saved snapshot")
        else:
            self.metric_latest[0].setText("—")
            self.metric_latest[1].setText("No capture yet")
        self.chart.set_snapshots(self.snapshots)

    def _selection_changed(self):
        selected = self.snapshot_table.selectedItems()
        self.restore_button.setEnabled(bool(selected) and not self.busy)

    def create_workspace(self):
        if self.busy:
            return
        name, accepted = QInputDialog.getText(self, "New workspace", "Workspace name:")
        name = name.strip()
        if not accepted:
            return
        if not name:
            QMessageBox.information(self, "Workspace name", "Enter a workspace name.")
            return
        self._task(lambda: self.client.create_workspace(name), self._workspace_created, "Creating workspace…")

    def _workspace_created(self, result):
        self._log(f"Workspace created: {result.get('name', 'New workspace')}")
        self.load_workspaces()

    def capture_workspace(self):
        if self.busy:
            return
        workspace_id = self.workspace_id
        workspaces_count = len(self.workspaces)
        def operation(progress):
            progress("Inspecting VS Code workspace and editor state…")
            snapshot = VSCodeAdapter().capture(progress=progress)
            progress("Reading Chrome session data…")
            browser_urls = BrowserAdapter().capture_urls()
            if snapshot is not None:
                snapshot.browser_urls = browser_urls
            elif browser_urls:
                snapshot = Snapshot(
                    application="browser", workspace={}, files=[], layout={},
                    active_file=None, browser_urls=browser_urls,
                )
            if snapshot is None:
                raise RuntimeError("No supported workspace or browser session was found to capture.")
            target_id = workspace_id
            if target_id is None:
                progress("Creating cloud workspace…")
                created = self.client.create_workspace(f"Oryn Workspace {workspaces_count + 1}")
                target_id = created["id"]
            progress("Compressing snapshot and uploading to Oryn Cloud…")
            result = self.client.create_snapshot(target_id, snapshot)
            return {"result": result, "workspace_id": target_id}
        self._task(
            operation,
            self._capture_done,
            "Starting workspace capture…",
            on_progress=self._log,
        )

    def _capture_done(self, result):
        snap = result["result"]
        self.workspace_id = result["workspace_id"]
        self._log(f"Snapshot {snap.get('snapshot_number', snap.get('id', '?'))} saved to Oryn Cloud")
        self.load_workspaces()

    def restore_snapshot(self):
        if self.busy:
            return
        selected = self.snapshot_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Restore snapshot", "Select a snapshot first.")
            return
        snapshot_id = self.snapshot_table.item(self.snapshot_table.currentRow(), 0).data(Qt.UserRole)
        workspace_id = self.workspace_id
        answer = QMessageBox.question(
            self, "Restore snapshot",
            "Restore this saved workspace? VS Code may close and reopen as part of the restore process.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        def operation():
            snapshot = self.client.get_snapshot(workspace_id, snapshot_id)
            if not snapshot:
                raise RuntimeError("The selected snapshot could not be found.")
            app_type = snapshot.get("application")
            vscode_ok = True
            if app_type == "vscode":
                vscode_ok = VSCodeAdapter().restore(snapshot)
                if not vscode_ok:
                    raise RuntimeError("VS Code restore did not complete. Review the terminal output for details.")
            urls = BrowserAdapter().restore_urls(snapshot.get("browser_urls", []))
            return {"urls": urls, "application": app_type}
        self._task(operation, self._restore_done, "Restoring selected snapshot…")

    def _restore_done(self, result):
        self._log(f"Restore finished · {result['application']} · {result['urls']} browser tab(s) requested")

    def logout(self):
        answer = QMessageBox.question(self, "Sign out", "Sign out of Oryn on this device?", QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "Sign out", f"Could not remove the local session: {exc}")
            return
        self.logged_out.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Oryn · Workspace continuity")
        self.resize(1440, 920)
        self.setMinimumSize(1050, 720)
        self._tasks = set()
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.auth_view = AuthView()
        self.auth_view.authenticated.connect(self.show_dashboard)
        self.stack.addWidget(self.auth_view)
        self.dashboard = None
        token = load_token()
        if token:
            self.show_dashboard(CloudClient(token=token))
        else:
            self.stack.setCurrentWidget(self.auth_view)

    def show_dashboard(self, client):
        self.dashboard = DashboardView(client)
        self.dashboard.logged_out.connect(self.show_auth)
        self.dashboard.session_expired.connect(self.show_auth)
        self.stack.addWidget(self.dashboard)
        self.stack.setCurrentWidget(self.dashboard)

    def show_auth(self, reason=""):
        if self.dashboard:
            self.stack.removeWidget(self.dashboard)
            self.dashboard.deleteLater()
            self.dashboard = None
        self.stack.setCurrentWidget(self.auth_view)
        if reason:
            self.auth_view.message.setText(reason)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Oryn")
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
