"""Gemini Web DOM adapter. No API key, login automation or ChatGPT binary."""
import json
from web_state import guard_web_state

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
    'button.stop-button, button[data-test-id="stop-button"], button[data-testid="stop-button"], ' +
    'button[aria-label^="Stop" i], button[aria-label^="Dừng" i], button.send-button'
  )].some(button => shown(button) && (
    button.matches('.stop-button, [data-test-id="stop-button"], [data-testid="stop-button"]') ||
    /^(Stop|Dừng)(\s|$)/i.test(button.getAttribute('aria-label') || '') ||
    [...button.querySelectorAll('mat-icon, .mat-icon')].some(icon =>
      /^(stop|stop_circle)$/.test((icon.getAttribute('fonticon') || icon.textContent || '').trim()))));
  const queries = () => [...document.querySelectorAll('user-query')];
  const compact = text => (text || '').replace(/\s/g, '');
  const matchingQueries = text => {
    const expected = compact(text);
    return expected ? queries().filter(query => compact(query.textContent).includes(expected)).length : 0;
  };
  const submissionState = () => {
    const state = window.__srtGeminiSend, editor = findEditor();
    if (state?.sent && matchingQueries(state.text) > state.matchingQueriesBefore)
      state.confirmed = true;
    return {userQueries:queries().length, editorPresent:!!editor,
      draftChars:editor ? draft(editor).length : 0,
      draftMatchesBatch:!!editor && !!state && normalize(draft(editor)) === normalize(state.text),
      sendClicked:!!state?.sent, submissionConfirmed:!!state?.confirmed};
  };
  const responses = () => [...document.querySelectorAll('model-response')]
    .filter(el => !el.closest('user-query'));
  const responseText = el => {
    if (!el) return '';
    const content = el.querySelector('.markdown-main-panel, .model-response-text, message-content') || el;
    const blocks = [...content.querySelectorAll('pre code, pre, code-block code, code-block .code-container')]
      .map(node => (node.textContent || '').trim());
    const jsonBlock = blocks.find(text => {
      try {
        const value = JSON.parse(text);
        return Array.isArray(value.items) || (Array.isArray(value) && value.every(
          row => row && Number.isInteger(row.id) && typeof row.vi === 'string'));
      } catch (_) { return false; }
    });
    return jsonBlock || (content.innerText || content.textContent || '').trim();
  };
"""


def _script(body):
    return guard_web_state('(() => { ' + _HELPERS + '\n' + body + '\n})()')


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
      conversationChars:rows.reduce((sum, row) => sum + (row.textContent || '').length, 0),
      ...submissionState()}};
""")


def make_send_message_js(message, request_id):
    return _script(r"""
      if (!site) return {ok:false, why:'Trang hiện tại không phải Gemini.'};
      const text = MESSAGE, id = REQUEST_ID;
      const editor = findEditor();
      if (!editor) return {ok:false, retryable:true, why:'Ô nhập Gemini tạm chưa sẵn sàng.'};
      if (window.__srtGeminiSend?.id === id && window.__srtGeminiSend.sent)
        return {ok:false, why:'Lô này đã được gửi. Không tự gửi trùng.'};
      if (stopVisible())
        return {ok:false, retryable:true, why:'Gemini vẫn đang tạo phản hồi trước.'};
      const previous = normalize(draft(editor));
      const state = window.__srtGeminiSend;
      // Gemini can leave the submitted prompt in Quill after replying. Replace
      // only an exact prompt owned by an earlier, already-clicked batch.
      const staleSentDraft = state && state.id !== id && state.sent === true &&
        typeof state.text === 'string' && !!state.text && previous === normalize(state.text);
      if (previous && previous !== normalize(text) && !staleSentDraft)
        return {ok:false, why:'Ô Gemini đang có bản nháp khác. Cất hoặc xóa bản nháp trước khi dịch.'};
      editor.scrollIntoView({behavior:'instant', block:'center'});
      editor.focus();
      if (previous === normalize(text)) {
        // A retry may find the exact batch already prepared. Leave it intact.
      } else if (editor.tagName.toLowerCase() === 'textarea') {
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(editor, text);
        editor.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
      } else {
        const range = document.createRange(), selection = window.getSelection();
        range.selectNodeContents(editor);
        selection.removeAllRanges(); selection.addRange(range);
        document.execCommand('insertText', false, text);
        // Chromium may report success without inserting into a rerendering
        // Quill editor. Fall back only for an empty or known sent draft.
        if (!normalize(draft(editor)) || (staleSentDraft && normalize(draft(editor)) === previous)) {
          editor.innerText = text;
          editor.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
        }
      }
      if (!editor.isConnected || findEditor() !== editor)
        return {ok:false, retryable:true, why:'Gemini vừa thay ô nhập; chờ ô mới sẵn sàng.'};
      const ok = normalize(draft(editor)) === normalize(text);
      if (ok) {
        window.__srtOutboundPrompt = text;
        window.__srtGeminiSend = {id, sent:false, text, confirmed:false};
      }
      return ok ? {ok:true, prepared:true} : {
        ok:false, retryable:!normalize(draft(editor)),
        why:'Ô nhập Gemini chưa giữ đúng nội dung lô; chưa bấm gửi.'};
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
  state.matchingQueriesBefore = matchingQueries(state.text);
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
