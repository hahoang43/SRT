"""Gemini Web DOM adapter. No API key, login automation or ChatGPT binary."""
import json

WEB_URL = 'https://gemini.google.com/app'

_HELPERS = r"""
  const shown = el => !!el && !!el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden';
  const site = location.hostname === 'gemini.google.com';
  const normalize = text => (text || '').replace(/\r\n?/g, '\n').replace(/\n+/g, '\n').trim();
  const findEditor = () => [...document.querySelectorAll(
    'rich-textarea .ql-editor[contenteditable="true"], ' +
    'rich-textarea [contenteditable="true"], .input-area [contenteditable="true"], ' +
    'textarea[aria-label="Enter a prompt here"], textarea[aria-label="Nhập câu lệnh tại đây"]'
  )].find(el => shown(el) && !el.disabled && !el.readOnly && el.getAttribute('aria-disabled') !== 'true');
  const draft = el => el.tagName.toLowerCase() === 'textarea' ? el.value : el.innerText;
  const stopVisible = () => [...document.querySelectorAll(
    'button.stop-button, button[aria-label="Stop response"], button[aria-label="Stop generating"], ' +
    'button[aria-label="Dừng phản hồi"], button[aria-label="Dừng tạo"], ' +
    'button[aria-label="Stop"], button[aria-label="Dừng"]'
  )].some(shown);
  const responses = () => [...document.querySelectorAll('model-response')]
    .filter(el => !el.closest('user-query'));
  const responseText = el => {
    if (!el) return '';
    const content = el.querySelector('.markdown-main-panel, .model-response-text, message-content') || el;
    const blocks = [...content.querySelectorAll('pre code')].map(node => (node.textContent || '').trim());
    const jsonBlock = blocks.find(text => {
      try { return Array.isArray(JSON.parse(text).items); } catch (_) { return false; }
    });
    return jsonBlock || (content.innerText || content.textContent || '').trim();
  };
"""


def _script(body):
    return '(() => { ' + _HELPERS + '\n' + body + '\n})()'


PROBE_JS = _script(r"""
  if (!site) return {site:false, editor:false, assistantCount:0};
  const rows = responses(), editor = findEditor();
  return {site:true, editor:!!editor, assistantCount:rows.length, lastText:responseText(rows.at(-1))};
""")

READ_LATEST_RESPONSE_JS = _script(r"""
  if (!site) return {site:false, assistantCount:0, text:'', generating:false};
  const rows = responses(), text = responseText(rows.at(-1)), stopping = stopVisible();
  return {site:true, assistantCount:rows.length, text, lastText:text,
    generating:stopping, stopVisible:stopping,
    diagnostics:{provider:'gemini', responses:rows.length,
      conversationChars:rows.reduce((sum, row) => sum + (row.textContent || '').length, 0)}};
""")


def make_send_message_js(message, request_id):
    return _script(r"""
      if (!site) return {ok:false, why:'Trang hiện tại không phải Gemini.'};
      const text = MESSAGE, id = REQUEST_ID;
      const editor = findEditor();
      if (!editor) return {ok:false, why:'Chưa thấy ô nhập Gemini. Kiểm tra đăng nhập Google trên Web.'};
      if (window.__srtGeminiSend?.id === id && window.__srtGeminiSend.sent)
        return {ok:false, why:'Lô này đã được gửi. Không tự gửi trùng.'};
      const previous = normalize(draft(editor));
      if (previous && previous !== normalize(text))
        return {ok:false, why:'Ô Gemini đang có bản nháp khác. Cất hoặc xóa bản nháp trước khi dịch.'};
      editor.focus();
      if (editor.tagName.toLowerCase() === 'textarea') {
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(editor, text);
        editor.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
      } else {
        const range = document.createRange(), selection = window.getSelection();
        range.selectNodeContents(editor);
        selection.removeAllRanges(); selection.addRange(range);
        if (!document.execCommand('insertText', false, text)) {
          editor.textContent = text;
          editor.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
        }
      }
      const ok = normalize(draft(editor)) === normalize(text);
      if (ok) {
        window.__srtOutboundPrompt = text;
        window.__srtGeminiSend = {id, sent:false};
      }
      return {ok, prepared:true};
    """.replace('REQUEST_ID', str(int(request_id))).replace('MESSAGE', json.dumps(message, ensure_ascii=False)))


SEND_MESSAGE_JS = _script(r"""
  if (!site) return {ok:false, why:'Trang hiện tại không phải Gemini.'};
  const state = window.__srtGeminiSend;
  if (!state) return {ok:false, why:'Chưa chuẩn bị lô Gemini.'};
  if (state.sent) return {ok:true, alreadySent:true};
  const editor = findEditor();
  if (!editor || normalize(draft(editor)) !== normalize(window.__srtOutboundPrompt))
    return {ok:false, why:'Ô nhập Gemini đã thay đổi. Không tự gửi nội dung khác.'};
  if (stopVisible()) return {ok:false, retryable:true, why:'Gemini vẫn đang tạo phản hồi trước.'};
  const button = [...document.querySelectorAll(
    'button.send-button, button[aria-label="Send message"], button[aria-label="Send prompt"], ' +
    'button[aria-label="Gửi tin nhắn"], button[aria-label="Gửi câu lệnh"]'
  )].find(el => shown(el) && !el.disabled && el.getAttribute('aria-disabled') !== 'true');
  if (!button) return {ok:false, retryable:true, why:'Nút gửi Gemini chưa sẵn sàng.'};
  state.sent = true;
  button.click();
  return {ok:true};
""")

REVEAL_EDITOR_JS = _script(r"""
  if (!site) return {ok:false};
  const editor = findEditor();
  if (!editor) return {ok:false};
  editor.scrollIntoView({behavior:'instant', block:'center'});
  editor.focus();
  return {ok:true};
""")
