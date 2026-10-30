"""Asynchronous Ollama client. Subtitle requests stay on the loopback interface."""
from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

from srt_engine import make_batch_prompt

DEFAULT_MODEL = 'qwen3:4b'
DEFAULT_URL = 'http://127.0.0.1:11434'


def local_model_name(value: str) -> str:
    value = value.strip()
    if (len(value) > 200 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?', value) or
            value.lower().endswith(('-cloud', ':cloud'))):
        raise ValueError('Chọn mô hình chạy cục bộ, ví dụ qwen3:4b; không dùng mô hình cloud.')
    return value


def translation_payload(model, cues, prompt):
    return {
        'model': local_model_name(model), 'stream': True, 'think': False,
        'keep_alive': '10m',
        'messages': [{'role': 'user', 'content': make_batch_prompt(cues, prompt)}],
        'format': {
            'type': 'object', 'required': ['items'], 'additionalProperties': False,
            'properties': {'items': {
                'type': 'array', 'minItems': len(cues), 'maxItems': len(cues),
                'items': {'type': 'object', 'required': ['id', 'vi'], 'additionalProperties': False,
                          'properties': {'id': {'type': 'integer', 'enum': [c.number for c in cues]},
                                         'vi': {'type': 'string'}}}}},
        },
        'options': {'temperature': 0.2, 'num_ctx': 8192, 'num_predict': 4096},
    }


