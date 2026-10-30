"""Adapt the supplied CPython 3.12 Windows module to the app's Web protocol."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
import struct
import sys

import web_connect as builtin

NATIVE_FILE = 'ai_chatgpt.cp312-win_amd64.pyd'
NATIVE_SHA256 = 'e1f884cbed7b0a97d8e2d0f85e5e05016933c00aeb999e0d79842587df1be6a5'


def _script(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 250_000:
        raise ValueError('Module phải trả về chuỗi JavaScript hợp lệ.')
    return value.strip().rstrip(';')


def _substitute(template, **values):
    return re.sub(r'\b(?:' + '|'.join(values) + r')\b', lambda match: values[match.group()], template)


_POSTED_PROMPT_HELPER = r"""
  const postedPromptCount = () => {
    const compact=text=>(text || '').replace(/\s/g,'');
    const prompt=compact(window.__srtOutboundPrompt);
    if (!prompt) return 0;
    let count=0;
    for (const root of document.querySelectorAll('main, [role="main"], #thread, #conversation')) {
      const copy=root.cloneNode(true);
      copy.querySelectorAll('form, textarea, [contenteditable], script, style').forEach(el=>el.remove());
      const text=compact((copy.textContent || '').slice(-500000));
      count=Math.max(count,text.split(prompt).length-1);
    }
    return count;
  };
