"""Asynchronous Gemini Developer API client; API keys stay in request headers."""
from __future__ import annotations

import json
import os
import re

from PySide6.QtCore import QObject, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

from srt_engine import make_batch_prompt

API_URL = 'https://generativelanguage.googleapis.com/v1beta'
DEFAULT_MODEL = 'gemini-2.5-flash'


def model_name(value):
    value = value.strip().removeprefix('models/')
    if not re.fullmatch(r'gemini-[A-Za-z0-9._-]+', value):
        raise ValueError('Nhập tên mô hình Gemini hợp lệ hoặc chọn từ danh sách đã kiểm tra.')
    return value


def api_key(value):
    value = value.strip()
    if not value or not value.isascii() or any(char.isspace() or ord(char) < 33 for char in value):
        raise ValueError('Nhập Gemini API key từ Google AI Studio trước khi kết nối hoặc dịch.')
    return value


def translation_payload(cues, prompt):
    return {
        'contents': [{'role': 'user', 'parts': [{'text': make_batch_prompt(cues, prompt)}]}],
        'generationConfig': {
            'temperature': 0.2,
            'responseMimeType': 'application/json',
            'responseSchema': {
                'type': 'OBJECT', 'required': ['items'],
                'properties': {'items': {
                    'type': 'ARRAY', 'minItems': len(cues), 'maxItems': len(cues),
                    'items': {'type': 'OBJECT', 'required': ['id', 'vi'],
                              'properties': {'id': {'type': 'INTEGER'}, 'vi': {'type': 'STRING'}}},
                }},
            },
        },
    }