class OllamaClient(QObject):
    models_ready = Signal(list)
    pull_progress = Signal(str)
    model_pulled = Signal(str)
    translation_progress = Signal(int)
    translated = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None, base_url=DEFAULT_URL):
        super().__init__(parent)
        url = QUrl(base_url)
        if (url.scheme() != 'http' or url.host() not in ('127.0.0.1', 'localhost', '::1') or
                url.userName() or url.password() or url.path() not in ('', '/') or
                url.hasQuery() or url.hasFragment() or not url.isValid()):
            raise ValueError('Ollama phải chạy trên máy này (localhost).')
        self.base_url = base_url.rstrip('/')
        self.manager = QNetworkAccessManager(self)
        # A system HTTP proxy must never receive local subtitle requests.
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.reply = None
        self.operation = ''
        self._serial = 0
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(lambda: self._fail('Ollama không có tiến triển trong thời gian chờ. Giảm số dòng/lô hoặc tăng thời gian chờ.'))
        self._hard = QTimer(self)
        self._hard.setSingleShot(True)
        self._hard.timeout.connect(lambda: self._fail('Ollama đã vượt thời gian xử lý tối đa. Giảm số dòng/lô.'))

    @property
    def busy(self):
        return bool(self.operation)

    def cancel(self):
        self._serial += 1
        self._idle.stop()
        self._hard.stop()
        old, self.reply = self.reply, None
        self.operation = ''
        if old is not None:
            old.abort()
            old.deleteLater()

    def _fail(self, message):
        self.cancel()
        self.failed.emit(message)

    def _begin(self, operation, timeout):
        if self.busy:
            raise ValueError('Ollama đang xử lý yêu cầu khác. Hãy chờ hoặc bấm Dừng Ollama.')
        self.operation = operation
        self._timeout = timeout
        self._hard.start(3600000 if operation == 'pull' else max(900000, timeout * 1000))
        self._buffer = bytearray()
        self._text = ''
        self._done = False
        self._pull_status = ''

    def _request(self, endpoint, data=None, stream=False):
        request = QNetworkRequest(QUrl(self.base_url + endpoint))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, 'application/json')
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = self.manager.get(request) if data is None else self.manager.post(
            request, json.dumps(data, ensure_ascii=False).encode('utf-8'))
        self.reply = reply
        serial = self._serial
        reply.readyRead.connect(lambda: self._read(reply, serial, stream))
        reply.finished.connect(lambda: self._finished(reply, serial, endpoint, stream))
        self._idle.start(self._timeout * 1000)

    def refresh_models(self):
        self._begin('models', 10)
        self._request('/api/tags')

    def pull_model(self, model):
        model = local_model_name(model)
        self._begin('pull', 120)
        self._model = model
        self._request('/api/pull', {'model': self._model, 'stream': True}, stream=True)

    def translate(self, model, cues, prompt, timeout=600):
        payload = translation_payload(model, cues, prompt)
        self._begin('translate', timeout)
        self._payload = payload
        self._request('/api/show', {'model': self._payload['model']})

    def _current(self, reply, serial):
        return self.reply is reply and self._serial == serial and self.busy

    def _read(self, reply, serial, stream):
        if not self._current(reply, serial):
            return
        chunk = bytes(reply.readAll())
        if chunk:
            self._idle.start(self._timeout * 1000)
        self._buffer.extend(chunk)
        if len(self._buffer) > 2_000_000:
            self._fail('Phản hồi Ollama quá lớn hoặc không đúng định dạng.')
            return
        if stream:
            while b'\n' in self._buffer and self._current(reply, serial):
                line, _, rest = self._buffer.partition(b'\n')
                self._buffer = bytearray(rest)
                self._packet(line)

    def _packet(self, line):
        if not line.strip():
            return
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('JSON không phải object')
            if value.get('error'):
                self._fail('Ollama: ' + str(value['error'])[:500])
                return
            if self.operation == 'pull':
                status = str(value.get('status', 'Đang tải mô hình'))
                total, completed = value.get('total'), value.get('completed')
                if type(total) is int and total > 0 and type(completed) is int:
                    status += f' — {min(100, completed * 100 // total)}%'
                self._done = value.get('status') == 'success'
                if status != self._pull_status:
                    self._pull_status = status
                    self.pull_progress.emit(status)
            else:
                message = value.get('message', {})
                part = message.get('content', '')
                if not isinstance(part, str):
                    raise ValueError('Nội dung phản hồi không phải văn bản')
                self._text += part
                if len(self._text) > 500000:
                    raise ValueError('Nội dung phản hồi quá lớn')
                self._done = value.get('done') is True
                self.translation_progress.emit(len(self._text))
        except (ValueError, TypeError, AttributeError) as error:
            self._fail('Không đọc được dữ liệu Ollama: ' + str(error)[:300])

    def _finished(self, reply, serial, endpoint, stream):
        if not self._current(reply, serial):
            return
        self._read(reply, serial, stream)
        if not self._current(reply, serial):
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is not None and not 200 <= status < 300:
            detail = ''
            try:
                detail = str(json.loads(self._buffer).get('error', ''))[:500]
            except (ValueError, AttributeError):
                pass
            self._fail(f'Ollama HTTP {status}: ' + (detail or 'Không xử lý được yêu cầu.') +
                       (' Hãy tải mô hình đã chọn trước.' if status == 404 else ''))
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._fail('Không kết nối được Ollama trên máy. Cài và mở Ollama, rồi bấm Kiểm tra Ollama. ' + reply.errorString())
            return
        if stream and self._buffer.strip():
            self._packet(bytes(self._buffer))
        if not self._current(reply, serial):
            return
        try:
            if endpoint == '/api/show':
                info = json.loads(self._buffer)
                if not isinstance(info, dict):
                    raise ValueError('Thông tin mô hình không hợp lệ.')
                if info.get('remote_host') or info.get('remote_model'):
                    raise ValueError('Mô hình này chạy trên cloud. Hãy tải mô hình cục bộ như qwen3:4b.')
                capabilities = info.get('capabilities')
                if capabilities is not None and 'completion' not in capabilities:
                    raise ValueError('Mô hình này không hỗ trợ sinh bản dịch.')
                self._buffer.clear()
                self.reply = None
                reply.deleteLater()
                self._request('/api/chat', self._payload, stream=True)
                return
            if self.operation == 'models':
                info = json.loads(self._buffer)
                models = info.get('models')
                if not isinstance(models, list):
                    raise ValueError('Thiếu danh sách models từ Ollama.')
                names = []
                for model in models:
                    if not isinstance(model, dict) or model.get('remote_host') or model.get('remote_model'):
                        continue
                    try:
                        names.append(local_model_name(model.get('name', '')))
                    except (ValueError, AttributeError):
                        continue
                self.cancel()
                self.models_ready.emit(sorted(set(names)))
            elif not self._done:
                raise ValueError('Luồng Ollama đã kết thúc trước khi hoàn tất. Bản dịch dở chưa được nhập; bấm Bắt đầu để thử lại phần còn thiếu.')
            elif self.operation == 'pull':
                model = self._model
                self.cancel()
                self.model_pulled.emit(model)
            else:
                text = self._text
                self.cancel()
                self.translated.emit(text)
        except (ValueError, TypeError, AttributeError) as error:
            self._fail(str(error))
