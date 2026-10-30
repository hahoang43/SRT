"""SRT CUỐN CHIẾU - ChatGPT web mode, no API key.
Windows: run_windows.bat | Cross-platform: python app.py
The connection test checks that ChatGPT Web and its editor are ready.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal, QUrl, QSettings
from PySide6.QtGui import QColor, QBrush, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTableView, QVBoxLayout,
    QWidget,
)
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

from srt_engine import (
    Cue, DEFAULT_PROMPT, check_translations, extract_json, make_batch_prompt,
    parse_srt, read_text, restore_progress, save_progress, srt_contents,
)
from web_connect import PROBE_JS, READ_LATEST_RESPONSE_JS, SEND_MESSAGE_JS, make_send_message_js
from native_chatgpt_bridge import load_web_bridge, NATIVE_SEND_ACK_JS

WEB_BRIDGE = load_web_bridge()
PROBE_JS = WEB_BRIDGE.probe_js
READ_LATEST_RESPONSE_JS = WEB_BRIDGE.read_js


class CueTableModel(QAbstractTableModel):
    changed = Signal()
    headers = ('STT', 'Mốc thời gian', 'Gốc (tiếng Trung)', 'Dịch (tiếng Việt)')

    def __init__(self):
        super().__init__()
        self.cues: list[Cue] = []
        self.page = 0
        self.page_size = 150

    def load_cues(self, cues: list[Cue]):
        self.beginResetModel()
        self.cues = cues
        self.page = 0
        self.endResetModel()

    def set_page(self, page: int):
        if page == self.page:
            return
        self.beginResetModel()
        self.page = page
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else max(0, min(self.page_size, len(self.cues) - self.page*self.page_size))

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section] if orientation == Qt.Orientation.Horizontal else str(self.page*self.page_size + section + 1)
        return None

    def _cue(self, row: int) -> Cue:
        return self.cues[self.page*self.page_size + row]

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        cue = self._cue(index.row())
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return (cue.number, cue.time_range, cue.source, cue.translation)[index.column()]
        if role == Qt.ItemDataRole.BackgroundRole and index.column() == 3:
            return QBrush(QColor('#e6f8ee' if cue.translation.strip() else '#fff8ee'))
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 0:
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.ForegroundRole and index.column() in (0, 1):
            return QColor('#5a6475')
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 3:
            return flags | Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):
        if index.isValid() and index.column() == 3 and role == Qt.ItemDataRole.EditRole:
            self._cue(index.row()).translation = str(value).strip()
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])
            self.changed.emit()
            return True
        return False

    def refresh_number(self, number: int):
        row = number - 1 - self.page*self.page_size
        if 0 <= row < self.rowCount():
            index = self.index(row, 3)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DỊCH SRT WEB v1.3.0 — ChatGPT Web | Cuốn chiếu tự động')
        self.resize(1640, 910)
        self.path: Path | None = None
        self.source_content = ''
        self.settings = QSettings('SRT-Cuon-Chieu', 'SRT-Cuon-Chieu')
        self.prompt = self.settings.value('prompt', DEFAULT_PROMPT, type=str) or DEFAULT_PROMPT
        self.web_batch: list[int] = []
        self._web_loaded = False
        self._connection_state = 'idle'
        self._connection_deadline = 0.0
        self._connection_baseline = 0
        self._probe_busy = False
        self.connection_timer = QTimer(self)
        self.connection_timer.setInterval(1250)
        self.connection_timer.timeout.connect(self._probe_web_connection)
        self.auto_session = False
        self.auto_paused = False
        self.batch_waiting_for_json = False
        self.auto_batch: list[Cue] = []
        self.auto_baseline = 0
        self.auto_deadline = 0.0
        self.auto_poll_busy = False
        self.auto_last_response = ''
        self.auto_stable_reads = 0
        self.auto_generation = 0
        self.auto_retries = {}
        self.auto_last_error = ''
        self.auto_diagnostic = None
        self.auto_send_state = 'idle'
        self.auto_received = None
        self.next_batch_timer = QTimer(self)
        self.next_batch_timer.setSingleShot(True)
        self.next_batch_timer.timeout.connect(self._queue_next_auto_batch)
        self.service_wait_until = 0.0
        self.service_wait_timer = QTimer(self)
        self.service_wait_timer.setInterval(1000)
        self.service_wait_timer.timeout.connect(self._tick_service_wait)
        self._build_ui()
        self._style()
        self.log('SRT WEB v1.3.0 — Sẵn sàng. Mở file SRT để bắt đầu.')
        self.log(WEB_BRIDGE.status)

    def _button(self, text: str, action, kind: str = ''):
        button = QPushButton(text)
        if kind:
            button.setProperty('kind', kind)
        button.clicked.connect(action)
        button.setMinimumHeight(34)
        return button

    def _build_ui(self):
        body = QWidget()
        self.setCentralWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(9)

        top = QHBoxLayout()
        branding = QVBoxLayout()
        heading = QLabel('DỊCH SRT CHATGPT WEB — TỰ ĐỘNG')
        heading.setObjectName('heading')
        branding.addWidget(heading)
        note = QLabel('Chuẩn hóa JSON đầu vào/đầu ra · Dịch cuốn chiếu · Khóa ID và thời gian')
        note.setObjectName('subtitle')
        branding.addWidget(note)
        top.addLayout(branding, 1)
        self.connection_label = QLabel('● Chưa kiểm tra ChatGPT Web')
        self.connection_label.setObjectName('status')
        top.addWidget(self.connection_label)
        self.connect_btn = self._button('⚡ Mở ChatGPT Web', self.connect_and_open, 'teal')
        top.addWidget(self.connect_btn)
        self.web_btn = self._button('🌐 Hiện Web', self.toggle_web, 'gold')
        top.addWidget(self.web_btn)
        outer.addLayout(top)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.splitter, 1)

        left = QFrame()
        left.setObjectName('panel')
        left_layout = QVBoxLayout(left)
        file_bar = QHBoxLayout()
        self.filename = QLabel('Chưa mở file SRT')
        self.filename.setObjectName('filename')
        self.filename.setWordWrap(True)
        file_bar.addWidget(self.filename, 1)
        self.page_back = self._button('<< Trước', lambda: self.set_page(self.model.page-1))
        self.page_box = QComboBox()
        self.page_box.setMinimumWidth(95)
        self.page_box.currentIndexChanged.connect(self.set_page)
        self.page_forward = self._button('Sau >>', lambda: self.set_page(self.model.page+1))
        file_bar.addWidget(self.page_back)
        file_bar.addWidget(self.page_box)
        file_bar.addWidget(self.page_forward)
        left_layout.addLayout(file_bar)
        self.model = CueTableModel()
        self.model.changed.connect(self.table_edited)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setDefaultSectionSize(65)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 58)
        self.table.setColumnWidth(1, 225)
        left_layout.addWidget(self.table, 1)
        self.table_info = QLabel('0 dòng phụ đề · 0 dòng đã dịch')
        left_layout.addWidget(self.table_info)
        self.splitter.addWidget(left)

        control = QScrollArea()
        control.setObjectName('controls')
        control.setWidgetResizable(True)
        control.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        control_content = QWidget()
        forms = QVBoxLayout(control_content)
        forms.setSpacing(9)
        forms.setContentsMargins(7, 7, 7, 7)

        file_group = QGroupBox('1. QUẢN LÝ FILE')
        file_layout = QVBoxLayout(file_group)
        file_buttons = QHBoxLayout()
        self.open_btn = self._button('📁 Mở File SRT', self.open_srt)
        self.save_btn = self._button('💾 Lưu SRT', self.save_srt)
        file_buttons.addWidget(self.open_btn)
        file_buttons.addWidget(self.save_btn)
        file_layout.addLayout(file_buttons)
        self.checkpoint_label = QLabel('Tiến độ tự lưu: .progress.json cùng thư mục')
        self.checkpoint_label.setWordWrap(True)
        file_layout.addWidget(self.checkpoint_label)
        forms.addWidget(file_group)

        prompt_group = QGroupBox('2. PROMPT NGÔN NGỮ')
        prompt_layout = QVBoxLayout(prompt_group)
        langs = QHBoxLayout()
        langs.addWidget(QLabel('Ngôn ngữ dịch:'))
        self.lang_box = QComboBox()
        self.lang_box.addItems(['Tiếng Việt (Trung → Việt)'])
        langs.addWidget(self.lang_box, 1)
        prompt_layout.addLayout(langs)
        prompt_layout.addWidget(self._button('🔎 MỞ BẢNG TẠO PROMPT', self.edit_prompt, 'light'))
        forms.addWidget(prompt_group)

        web_connect_group = QGroupBox('3. KẾT NỐI CHATGPT WEB — KHÔNG CẦN API')
        web_connect_layout = QVBoxLayout(web_connect_group)
        connect_note = QLabel('Nhấn Kết nối để mở ChatGPT trong app và kiểm tra ô chat đã sẵn sàng. '
                              'Ứng dụng không tự gửi lời chào. Dùng được chế độ khách khi ChatGPT cho phép; không bắt đăng nhập ở phía ứng dụng.')
        connect_note.setWordWrap(True)
        web_connect_layout.addWidget(connect_note)
        self.test_btn = self._button('🧪 KIỂM TRA KẾT NỐI WEB', self.connect_and_open, 'light')
        web_connect_layout.addWidget(self.test_btn)
        forms.addWidget(web_connect_group)

        settings_group = QGroupBox('4. CÀI ĐẶT DỊCH CUỐN CHIẾU (WEB)')
        settings = QFormLayout(settings_group)
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 150)
        self.batch_spin.setValue(20)
        settings.addRow('Dòng / lần:', self.batch_spin)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(15, 300)
        self.timeout_spin.setValue(90)
        self.timeout_spin.setSuffix(' giây')
        settings.addRow('Chờ khi Web không tiến triển:', self.timeout_spin)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 120)
        self.delay_spin.setValue(3)
        self.delay_spin.setSuffix(' giây')
        settings.addRow('Chờ giữa lô:', self.delay_spin)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFormat('%v% · Đã dịch %p%')
        settings.addRow(self.progress)
        self.start_btn = self._button('📋 BẮT ĐẦU DỊCH CUỐN CHIẾU', self.start_translation, 'green')
        self.pause_btn = self._button('⏸ TẠM DỪNG', self.toggle_pause, 'gold')
        self.stop_btn = self._button('⏹ DỪNG LẠI', self.stop_translation, 'red')
        settings.addRow(self.start_btn)
        settings.addRow(self.pause_btn)
        settings.addRow(self.stop_btn)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        forms.addWidget(settings_group)

        log_group = QGroupBox('5. NHẬT KÝ HOẠT ĐỘNG')
        log_layout = QVBoxLayout(log_group)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        log_layout.addWidget(self.log_text)
        log_layout.addWidget(self._button('Sao chép nhật ký', self.copy_log))
        log_layout.addWidget(self._button('Xóa nhật ký', lambda: self.log_text.clear()))
        forms.addWidget(log_group)
        forms.addStretch()
        control.setWidget(control_content)
        control.setMinimumWidth(370)
        self.splitter.addWidget(control)

        self.web_panel = QFrame()
        self.web_panel.setObjectName('panel')
        web_layout = QVBoxLayout(self.web_panel)
        web_heading = QHBoxLayout()
        web_heading.addWidget(QLabel('CHATGPT WEB — KẾT NỐI & DỊCH TỰ ĐỘNG'), 1)
        web_heading.addWidget(self._button('⟳', self.reload_web))
        web_heading.addWidget(self._button('✕', self.toggle_web))
        web_layout.addLayout(web_heading)
        self.web_status = QLabel('Nhấn Mở kết nối AI để kiểm tra ChatGPT Web đã sẵn sàng.')
        self.web_status.setWordWrap(True)
        web_layout.addWidget(self.web_status)
        if WEB_AVAILABLE:
            self.web_view = QWebEngineView()
            # Reuse web cookies for manual browsing. Credentials never read by this app.
            from PySide6.QtCore import QStandardPaths
            data_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
            data_dir.mkdir(parents=True, exist_ok=True)
            self.web_profile = QWebEngineProfile('SrtWebChatGPT', self)
            self.web_profile.setPersistentStoragePath(str(data_dir / 'chatgpt_profile'))
            self.web_profile.setCachePath(str(data_dir / 'chatgpt_cache'))
            self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            self.web_page = QWebEnginePage(self.web_profile, self.web_view)
            self.web_view.setPage(self.web_page)
            self.web_view.loadFinished.connect(self._web_loaded_callback)
            web_layout.addWidget(self.web_view, 1)
        else:
            self.web_view = None
            web_layout.addWidget(QLabel('Thiếu QtWebEngine. Không thể thực hiện phép thử nhắn tin trong ứng dụng.'))
            web_layout.addWidget(self._button('Mở ChatGPT trong trình duyệt', lambda: QDesktopServices.openUrl(QUrl('https://chatgpt.com/'))))
        self.web_panel.hide()
        self.splitter.addWidget(self.web_panel)
        self.splitter.setStretchFactor(0, 8)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setStretchFactor(2, 5)
        self.splitter.setSizes([900, 440, 0])
        self.refresh_progress()
        self.refresh_navigation()

    def _style(self):
        self.setStyleSheet('''
            QMainWindow, QWidget { background: #f3f5f7; font: 10pt "Segoe UI"; color: #243142; }
            QLabel#heading { color: #008d83; font-size: 18pt; font-weight: 800; }
            QLabel#subtitle { color: #158578; font-weight: 600; }
            QLabel#status { color: #657285; font-weight: 600; padding: 8px; }
            QLabel#filename { color: #1e567d; font-weight: 600; }
            QFrame#panel { background: #ffffff; border: 1px solid #d6dfe6; }
            QScrollArea#controls { border: 1px solid #d6dfe6; background: #f3f5f7; }
            QGroupBox { background: #ffffff; border: 1px solid #d7dfe4; margin-top: 15px;
                        padding-top: 10px; font-weight: 600; border-radius: 4px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; top: 0px; padding: 1px 3px; }
            QPlainTextEdit, QComboBox, QSpinBox { border: 1px solid #becbd5; border-radius: 3px;
                        background: white; padding: 5px; }
            QPushButton { background: #e9eff2; border: 1px solid #aabdc8; border-radius: 3px;
                          padding: 6px 9px; font-weight: 600; }
            QPushButton:hover { background: #dbeaf1; }
            QPushButton:disabled { color: #929aa5; background: #e9ebee; }
            QPushButton[kind="teal"] { background: #039785; border-color: #017468; color: white; }
            QPushButton[kind="green"] { background: #1aae46; border-color: #168837; color: white; }
            QPushButton[kind="red"] { background: #d93547; border-color: #c31f35; color: white; }
            QPushButton[kind="gold"] { background: #eec35e; border-color: #cda343; }
            QPushButton[kind="light"] { background: #dff4ff; border-color: #69a8c7; }
            QTableView { background: white; gridline-color: #e5ebf0; alternate-background-color: #f7fafc;
                         selection-background-color: #cae9fb; selection-color: #1a2a3a; }
            QHeaderView::section { background: #e7eff4; padding: 7px; border: 1px solid #d4dce3; font-weight: 600; }
            QProgressBar { border: 1px solid #b5cbd0; height: 22px; text-align: center; }
            QProgressBar::chunk { background: #24b55a; }
        ''')

    def log(self, text: str):
        self.log_text.appendPlainText(datetime.now().strftime('%H:%M:%S') + '  ' + text)

    def copy_log(self):
        QApplication.clipboard().setText('SRT WEB v1.3.0\n' + self.log_text.toPlainText())

    def show_notice(self, message: str):
        QMessageBox.information(self, 'Thông báo', message)

    def refresh_navigation(self):
        pages = max(1, (len(self.model.cues)+self.model.page_size-1)//self.model.page_size)
        self.page_box.blockSignals(True)
        self.page_box.clear()
        for page in range(pages):
            self.page_box.addItem(f'{page+1} / {pages}')
        self.page_box.setCurrentIndex(self.model.page)
        self.page_box.blockSignals(False)
        self.page_back.setEnabled(self.model.page > 0)
        self.page_forward.setEnabled(self.model.page < pages-1)

    def set_page(self, page: int):
        pages = max(1, (len(self.model.cues)+self.model.page_size-1)//self.model.page_size)
        if page < 0 or page >= pages:
            return
        self.model.set_page(page)
        self.refresh_navigation()

    def refresh_progress(self):
        total = len(self.model.cues)
        done = sum(1 for c in self.model.cues if c.translation.strip() or not c.source.strip())
        self.table_info.setText(f'{total} dòng phụ đề · {done} dòng đã dịch/xử lý · còn {total-done}')
        self.progress.setValue(round(done*100/total) if total else 0)
        self.progress.setFormat(f'{done}/{total} dòng · %p%')

    def _save_checkpoint(self):
        if self.path and self.source_content:
            try:
                save_progress(self.path, self.source_content, self.model.cues)
            except Exception as exc:
                self.log(f'⚠ Không lưu được tiến độ: {exc}')

    def table_edited(self):
        self._save_checkpoint()
        self.refresh_progress()

    def open_srt(self):
        if self.auto_session:
            self.show_notice('Hãy dừng phiên dịch trước khi mở file khác.')
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Chọn file phụ đề Trung Quốc', '', 'SubRip (*.srt);;Tất cả file (*)')
        if not path:
            return
        try:
            content = read_text(path)
            cues = parse_srt(content)
            count = restore_progress(path, content, cues)
        except Exception as exc:
            QMessageBox.critical(self, 'Lỗi file SRT', str(exc))
            return
        self.path = Path(path)
        self.source_content = content
        self.model.load_cues(cues)
        self.web_batch = []
        self.batch_waiting_for_json = False
        self.filename.setText(f'{self.path.name} — {len(cues)} dòng')
        self.refresh_navigation()
        self.refresh_progress()
        self.log(f'Đã mở {self.path.name} · {len(cues)} ID. Phục hồi {count} dòng từ checkpoint.')

    def save_srt(self):
        if not self.model.cues:
            self.show_notice('Chưa mở file SRT.')
            return
        missing = [c.number for c in self.model.cues if not c.translation.strip() and c.source.strip()]
        if missing:
            confirm = QMessageBox.question(self, 'File chưa dịch đủ',
                 f'Còn {len(missing)} dòng chưa dịch. Nếu tiếp tục, các dòng đó sẽ giữ nguyên tiếng Trung. Vẫn xuất SRT?',
                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                 QMessageBox.StandardButton.No)
            if confirm != QMessageBox.StandardButton.Yes:
                return
        suggested = str(self.path.with_name(self.path.stem + '_vi.srt')) if self.path else 'translated_vi.srt'
        target, _ = QFileDialog.getSaveFileName(self, 'Lưu phụ đề tiếng Việt', suggested, 'SubRip (*.srt)')
        if not target:
            return
        try:
            Path(target).write_text(srt_contents(self.model.cues, include_original_for_missing=True), encoding='utf-8-sig')
            self._save_checkpoint()
            self.log(f'💾 Đã xuất {target}; thiếu bản dịch: {len(missing)} dòng.')
            self.show_notice(f'Đã lưu:\n{target}\nTổng {len(self.model.cues)} mốc thời gian (không bị bỏ sót).')
        except Exception as exc:
            QMessageBox.critical(self, 'Lưu thất bại', str(exc))

    def edit_prompt(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Tùy chỉnh prompt dịch Trung → Việt')
        dialog.resize(720, 490)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Thêm yêu cầu văn phong; khóa JSON, ID và số dòng luôn được tự áp dụng.'))
        editor = QPlainTextEdit()
        editor.setPlainText(self.prompt)
        layout.addWidget(editor)
        controls = QHBoxLayout()
        reset = self._button('Khôi phục prompt mặc định', lambda: editor.setPlainText(DEFAULT_PROMPT))
        controls.addWidget(reset)
        controls.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        controls.addWidget(buttons)
        layout.addLayout(controls)
        editor.textChanged.connect(lambda: self._save_prompt(editor.toPlainText()))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._save_prompt(editor.toPlainText())
            self.log('Đã cập nhật prompt dịch (đã tự lưu).')

    def _save_prompt(self, value: str):
        self.prompt = value.strip() or DEFAULT_PROMPT
        self.settings.setValue('prompt', self.prompt)
        self.settings.sync()

    def _status(self, message: str, color: str = '#657285'):
        self.connection_label.setText(message)
        self.connection_label.setStyleSheet(f'color: {color}; font-weight: 700;')

    def connect_and_open(self):
        """Check that ChatGPT Web and its chat editor are ready."""
        if not WEB_AVAILABLE or self.web_view is None:
            self.show_notice('Máy thiếu QtWebEngine: không thể kiểm tra kết nối trong khung Web. '
                             'Hãy chạy run_windows.bat để cài đúng thư viện.')
            return
        if not self.web_panel.isVisible():
            self.toggle_web()
        self._connection_state = 'looking_for_editor'
        self._connection_deadline = time.monotonic() + self.timeout_spin.value()
        self._probe_busy = False
        self.connect_btn.setEnabled(False)
        self.test_btn.setEnabled(False)
        self._status('◌ Đang kiểm tra ChatGPT Web…', '#ab7700')
        self.web_status.setText('Đang kiểm tra ô chat. Không cần đăng nhập nếu ChatGPT cho phép dùng chế độ khách.')
        self.log('🔌 Bắt đầu kiểm tra Web; không tự gửi lời chào và không sử dụng OpenAI API key.')
        self.connection_timer.start()
        QTimer.singleShot(500, self._probe_web_connection)

    def _end_connection_test(self):
        self.connection_timer.stop()
        self._probe_busy = False
        self.connect_btn.setEnabled(True)
        self.test_btn.setEnabled(True)

    def _connection_failed(self, explanation: str):
        self._end_connection_test()
        self._connection_state = 'failed'
        self._status('● Chưa xác nhận kết nối Web', '#c43140')
        self.web_status.setText(explanation)
        self.log('⚠ Kiểm tra ChatGPT Web không thành công: ' + explanation)
        QMessageBox.warning(self, 'Chưa kiểm tra được kết nối', explanation)

    def _run_web_script(self, script: str, callback):
        """Serialize objects explicitly across the Qt JavaScript/Python boundary."""
        def decoded(value):
            try:
                result = json.loads(value) if isinstance(value, str) else value
            except (TypeError, ValueError):
                result = None
            if isinstance(result, dict) and result.get('scriptError'):
                self.log('⚠ Lỗi đọc Web: ' + str(result['scriptError']))
            callback(result)

        self.web_view.page().runJavaScript(
            '(() => { try { return JSON.stringify(' + script +
            '); } catch (error) { return JSON.stringify({scriptError:String(error)}); } })()', decoded)

    def _probe_web_connection(self):
        if self._connection_state != 'looking_for_editor' or self._probe_busy:
            return
        if time.monotonic() >= self._connection_deadline:
            self._connection_failed('Hết thời gian chờ. Hãy kiểm tra ChatGPT và ô chat trong khung Web, '
                                    'kiểm tra trang đã tải được, rồi nhấn Kết nối lại. '
                                    'Ứng dụng không tự đăng nhập hoặc vượt bước xác minh.')
            return
        if self.web_view is None:
            return
        self._probe_busy = True
        state = self._connection_state
        self._run_web_script(PROBE_JS, lambda result: self._on_probe(result, state))

    def _on_probe(self, probe, original_state: str):
        self._probe_busy = False
        if original_state != self._connection_state:
            return
        if isinstance(probe, dict) and probe.get('cooldown'):
            self._end_connection_test()
            self._connection_state = 'cooldown'
            self._status('● ChatGPT đang yêu cầu chờ', '#ab7700')
            self.web_status.setText('ChatGPT yêu cầu thử lại sau ' + str(probe.get('clock', 'thời gian trên Web')) + '. Bắt đầu dịch sẽ giữ tiến độ và chờ theo thông báo.')
            return
        if not isinstance(probe, dict) or not probe.get('site'):
            self.web_status.setText('Đang chờ chuyển đến chatgpt.com; có thể đang ở trang đăng nhập.')
            return
        if not probe.get('editor'):
            self.web_status.setText('Đang chờ ô chat sẵn sàng; chế độ khách được hỗ trợ khi trang cho phép.')
            return
        self._end_connection_test()
        self._connection_state = 'success'
        self._status('● ChatGPT Web đã kết nối', '#168b50')
        self.web_status.setText('✓ Kết nối thành công: ChatGPT Web và ô chat đã sẵn sàng.')
        self.log('✅ KẾT NỐI WEB THÀNH CÔNG: đã xác nhận trang và ô chat, không gửi tin nhắn.')
        self.show_notice('✅ KẾT NỐI CHATGPT WEB THÀNH CÔNG!\n\n'
                         'Đã xác nhận ChatGPT Web và ô chat đã sẵn sàng.\n'
                         'Ứng dụng không tự động gửi lời chào.\n\n'
                         'Lưu ý: đây là kiểm tra giao diện Web, không phải kết nối API dịch tự động.')

    def toggle_web(self):
        showing = not self.web_panel.isVisible()
        self.web_panel.setVisible(showing)
        self.web_btn.setText('🙈 Ẩn Web' if showing else '🌐 Hiện Web')
        if showing:
            self.splitter.setSizes([710, 390, 540])
            if self.web_view and not self._web_loaded:
                self._web_loaded = True
                self.web_view.setUrl(QUrl('https://chatgpt.com/'))
                self.log('Đang tải trang ChatGPT (có thể cần đăng nhập riêng).')
        else:
            self.splitter.setSizes([950, 490, 0])

    def reload_web(self):
        if self.web_view:
            self.web_view.reload()

    def _web_loaded_callback(self, loaded: bool):
        if loaded:
            self.log('✓ Trang Web đã tải. Có thể dùng chế độ khách khi ô chat sẵn sàng.')
            if self._connection_state == 'looking_for_editor':
                QTimer.singleShot(450, self._probe_web_connection)
            elif self._connection_state == 'idle':
                self.web_status.setText('Đã tải trang. Nhấn Kết nối để kiểm tra ô chat sẵn sàng.')
        else:
            self.web_status.setText('Không tải được trang; hãy kiểm tra mạng hoặc đăng nhập Web.')
            self.log('⚠ Trang Web chưa tải được; có thể cần trình duyệt ngoài.')

    def _missing(self):
        return [cue for cue in self.model.cues if not cue.translation.strip() and cue.source.strip()]

    def start_translation(self):
        """Send SRT batches to ChatGPT Web and import each JSON response."""
        if not self.model.cues:
            self.show_notice('Hãy mở file SRT trước.')
            return
        if not WEB_AVAILABLE or self.web_view is None:
            self.show_notice('Máy thiếu QtWebEngine, không thể dịch tự động.')
            return
        if self.auto_session:
            self.show_notice('Đang có phiên dịch cuốn chiếu.')
            return
        if not self._missing():
            self.show_notice('Tất cả dòng đã có bản dịch.')
            return
        self.auto_retries = {}
        self.auto_session = True
        self.auto_paused = False
        self.batch_waiting_for_json = False
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.open_btn.setEnabled(False)
        if not self.web_panel.isVisible():
            self.toggle_web()
        self.log(f'Bắt đầu dịch tự động: mỗi lô {self.batch_spin.value()} dòng.')
        self._queue_next_auto_batch()

    def _queue_next_auto_batch(self):
        if not self.auto_session or self.auto_paused or self.batch_waiting_for_json or self.auto_send_state == 'cooldown':
            return
        if not self._missing():
            self.log('✅ ĐÃ HOÀN TẤT: tất cả ID có bản dịch.')
            self.stop_translation()
            self.show_notice('Đã có bản dịch cho tất cả ID. Nhấn “Lưu SRT” để xuất.')
            return
        self.auto_generation += 1
        self.auto_received = None
        size = 1 if self._missing()[0].number in self.auto_retries else self.batch_spin.value()
        self.auto_batch = self._missing()[:size]
        self.batch_waiting_for_json = True
        prompt = make_batch_prompt(self.auto_batch, self.prompt)
        self.auto_deadline = time.monotonic() + self.timeout_spin.value()
        self.auto_hard_deadline = time.monotonic() + 900
        self.auto_last_error = ''
        self.auto_editor_deadline = time.monotonic() + self.timeout_spin.value()
        self.auto_editor_wait_logged = False
        self.web_status.setText(f'Đang gửi lô {self.auto_batch[0].number}–{self.auto_batch[-1].number}…')
        self._run_batch_script(PROBE_JS, lambda result: self._on_batch_probe(result, prompt))

    def _run_batch_script(self, script, callback):
        generation = self.auto_generation
        completed = False
        def current(result):
            nonlocal completed
            if completed:
                return
            completed = True
            if self.auto_session and self.auto_generation == generation:
                if isinstance(result, dict) and result.get('cooldown'):
                    self._wait_for_service(result)
                else:
                    callback(result)
        def stalled():
            if not completed and self.auto_session and self.auto_generation == generation:
                current({'scriptError':'QtWebEngine không trả kết quả trong 10 giây.'})
        QTimer.singleShot(10000, stalled)
        self._run_web_script(script, current)

    def _wait_for_service(self, result):
        retry_at = result.get('retryAt')
        if (type(retry_at) not in (int, float) or not 0 < retry_at - time.time() <= 86400):
            self._auto_failed('ChatGPT yêu cầu chờ nhưng chưa xác định được thời điểm thử lại. Bản dịch đã lưu được giữ nguyên; kiểm tra thông báo trên Web.')
            return
        self._save_checkpoint()
        self.auto_generation += 1
        self.auto_poll_busy = False
        self.auto_send_state = 'cooldown'
        self.batch_waiting_for_json = False
        self.auto_batch = []
        self.auto_received = None
        self.next_batch_timer.stop()
        self.service_wait_until = retry_at
        self.log('⏳ ChatGPT yêu cầu chờ đến ' + datetime.fromtimestamp(retry_at).strftime('%H:%M') +
                 '. Giữ tiến độ; không gửi thêm trong thời gian chờ.')
        self.service_wait_timer.start()
        self._tick_service_wait()

    def _tick_service_wait(self):
        if not self.auto_session or self.auto_send_state != 'cooldown':
            self.service_wait_timer.stop()
            return
        remaining = max(0, int(self.service_wait_until - time.time()) + 1)
        if time.time() >= self.service_wait_until:
            self.service_wait_timer.stop()
            self.auto_send_state = 'idle'
            self.log('Đã đến giờ thử lại do ChatGPT thông báo; tiếp tục các ID còn thiếu khi ô chat sẵn sàng.')
            if not self.auto_paused:
                self._queue_next_auto_batch()
            return
        self.web_status.setText('ChatGPT yêu cầu chờ đến ' +
            datetime.fromtimestamp(self.service_wait_until).strftime('%H:%M') +
            f' — còn {remaining // 60} phút {remaining % 60} giây. Đã giữ tiến độ.')

    def _schedule_poll(self, delay=1200):
        generation = self.auto_generation
        def current():
            if self.auto_session and self.auto_generation == generation:
                self._poll_batch_response()
        QTimer.singleShot(delay, current)

    def _on_batch_probe(self, result, prompt: str):
        if not self.auto_session:
            return
        if isinstance(result, dict) and result.get('scriptError'):
            self._auto_failed('Không kiểm tra được ô chat: ' + str(result['scriptError']))
            return
        if not isinstance(result, dict) or not result.get('site') or not result.get('editor'):
            if time.monotonic() >= self.auto_editor_deadline:
                self._auto_failed('Hết thời gian chờ ô chat có thể nhập. Đăng nhập không bảo đảm giao diện đã sẵn sàng; kiểm tra trang đã tải xong, đóng hộp thoại trên Web hoặc xem thông báo của trang. Bản dịch đã lưu được giữ nguyên.')
                return
            self.web_status.setText('Đang chờ giao diện ChatGPT và ô chat sẵn sàng…')
            if not self.auto_editor_wait_logged:
                self.log('◌ Đang chờ ô chat có thể nhập; chưa gửi lô và chưa kết luận lỗi đăng nhập.')
                self.auto_editor_wait_logged = True
            generation = self.auto_generation
            def probe_again():
                if self.auto_session and generation == self.auto_generation:
                    self._run_batch_script(PROBE_JS, lambda value: self._on_batch_probe(value, prompt))
            QTimer.singleShot(750, probe_again)
            return
        self.auto_baseline = int(result.get('assistantCount') or 0)
        self.auto_baseline_text = result.get('lastText', '')
        self.auto_dom_chars = None
        self.auto_last_response = ''
        self.auto_stable_reads = 0
        if WEB_BRIDGE.native:
            try:
                script = WEB_BRIDGE.send_js(prompt, self.auto_generation)
            except Exception as error:
                self._auto_failed('Module ai_chatgpt không tạo được lệnh gửi: ' + str(error))
                return
            self.auto_send_state = 'native_pending'
            self.auto_send_deadline = time.monotonic() + min(30, self.timeout_spin.value())
            self._run_batch_script(script, self._on_native_queued)
        else:
            self._run_batch_script(make_send_message_js(prompt), self._on_batch_prepared)

    def _on_native_queued(self, result):
        if not isinstance(result, dict) or result.get('ok') is not True:
            self._auto_failed('Module ai_chatgpt không điền/gửi được lô. Kiểm tra ô chat trên Web.')
            return
        self.log('Module ai_chatgpt đã chuẩn bị lô; chờ xác nhận ô nhập được xóa sau khi gửi.')
        self._schedule_native_ack()

    def _schedule_native_ack(self):
        generation = self.auto_generation
        def confirm():
            if self.auto_session and self.auto_generation == generation and self.auto_send_state == 'native_pending':
                if time.monotonic() >= self.auto_send_deadline:
                    self._auto_failed('Module ai_chatgpt chưa gửi được lô trong 30 giây. Không tự gửi lại để tránh trùng; bản dịch đã lưu được giữ nguyên.')
                    return
                self._run_batch_script(NATIVE_SEND_ACK_JS, self._on_native_ack)
        QTimer.singleShot(750, confirm)

    def _on_native_ack(self, result):
        if not self.auto_session or self.auto_send_state != 'native_pending':
            return
        if isinstance(result, dict) and result.get('pending'):
            self._schedule_native_ack()
        elif isinstance(result, dict) and result.get('ok'):
            self.auto_send_state = 'checking'
            self._on_batch_sent(result)
        else:
            self._auto_failed('Không xác nhận được thao tác gửi của ai_chatgpt; không tự gửi lại.')

    def _cancel_native_pending(self):
        if WEB_BRIDGE.native and self.auto_send_state == 'native_pending' and self.web_view is not None:
            self.web_view.page().runJavaScript('window.__srtNativeSendId = null;')

    def _on_batch_prepared(self, result):
        if not isinstance(result, dict) or not result.get('ok'):
            self._auto_failed('Không điền được nội dung lô vào ô chat.')
            return
        self.auto_send_state = 'waiting'
        self.auto_send_deadline = time.monotonic() + min(30, self.timeout_spin.value())
        self.auto_send_reason = ''
        self._schedule_send(350)

    def _schedule_send(self, delay=500):
        generation = self.auto_generation
        def send():
            if (self.auto_session and generation == self.auto_generation and
                    self.auto_send_state == 'waiting'):
                if time.monotonic() >= self.auto_send_deadline:
                    self._auto_failed('Đã chờ nút gửi nhưng chưa sẵn sàng: ' + self.auto_send_reason +
                                      ' Bản dịch đã nhận vẫn được lưu. Kiểm tra thông báo thực tế trên Web trước khi thử lại.')
                    return
                self.auto_send_state = 'checking'
                self._run_batch_script(SEND_MESSAGE_JS, self._on_batch_sent)
        QTimer.singleShot(delay, send)

    def _on_batch_sent(self, result):
        if not self.auto_session or self.auto_send_state != 'checking':
            return
        if not isinstance(result, dict) or not result.get('ok'):
            reason = result.get('why', result.get('scriptError', 'Không kiểm tra được nút gửi.')) if isinstance(result, dict) else 'Không kiểm tra được nút gửi.'
            if isinstance(result, dict) and result.get('retryable') is True:
                self.auto_send_state = 'waiting'
                if reason != self.auto_send_reason:
                    self.log('◌ Đang chờ gửi: ' + reason)
                self.auto_send_reason = reason
                self.web_status.setText('Đang chờ nút gửi sẵn sàng (tối đa 30 giây): ' + reason)
                self._schedule_send()
                return
            self._auto_failed(reason)
            return
        self.auto_send_state = 'sent'
        self.auto_deadline = time.monotonic() + self.timeout_spin.value()
        self.auto_hard_deadline = time.monotonic() + 900
        self.log(f'✓ Đã bấm gửi lô {self.auto_batch[0].number}–{self.auto_batch[-1].number}; đang chờ JSON.')
        self._schedule_poll(1500)

    def _poll_batch_response(self):
        if not self.auto_session or not self.batch_waiting_for_json or self.auto_poll_busy:
            return
        if time.monotonic() >= min(self.auto_deadline, self.auto_hard_deadline):
            self._auto_failed(self.auto_last_error or 'Chưa đọc được bản dịch từ giao diện Web. Nếu bên phải đã có JSON, hãy gửi nhật ký (bao gồm dòng Cấu trúc Web) để kiểm tra bộ đọc; nếu trang báo giới hạn, cần xử lý yêu cầu của ChatGPT.')
            return
        self.auto_poll_busy = True
        self._run_batch_script(READ_LATEST_RESPONSE_JS, self._on_batch_response)

    def _on_batch_response(self, result):
        self.auto_poll_busy = False
        if not self.auto_session or not self.batch_waiting_for_json:
            return
        text = result.get('text', '') if isinstance(result, dict) else ''
        count = result.get('assistantCount', 0) if isinstance(result, dict) else 0
        if isinstance(result, dict) and result.get('scriptError'):
            self._auto_failed('Không đọc được giao diện Web: ' + str(result['scriptError']))
            return
        generating = bool(result.get('generating')) if isinstance(result, dict) else True
        diagnostics = result.get('diagnostics', {}) if isinstance(result, dict) else {}
        chars = diagnostics.get('conversationChars') if isinstance(diagnostics, dict) else None
        if isinstance(chars, int) and chars > 0:
            if generating and chars != getattr(self, 'auto_dom_chars', None):
                self.auto_deadline = time.monotonic() + self.timeout_spin.value()
            self.auto_dom_chars = chars
        summary = (count, len(text), generating, str(result.get('diagnostics', {})) if isinstance(result, dict) else '')
        if summary != self.auto_diagnostic:
            self.auto_diagnostic = summary
            self.log(f'Web: {count} phản hồi; {len(text)} ký tự; đang tạo: {generating}.')
            if isinstance(result, dict) and result.get('diagnostics'):
                self.log('Cấu trúc Web: ' + json.dumps(result['diagnostics'], ensure_ascii=False))
        changed = result.get('lastText', '') != self.auto_baseline_text if isinstance(result, dict) else False
        if isinstance(result, dict) and result.get('site') is False:
            self._auto_failed('Trang hiện tại không còn là ChatGPT. Bản dịch hợp lệ đã nhận vẫn được lưu; kiểm tra Web trước khi tiếp tục.')
            return
        # A guest page can remove a reply immediately after streaming. Validate
        # and checkpoint a complete batch on its FIRST visible read. Never
        # send the next batch until generation has finished.
        if text and (count > self.auto_baseline or changed):
            try:
                received = check_translations(self.auto_batch, extract_json(text))
            except (ValueError, TypeError):
                received = None
            if received is not None and received != self.auto_received:
                self.auto_received = received
                self.auto_deadline = time.monotonic() + self.timeout_spin.value()
                self.apply_translations(received)
                self.log(f'✓ Đã lưu {len(received)} ID hợp lệ ngay khi đọc được; chờ Web hoàn tất.')
        if self.auto_received is not None:
            if generating:
                # Preserve the existing fallback for a stale streaming CSS
                # class, while a visible Stop control always blocks sending.
                if text == self.auto_last_response:
                    self.auto_stable_reads += 1
                else:
                    self.auto_last_response = text
                    self.auto_stable_reads = 1
                if (not isinstance(result, dict) or result.get('stopVisible', True) or
                        self.auto_stable_reads < 4):
                    self._schedule_poll()
                    return
            self._accept_batch(self.auto_received)
            return
        if (count <= self.auto_baseline and not changed) or not text:
            self.auto_last_response = ''
            self.auto_stable_reads = 0
            self._schedule_poll()
            return
        if text == self.auto_last_response:
            self.auto_stable_reads += 1
        else:
            self.auto_last_response = text
            self.auto_stable_reads = 1
            self.auto_deadline = time.monotonic() + self.timeout_spin.value()
            self.web_status.setText(f'Đang nhận phản hồi: {len(text)} ký tự…')
        if self.auto_stable_reads < 2 or (generating and
                (not isinstance(result, dict) or result.get('stopVisible', True) or self.auto_stable_reads < 4)):
            self._schedule_poll()
            return
        try:
            parsed = extract_json(text)
        except (ValueError, TypeError) as exc:
            self.auto_last_error = f'Không đọc được JSON phản hồi: {exc}'
            self.web_status.setText(self.auto_last_error)
            self._schedule_poll()
            return
        # Retain valid cues even when another cue has wrong line count or is
        # missing. Only rejected cues are retried, individually and boundedly.
        mapping, errors = {}, []
        rows = parsed.get('items')
        if not isinstance(rows, list):
            self.auto_last_error = 'JSON phản hồi thiếu danh sách items.'
            self._schedule_poll()
            return
        if generating:
            try:
                check_translations(self.auto_batch, parsed)
            except (ValueError, TypeError):
                self._schedule_poll()
                return
        for cue in self.auto_batch:
            matches = [row for row in rows if isinstance(row, dict) and
                       type(row.get('id')) is int and row['id'] == cue.number]
            try:
                mapping.update(check_translations([cue], {'items': matches}))
            except (ValueError, TypeError) as exc:
                errors.append(f'ID {cue.number}: {exc}')
                self.auto_retries[cue.number] = self.auto_retries.get(cue.number, 0) + 1
        if errors:
            self.log('⚠ ' + '; '.join(errors[:3]))
        self._accept_batch(mapping, errors)

    def _accept_batch(self, mapping, errors=()):
        for number in mapping:
            self.auto_retries.pop(number, None)
        self.apply_translations(mapping)
        self.log(f'✓ Đã nhận tự động {len(mapping)} ID.')
        self.web_status.setText(f'Đã cập nhật {len(mapping)} dòng vào bảng dịch.')
        if any(self.auto_retries.get(c.number, 0) > 2 for c in self.auto_batch if c.number not in mapping):
            self._auto_failed('Phản hồi vẫn sai sau 2 lần thử lại. ' + '; '.join(errors[:3]))
            return
        self.batch_waiting_for_json = False
        self.auto_batch = []
        if self._missing():
            self.next_batch_timer.start(max(0, self.delay_spin.value() * 1000))
        else:
            self._finish_auto_session()

    def _auto_failed(self, message: str):
        self.batch_waiting_for_json = False
        self.stop_translation()
        self.web_status.setText('Đã dừng: ' + message)
        self.log('⚠ Dịch tự động thất bại: ' + message)
        QMessageBox.warning(self, 'Dịch tự động thất bại', message)

    def _finish_auto_session(self):
        self.stop_translation()
        self.show_notice('Đã dịch tự động toàn bộ file SRT. Nhấn “Lưu SRT” để xuất.')

    def apply_translations(self, mapping: dict[int, str]):
        for number, vi in mapping.items():
            if 1 <= number <= len(self.model.cues):
                self.model.cues[number-1].translation = vi
        last = max(mapping) if mapping else 1
        self.set_page((last-1)//self.model.page_size)
        for number in mapping:
            self.model.refresh_number(number)
        if mapping:
            row = (last-1)%self.model.page_size
            self.table.scrollTo(self.model.index(row, 3), QTableView.ScrollHint.PositionAtCenter)
        self.refresh_progress()
        self._save_checkpoint()

    def toggle_pause(self):
        if not self.auto_session:
            return
        self.auto_paused = not self.auto_paused
        self.pause_btn.setText('▶ TIẾP TỤC' if self.auto_paused else '⏸ TẠM DỪNG')
        if self.auto_paused:
            self.next_batch_timer.stop()
            self.log('⏸ Tạm dừng: không chuẩn bị lô mới. Dữ liệu đã dịch được giữ nguyên.')
        else:
            self.log('▶ Tiếp tục: chuẩn bị lô kế tiếp khi lô hiện tại hoàn tất.')
            if not self.batch_waiting_for_json:
                self._queue_next_auto_batch()

    def stop_translation(self):
        self._cancel_native_pending()
        self.service_wait_timer.stop()
        self.auto_send_state = 'idle'
        self.auto_received = None
        self.auto_generation += 1
        self.auto_poll_busy = False
        self.next_batch_timer.stop()
        self.auto_session = False
        self.auto_paused = False
        self.batch_waiting_for_json = False
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.open_btn.setEnabled(True)
        self.pause_btn.setText('⏸ TẠM DỪNG')
        self._save_checkpoint()
        self.log('■ Đã kết thúc phiên. Các ID đã dịch vẫn được lưu lại.')


    def closeEvent(self, event):
        self._cancel_native_pending()
        self.service_wait_timer.stop()
        self.auto_generation += 1
        self.auto_session = False
        self.auto_send_state = 'idle'
        self.connection_timer.stop()
        self.next_batch_timer.stop()
        self._save_checkpoint()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = App()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
