"""Bounded ChatGPT Web integration helpers for an embedded Qt web view.

The connection test only confirms that an assistant response element appears.
The translation flow reads the latest assistant text only to validate its JSON.
No login automation, CAPTCHA solving, rate-limit handling, or scraping is used.
Since chatgpt.com can change its HTML, this is best effort only.
"""

GREETING = 'Xin chào'

# Check the domain and whether the chat editor is ready.
PROBE_JS = r"""(() => {
  const host = window.location.hostname;
  if (host !== 'chatgpt.com' && host !== 'www.chatgpt.com') {
    return {site: false, editor: false, assistantCount: 0, repliesWithText: 0};
  }
  const selectors = [
    '#prompt-textarea',
    'textarea[name="prompt-textarea"]',
    '[data-testid="prompt-textarea"]',
    'textarea#mobile-composer-prompt',
    '[contenteditable="true"][data-lexical-editor="true"]',
    '[contenteditable="true"]'
  ];
  const shown = x => x && x.getClientRects().length &&
    window.getComputedStyle(x).visibility !== 'hidden';
  const editor = selectors.flatMap(s => [...document.querySelectorAll(s)]).find(shown);
  const replies = [...document.querySelectorAll('[data-message-author-role="assistant"]')];
  return {
    site: true,
    editor: !!editor,
    assistantCount: replies.length,
    repliesWithText: replies.filter(el => Boolean((el.innerText || '').trim())).length
  };
})()"""

# Fill only this app's one greeting; no credentials or any page content is accessed.
FILL_GREETING_JS = r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {ok:false, why:'Khác tên miền ChatGPT'};
  }
  const sels = ['#prompt-textarea','textarea[name="prompt-textarea"]',
                '[data-testid="prompt-textarea"]','textarea#mobile-composer-prompt',
                '[contenteditable="true"][data-lexical-editor="true"]',
                '[contenteditable="true"]'];
  const editor = sels.flatMap(s => [...document.querySelectorAll(s)])
    .find(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  if (!editor) return {ok:false, why:'Chưa thấy ô chat (có thể cần đăng nhập)'};
  editor.focus();
  const text = 'Xin chào';
  if (editor.tagName.toLowerCase() === 'textarea') {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(editor, text);
    editor.dispatchEvent(new InputEvent('input', {
      bubbles: true, inputType: 'insertText', data: text
    }));
  } else {
    const sel = window.getSelection();
    if (sel) { const range = document.createRange(); range.selectNodeContents(editor);
      sel.removeAllRanges(); sel.addRange(range); }
    const inserted = document.execCommand('insertText', false, text);
    if (!inserted) {
      editor.innerHTML = '';
      editor.appendChild(document.createTextNode(text));
      editor.dispatchEvent(new InputEvent('input', {
        bubbles: true, inputType: 'insertText', data: text
      }));
    }
  }
  const insertedText = editor.value || editor.innerText || '';
  return {ok: insertedText.includes(text), why:'Không điền được vào ô chat'};
})()"""

# Only click a visible enabled send control for the one greeting.
SEND_GREETING_JS = r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {ok:false, why:'Trang đã đổi tên miền'};
  }
  const editorSels = ['#prompt-textarea','textarea[name="prompt-textarea"]',
                '[data-testid="prompt-textarea"]','textarea#mobile-composer-prompt',
                '[contenteditable="true"][data-lexical-editor="true"]',
                '[contenteditable="true"]'];
  const shown = el => el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden';
  const editor = editorSels.flatMap(s => [...document.querySelectorAll(s)])
    .find(el => shown(el));
  if (!editor) return {ok:false, why:'Không tìm thấy ô chat'};
  const sels = ['button#composer-submit-button', '[data-testid="send-button"]',
                'button[aria-label="Send message"]', 'button[aria-label="Send prompt"]',
                'button[aria-label="Gửi tin nhắn"]', 'button[type="submit"]',
                'button[aria-label*="Send"]', 'button[aria-label*="Gửi"]'];
  const btn = sels.flatMap(s => [...document.querySelectorAll(s)])
    .find(el => shown(el) && !el.disabled && el.getAttribute('aria-disabled') !== 'true');
  if (btn) {
    btn.click();
    return {ok:true, method:'button'};
  }
  editor.dispatchEvent(new KeyboardEvent('keydown', {
    bubbles:true, cancelable:true, key:'Enter', code:'Enter',
    keyCode:13, which:13
  }));
  editor.dispatchEvent(new KeyboardEvent('keyup', {
    bubbles:true, cancelable:true, key:'Enter', code:'Enter',
    keyCode:13, which:13
  }));
  return {ok:true, method:'enter'};
})()"""