class GeminiClient(QObject):
    models_ready = Signal(list)
    translated = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        # Qt does not consistently inherit HTTPS_PROXY on Linux. Preserve the
        # cloud runtime's supported proxy route; otherwise use Qt's OS defaults.
        proxy_url = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        if proxy_url:
            url = QUrl(proxy_url)
            if url.scheme() == 'http' and url.host():
                self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy,
                    url.host(), url.port(8080), url.userName(), url.password()))
        self.reply = None
        self.operation = ''
        self._serial = 0
        self._api_key = ''
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._fail(
            'Gemini quá thời gian chờ. Tiến độ đã nhận được giữ; yêu cầu không tự gửi lại.'))

    @property
    def busy(self):
        return bool(self.operation)

    def cancel(self):
        self._serial += 1
        self._timer.stop()
        old, self.reply = self.reply, None
        self.operation = ''
        self._api_key = ''
        if old is not None:
            old.abort()
            old.deleteLater()

    def _fail(self, message):
        self.cancel()
        self.failed.emit(message)

    def _begin(self, operation, key, timeout):
        if self.busy:
            raise ValueError('Gemini đang xử lý yêu cầu khác. Hãy chờ hoặc bấm Dừng Gemini.')
        self._api_key = api_key(key)
        self.operation = operation
        self._timer.start(max(1, int(timeout * 1000)))

    def refresh_models(self, key):
        self._begin('models', key, 30)
        self._models = set()
        self._page_tokens = set()
        self._request('/models')

    def translate(self, key, model, cues, prompt, timeout=120):
        model = model_name(model)
        payload = translation_payload(cues, prompt)
        self._begin('translate', key, timeout)
        self._request('/models/' + model + ':generateContent', payload)

    def _request(self, endpoint, data=None, page_token=''):
        url = QUrl(API_URL + endpoint)
        if page_token:
            query = QUrlQuery()
            query.addQueryItem('pageToken', page_token)
            url.setQuery(query)
        request = QNetworkRequest(url)
        request.setRawHeader(b'x-goog-api-key', self._api_key.encode('ascii'))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, 'application/json')
        # Never forward the key or subtitle payload to a redirect destination.
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = self.manager.get(request) if data is None else self.manager.post(
            request, json.dumps(data, ensure_ascii=False).encode('utf-8'))
        self.reply = reply
        self._buffer = bytearray()
        serial = self._serial
        reply.readyRead.connect(lambda: self._read(reply, serial))
        reply.finished.connect(lambda: self._finished(reply, serial))

    def _current(self, reply, serial):
        return self.reply is reply and self._serial == serial and self.busy

    def _read(self, reply, serial):
        if self._current(reply, serial):
            self._buffer.extend(bytes(reply.readAll()))
            if len(self._buffer) > 2_000_000:
                self._fail('Phản hồi Gemini quá lớn. Giảm số dòng mỗi lô.')

    def _finished(self, reply, serial):
        if not self._current(reply, serial):
            return
        self._read(reply, serial)
        if not self._current(reply, serial):
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is not None and not 200 <= status < 300:
            # Do not log arbitrary server messages: they can echo the API key.
            messages = {
                400: 'Yêu cầu hoặc API key không hợp lệ. Kiểm tra key và mô hình trong Google AI Studio.',
                401: 'API key không hợp lệ. Tạo hoặc kiểm tra key trong Google AI Studio.',
                403: 'Key không có quyền truy cập. Kiểm tra hạn chế key, dự án và khu vực được hỗ trợ.',
                404: 'Không tìm thấy mô hình. Bấm kiểm tra key / đọc mô hình rồi chọn lại.',
                429: 'Đã hết hạn mức hoặc gửi quá nhanh. Kiểm tra quota trong Google AI Studio, chờ rồi tiếp tục.',
            }
            self._fail(f'Gemini HTTP {status}: ' + messages.get(status,
                'Dịch vụ chưa xử lý được yêu cầu. Kiểm tra mạng hoặc thử lại sau.') +
                ' Ứng dụng không tự gửi lại yêu cầu này.')
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._fail('Không kết nối được Gemini. Kiểm tra Internet, proxy và chứng chỉ TLS. '
                       'Yêu cầu không tự gửi lại.')
            return
        try:
            value = json.loads(self._buffer)
            if not isinstance(value, dict) or value.get('error'):
                raise ValueError('Gemini trả dữ liệu không hợp lệ.')
            if self.operation == 'models':
                models = value.get('models')
                if not isinstance(models, list):
                    raise ValueError('Gemini không trả danh sách mô hình.')
                for model in models:
                    if not isinstance(model, dict) or 'generateContent' not in (model.get('supportedGenerationMethods') or []):
                        continue
                    try:
                        self._models.add(model_name(model.get('name', '')))
                    except (ValueError, AttributeError):
                        continue
                token = value.get('nextPageToken', '')
                if token:
                    if not isinstance(token, str) or len(token) > 4096 or token in self._page_tokens or len(self._page_tokens) >= 20:
                        raise ValueError('Phân trang danh sách mô hình Gemini không hợp lệ.')
                    self._page_tokens.add(token)
                    self.reply = None
                    reply.deleteLater()
                    self._request('/models', page_token=token)
                    return
                names = sorted(self._models)
                self.cancel()
                self.models_ready.emit(names)
                return
            if value.get('promptFeedback', {}).get('blockReason'):
                raise ValueError('Gemini từ chối nội dung lô này. Chưa nhập bản dịch; kiểm tra phụ đề và prompt.')
            candidates = value.get('candidates')
            if not isinstance(candidates, list) or not candidates:
                raise ValueError('Gemini không trả bản dịch. Kiểm tra nội dung hoặc đổi mô hình.')
            candidate = candidates[0]
            if candidate.get('finishReason') != 'STOP':
                raise ValueError('Gemini chưa hoàn tất bản dịch hoặc nội dung bị chặn. Giảm số dòng/lô; bản dịch dở chưa được nhập.')
            parts = candidate.get('content', {}).get('parts', [])
            text = ''.join(part['text'] for part in parts if isinstance(part, dict)
                           and not part.get('thought') and isinstance(part.get('text'), str))
            if not text.strip():
                raise ValueError('Gemini trả bản dịch trống.')
            self.cancel()
            self.translated.emit(text)
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            # Error messages from our validations are safe; raw response content
            # and JSON decoder excerpts must never enter the user log.
            message = str(error) if type(error) is ValueError else ''
            self._fail(message or 'Không đọc được phản hồi Gemini. Chưa nhập bản dịch.')