"""


class WebBridge:
    def __init__(self, handler=None, status='Bộ Web tích hợp.'):
        self.native = handler is not None
        self.handler = handler
        self.status = status
        self.probe_js = builtin.PROBE_JS
        self.read_js = builtin.READ_LATEST_RESPONSE_JS
        if self.native:
            native_read = _script(handler.get_read_js())
            native_read = re.sub(r'targetNode\.scrollIntoView\([^;]*\);', '', native_read)
            native_read = re.sub(r'box\.scrollTop\s*=\s*box\.scrollHeight\s*;', '', native_read)
            self.probe_js = self._reader(builtin.PROBE_JS, native_read, probe=True)
            self.read_js = self._reader(builtin.READ_LATEST_RESPONSE_JS, native_read)

    @staticmethod
    def _reader(base, native, probe=False):
        # Native returns a JSON STRING with is_generating/text. The app expects
        # an OBJECT with generating/text and response correlation fields.
        script = """(() => {
          const base = (BASE);
          if (!base.site || base.cooldown) return base;
          let value;
          try {
            value = (NATIVE);
            if (typeof value === 'string') value = JSON.parse(value);
          } catch (error) {
            return {...base, diagnostics:{...base.diagnostics, nativeError:String(error)}};
          }
          if (!value || typeof value !== 'object') return base;
          const text = typeof value.text === 'string' ? value.text.trim() : '';
          // Use native extraction first, retaining the built-in JSON recovery.
          const hasJSON = text => {
            try { return Array.isArray(JSON.parse(text).items); } catch (_) { return false; }
          };
          const selected = text && (hasJSON(text) || !hasJSON(base.text || base.lastText || ''))
            ? text : (base.text || base.lastText || '');
          return {...base, lastText:selected, text:selected,
            generating:!!base.generating || value.is_generating === true,
            diagnostics:{...base.diagnostics, nativeReader:true,
              nativeMethod:typeof value.debug === 'string' ? value.debug : '',
              nativeError:typeof value.error === 'string' ? value.error : ''}};
        })()"""
        script = _substitute(script, BASE=base, NATIVE=native)
        return builtin._guard_service_limit(script)

    def send_js(self, message, request_id=0):
        if not self.native:
            return builtin.make_send_message_js(message)
        marker = '__SRT_NATIVE_PAYLOAD_7D89__'
        native = _script(self.handler.get_send_js(marker))
        # Supply data through a JSON-encoded variable rather than embedding SRT
        # contents in the module's JavaScript template literal.
        pattern = r"(\bconst\s+text\s*=\s*)([`\"'])" + marker + r"\2"
        native, replaced = re.subn(pattern, lambda match: match[1] + 'window.__srtOutboundPrompt', native, count=1)
        if replaced != 1:
            raise ValueError('Định dạng get_send_js không khớp module đã kiểm tra.')
        native = re.sub(r'\bconst\s+input\s*=\s*document\.querySelector[\s\S]*?;',
                        'const input = findChatEditor();', native, count=1)
        safe_selection = """if (!input.isConnected || !(document.activeElement === input || input.contains(document.activeElement))) return false;
          const selection = window.getSelection();
          if (!selection) return false;
          const range = document.createRange();
          range.selectNodeContents(input);
          selection.removeAllRanges(); selection.addRange(range);"""
        native = re.sub(r"document\.execCommand\(\s*['\"]selectAll['\"]\s*,\s*false\s*,\s*null\s*\)\s*;",
                        lambda _: safe_selection, native)
        native = native.replace('input.innerHTML = `<p>${text}</p>`;', 'input.textContent = text;')
        native = re.sub(r'\bconst\s+sendBtn\s*=\s*document\.querySelector[\s\S]*?;',
                        'const sendBtn = window.__srtNativeReadyButton;', native, count=1)
        native = re.sub(r'(?<![\w.])(?:window\.)?setTimeout\s*\(', 'window.__srtNativeTimeout(', native)
        # The module schedules its own click after 400ms. Never follow it with
        # the built-in send script: that would send twice or submit a new draft.
        script = """(() => {
          if (!['chatgpt.com','www.chatgpt.com'].includes(location.hostname))
            return {ok:false, why:'Trang hiện tại không phải ChatGPT.'};
          window.__srtOutboundPrompt = MESSAGE;
          const requestId = REQUEST_ID;
          HELPERS
          window.__srtNativeSendId = requestId;
          const state={id:requestId,invoked:false,reason:'Chờ nút gửi sẵn sàng.',before:postedPromptCount(),until:Date.now()+30000};
          window.__srtNativeState=state;
          window.__srtNativeTimeout = (callback, delay) => {
            const check = () => {
              if (window.__srtNativeSendId!==requestId || state.invoked) return;
              if (Date.now()>=state.until) {state.reason='Hết thời gian chờ nút gửi của module.';return;}
              if (postedPromptCount()>state.before) {state.invoked=true;state.reason='Đã thấy yêu cầu mới trong hội thoại.';return;}
              const editor=findChatEditor();
              if (!editor) state.reason='Chưa thấy ô chat sau khi chuẩn bị lô.';
              else {
                const draft=editor.tagName.toLowerCase()==='textarea' ? editor.value : editor.innerText;
                if (normalizeDraft(draft)!==normalizeDraft(window.__srtOutboundPrompt)) {
                  state.reason='Nội dung ô chat đã thay đổi; không tự bấm gửi.';
                  return;
                }
                const stop=[...document.querySelectorAll('[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Dừng"]')]
                  .some(el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden');
                const button=findChatSendButton(editor);
                if (button && !stop) {
                  state.invoked=true;
                  state.reason='Đã bấm gửi; chờ xác nhận yêu cầu.';
                  window.__srtNativeReadyButton=button;
                  try {callback();} catch (error) {state.failed=true;state.reason='Lỗi thao tác gửi của module: '+String(error);}
                  return;
                }
                state.reason=stop ? 'Trang vẫn đang tạo câu trả lời trước.' : 'Nút gửi của module chưa sẵn sàng.';
              }
              state.timer=window.setTimeout(check,500);
            };
            state.check=check;
            state.timer=window.setTimeout(check,delay);
            return state.timer;
          };
          const value = (NATIVE);
          return {ok:value === true, nativeQueued:true};
        })()"""
        script = _substitute(script, NATIVE=native, MESSAGE=json.dumps(message, ensure_ascii=False), REQUEST_ID=str(int(request_id)), HELPERS=builtin._EDITOR_HELPER+builtin._SEND_CONTROL_HELPER+_POSTED_PROMPT_HELPER)
        return builtin._guard_service_limit(script)


NATIVE_SEND_ACK_JS = builtin._guard_service_limit(r"""(() => {
  if (!['chatgpt.com','www.chatgpt.com'].includes(location.hostname))
    return {ok:false, why:'Trang đã rời ChatGPT.'};
  /*EDITOR_HELPER*/
  /*POSTED_HELPER*/
  const state=window.__srtNativeState;
  if (!state || state.id!==window.__srtNativeSendId) return {ok:false,why:'Phiên gửi của module không còn hiệu lực.'};
  if (state.failed) return {ok:false,why:state.reason};
  if (postedPromptCount()>state.before) {state.invoked=true;return {ok:true,confirmed:'conversation'};}
  const editor = findChatEditor();
  if (!editor) return {pending:true, why:'Chờ ô chat sau thao tác gửi của module.'};
  const draft = editor.tagName.toLowerCase() === 'textarea' ? editor.value : editor.innerText;
  if (!normalizeDraft(draft) && state.invoked) return {ok:true,confirmed:'composer'};
  if (normalizeDraft(draft) === normalizeDraft(window.__srtOutboundPrompt))
    return {pending:true, why:state.reason};
  return {ok:false, why:'Nội dung ô chat đã thay đổi; không tự gửi lại để tránh trùng.'};
})()""".replace('/*EDITOR_HELPER*/', builtin._EDITOR_HELPER).replace('/*POSTED_HELPER*/', _POSTED_PROMPT_HELPER))


RESUME_NATIVE_WAIT_JS = builtin._guard_service_limit(r"""(() => {
  if (!['chatgpt.com','www.chatgpt.com'].includes(location.hostname))
    return {ok:false,why:'Trang đã rời ChatGPT.'};
  /*POSTED_HELPER*/
  const state=window.__srtNativeState;
  if (!state || state.id!==window.__srtNativeSendId || state.failed)
    return {ok:false,why:'Phiên gửi của module không còn hợp lệ.'};
  if (state.invoked || postedPromptCount()>state.before) {
    state.invoked=true;
    return {ok:true,resumed:false};
  }
  if (typeof state.check!=='function') return {ok:false,why:'Không còn thao tác chờ nút gửi.'};
  window.clearTimeout(state.timer);
  state.until=Date.now()+30000;
  state.check();
  return {ok:true,resumed:true};
})()""".replace('/*POSTED_HELPER*/', _POSTED_PROMPT_HELPER))


def load_web_bridge():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        return WebBridge(status='Bộ Web tích hợp: module ai_chatgpt cần Python 3.12 Windows 64-bit.')
    path = Path(__file__).resolve().with_name(NATIVE_FILE)
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() != NATIVE_SHA256:
            raise ValueError('File ai_chatgpt khác bản người dùng đã cung cấp.')
        spec = importlib.util.spec_from_file_location('ai_chatgpt', path)
        if spec is None or spec.loader is None:
            raise ImportError('Không tìm thấy bộ nạp module ai_chatgpt.')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return WebBridge(module.ChatGPTHandler, 'Đang dùng module ai_chatgpt.pyd do người dùng cung cấp.')
    except Exception as error:
        return WebBridge(status=f'Không nạp được ai_chatgpt.pyd: {error}. Đang dùng bộ Web tích hợp.')
