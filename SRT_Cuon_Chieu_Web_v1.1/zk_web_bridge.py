"""Optional ZK Web view/reader, driven by the existing SRT controller only."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import struct
import sys

from srt_engine import check_translations, extract_json

ZK_NAME = 'ZK_API_WEB_v2_0_7'
ZK_FILE = ZK_NAME + '.cp312-win_amd64.pyd'
ZK_SHA256 = 'f571098555a2810658881f1203d9a5da4ee5512e368c4c8d37491d3dc060437f'


@dataclass
class ZKSupport:
    module: object = None
    status: str = 'ZK Web chưa được nạp.'

    def create_view(self, parent, fallback):
        if self.module is None:
            return fallback(parent), False, self.status
        view = None
        try:
            cls = self.module.ChatGPTWebView
            if not issubclass(cls, fallback):
                raise TypeError('ChatGPTWebView không phải QWebEngineView tương thích.')
            try:
                signature = inspect.signature(cls)
            except (TypeError, ValueError):
                signature = None
            kwargs = {'parent': parent} if signature and 'parent' in signature.parameters else {}
            if signature:
                signature.bind(**kwargs)
            view = cls(**kwargs)
            if not callable(getattr(view, 'get_last_response', None)):
                raise TypeError('ChatGPTWebView thiếu get_last_response(callback).')
            if not kwargs:
                view.setParent(parent)
            return view, True, 'Đang dùng ZK ChatGPTWebView và bộ đọc ZK cùng ai_chatgpt.pyd.'
        except Exception as error:
            if view is not None:
                view.deleteLater()
            return fallback(parent), False, f'Không dùng được khung ZK: {error}. Dùng khung Web SRT.'


def load_zk_support(native_ready):
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        return ZKSupport(status='ZK Web cần Python 3.12 Windows 64-bit; đang dùng khung Web SRT.')
    if not native_ready:
        return ZKSupport(status='ZK Web chưa bật vì ai_chatgpt.pyd chưa nạp thành công.')
    path = Path(__file__).resolve().with_name(ZK_FILE)
    # Do not let an imported application's environment setup replace the user's
    # configured network route. No environment values are logged.
    keys = ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy',
            'QTWEBENGINE_CHROMIUM_FLAGS','QT_LOGGING_RULES','SSL_CERT_FILE','REQUESTS_CA_BUNDLE')
    proxies = {key: os.environ.get(key) for key in keys}
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() != ZK_SHA256:
            raise ValueError('File ZK khác bản người dùng đã cung cấp.')
        spec = importlib.util.spec_from_file_location(ZK_NAME, path)
        if spec is None or spec.loader is None:
            raise ImportError('Không có bộ nạp module ZK.')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, 'ChatGPTWebView'):
            raise ImportError('Module ZK không xuất ChatGPTWebView.')
        sys.modules[ZK_NAME] = module
        return ZKSupport(module, 'Đã nạp ZK_API_WEB_v2_0_7.pyd; chuẩn bị khung Web.')
    except ModuleNotFoundError as error:
        return ZKSupport(status=f'ZK Web còn thiếu module đi kèm: {error.name}. ai_chatgpt và mã SRT vẫn hoạt động.')
    except Exception as error:
        return ZKSupport(status=f'Không nạp được ZK Web: {error}. Dùng khung Web SRT.')
    finally:
        for key, value in proxies.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def merge_zk_response(base, args, cues):
    """Normalize the public callback, preserving a valid captured batch first."""
    if len(args) == 1:
        value = args[0]
        if isinstance(value, str):
            raw = value
            try:
                decoded = json.loads(raw)
            except (TypeError, ValueError):
                decoded = None
            value = decoded if isinstance(decoded, dict) and ('text' in decoded or 'error' in decoded) else {'text': raw}
    elif len(args) == 2 and type(args[0]) is bool and isinstance(args[1], str):
        value = {'is_generating': args[0], 'text': args[1]}
    elif len(args) == 2 and isinstance(args[0], str) and type(args[1]) is bool:
        value = {'text': args[0], 'is_generating': args[1]}
    else:
        raise TypeError('Callback ZK không có định dạng text/trạng thái được hỗ trợ.')
    if not isinstance(value, dict) or not isinstance(value.get('text'), str):
        raise TypeError('Kết quả ZK thiếu text dạng chuỗi.')
    if value.get('error'):
        raise ValueError(str(value['error'])[:240])
    text = value['text'].strip()
    def rank(candidate):
        try:
            parsed = extract_json(candidate)
            try:
                check_translations(cues, parsed)
                return 2
            except (TypeError, ValueError):
                ids = {cue.number for cue in cues}
                rows = parsed.get('items')
                return int(isinstance(rows, list) and any(isinstance(row, dict) and type(row.get('id')) is int and row['id'] in ids for row in rows))
        except (TypeError, ValueError):
            return 0
    prior = base.get('text', '')
    selected = prior if base.get('captured') and rank(prior) == 2 else (text if text and rank(text) >= rank(prior) else prior)
    return {**base, 'text': selected, 'lastText': selected,
            'generating': bool(base.get('generating')) or value.get('is_generating') is True or value.get('generating') is True,
            'diagnostics': {**base.get('diagnostics', {}), 'zkReader': True}}