def make_send_message_js(message: str) -> str:
    """Return JavaScript that enters and sends one message in the current chat."""
    import json
    return r"""(() => {
  const text = %s;
  const sels = ['#prompt-textarea','textarea[name="prompt-textarea"]',
                '[data-testid="prompt-textarea"]','textarea#mobile-composer-prompt',
                '[contenteditable="true"][data-lexical-editor="true"]',
                '[contenteditable="true"]'];
  const editor = sels.flatMap(s => [...document.querySelectorAll(s)])
    .find(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  if (!editor) return {ok:false, why:'Không tìm thấy ô chat'};
  editor.focus();
  if (editor.tagName.toLowerCase() === 'textarea') {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(editor, text);
    editor.dispatchEvent(new InputEvent('input', {
      bubbles:true, inputType:'insertText', data:text
    }));
  } else {
    editor.innerHTML = '';
    editor.appendChild(document.createTextNode(text));
    editor.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
  }
  const button = ['button#composer-submit-button','[data-testid="send-button"]',
    'button[aria-label="Send message"]','button[aria-label="Send prompt"]',
    'button[aria-label="Gửi tin nhắn"]','button[type="submit"]',
    'button[aria-label*="Send"]','button[aria-label*="Gửi"]'].flatMap(s => [...document.querySelectorAll(s)])
    .find(el => el.getClientRects().length && !el.disabled &&
      el.getAttribute('aria-disabled') !== 'true');
  if (button) {
    button.click();
    return {ok:true, method:'button'};
  }
  editor.dispatchEvent(new KeyboardEvent('keydown', {
    bubbles:true, cancelable:true, key:'Enter', code:'Enter',
    keyCode:13, which:13
  }));
  editor.dispatchEvent(new KeyboardEvent('keyup', {
    bubbles:true, cancelable:true, key:'Enter', code:'Enter',
    keyCode:13, which:13
  }));
  return {ok:true, method:'enter'};
})()""" % json.dumps(message, ensure_ascii=False)

READ_LATEST_RESPONSE_JS = r"""(() => {
  const messageSelectors = [
    '[data-message-author-role="assistant"]',
    '[data-testid^="conversation-turn-"][data-message-author-role="assistant"]',
    'article[data-testid*="conversation-turn"]'
  ];
  const unique = [...new Set(messageSelectors.flatMap(selector =>
    [...document.querySelectorAll(selector)]))];
  const assistantRows = unique.filter(row =>
    row.getAttribute('data-message-author-role') === 'assistant' ||
    row.querySelector('[data-message-author-role="assistant"]'));
  const last = assistantRows[assistantRows.length - 1];
  const stopSelectors = [
    'button[aria-label*="Stop"]',
    'button[aria-label*="Dừng"]',
    '[data-testid*="stop"]',
    'button[title*="Stop"]',
    'button[title*="Dừng"]'
  ];
  const visible = el => el && el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden';
  const generating = stopSelectors.some(selector =>
    [...document.querySelectorAll(selector)].some(visible));
  const text = last ? (last.innerText || last.textContent || '').trim() : '';
  return {
    assistantCount: assistantRows.length,
    text,
    generating,
    textLength: text.length
  };
})()"""


def response_appeared(probe: object, baseline: int) -> bool:
    """Return whether a new non-empty assistant response is present."""
    if not isinstance(probe, dict) or probe.get('site') is not True:
        return False
    count = probe.get('assistantCount')
    nonempty = probe.get('repliesWithText')
    return (isinstance(count, int) and not isinstance(count, bool) and
            isinstance(nonempty, int) and not isinstance(nonempty, bool) and
            count > baseline and nonempty > baseline)
