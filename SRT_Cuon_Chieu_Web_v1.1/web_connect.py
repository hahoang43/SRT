"""Bounded ChatGPT Web integration helpers for an embedded Qt web view.

The connection test only checks the site and chat editor; it never sends a message.
The translation flow reads the latest assistant text only to validate its JSON.
No login automation, CAPTCHA solving, or rate-limit bypass is used.
Since chatgpt.com can change its HTML, this is best effort only.
"""

# Both probes use the same canonical assistant nodes in document order.
_DOM_HELPERS = r"""
  const shown = el => !!el && !!el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden';
  // Guest pages may omit author-role on the visible response. Select one
  // message per turn, in DOM order, without ever reading a user turn as a reply.
  const turns = [...document.querySelectorAll('[data-testid^="conversation-turn-"]')];
  let assistantRows = turns.length ? turns.flatMap(turn => {
    if (turn.matches('[data-message-author-role="user"]') ||
        turn.querySelector('[data-message-author-role="user"]') ||
        turn.getAttribute('data-turn') === 'user') return [];
    const reply = turn.querySelector('[data-message-author-role="assistant"]') ||
      (turn.matches('[data-message-author-role="assistant"]') ? turn : null) ||
      turn.querySelector('.markdown');
    return reply ? [reply] : [];
  }) : [...document.querySelectorAll('[data-message-author-role="assistant"]')];
  if (!assistantRows.length) {
    // Fallback only to complete translation JSON in conversation content.
    // Never inspect the whole page or use composer/user text as a response.
    assistantRows = [...document.querySelectorAll('main .markdown, main pre code')].filter(el => {
      if (el.closest('[data-message-author-role="user"], [data-turn="user"], form')) return false;
      try {
        const value = JSON.parse((el.innerText || el.textContent || '').trim());
        return Array.isArray(value.items) && value.items.length > 0 &&
          value.items.every(row => Number.isInteger(row.id) && typeof row.vi === 'string' && !('zh' in row));
      } catch (_) { return false; }
    });
    assistantRows = assistantRows.filter(el => !assistantRows.some(other => other !== el && other.contains(el)));
  }
  const lastReply = assistantRows[assistantRows.length - 1];
  const replyText = el => {
    const content = el && (el.querySelector('.markdown') || el);
    return content ? (content.innerText || content.textContent || '').trim() : '';
  };
  const lastText = replyText(lastReply);

"""

PROBE_JS = r"""(() => {
  const host = window.location.hostname;
  if (host !== 'chatgpt.com' && host !== 'www.chatgpt.com') {
    return {site:false, editor:false, assistantCount:0};
  }
""" + _DOM_HELPERS + r"""
  const editor = [...document.querySelectorAll(
    '#prompt-textarea, textarea[name="prompt-textarea"], [data-testid="prompt-textarea"], ' +
    'textarea#mobile-composer-prompt, [contenteditable="true"][data-lexical-editor="true"]'
  )].find(el => shown(el) && !el.disabled && el.getAttribute('contenteditable') !== 'false');
  return {site:true, editor:!!editor, assistantCount:assistantRows.length, lastText};
})()"""

def make_send_message_js(message: str) -> str:
    """Return JavaScript that enters and sends one message in the current chat."""
    import json
    return r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {ok:false, why:'Trang hiện tại không phải ChatGPT.'};
  }
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
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(editor);
    selection.removeAllRanges(); selection.addRange(range);
    if (!document.execCommand('insertText', false, text)) {
      editor.textContent = text;
      editor.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
    }
  }
  const actual = editor.tagName.toLowerCase() === 'textarea' ? editor.value : editor.innerText;
  return {ok:actual.trim() === text.trim(), prepared:true, why:'Không điền được nội dung lô vào ô chat.'};
})()""" % json.dumps(message, ensure_ascii=False)

# React updates send-button state after the input event. Click in a separate
# invocation, rather than pretending a synthetic Enter was accepted.
SEND_MESSAGE_JS = r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {ok:false, why:'Trang hiện tại không phải ChatGPT.'};
  }
  const button = ['button#composer-submit-button','button[data-testid="send-button"]',
    'button[aria-label="Send message"]','button[aria-label="Send prompt"]',
    'button[aria-label="Gửi tin nhắn"]','button[type="submit"]']
    .flatMap(s => [...document.querySelectorAll(s)])
    .find(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' &&
      !el.disabled && el.getAttribute('aria-disabled') !== 'true');
  if (!button) return {ok:false, why:'Nút gửi chưa sẵn sàng. Kiểm tra trang có báo giới hạn hoặc yêu cầu đăng nhập không.'};
  button.click();
  return {ok:true};
})()"""

READ_LATEST_RESPONSE_JS = r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {site:false, assistantCount:0, text:'', generating:false};
  }
""" + _DOM_HELPERS + r"""
  const last = assistantRows[assistantRows.length - 1];
  // Read code contents, not the surrounding language/copy buttons or prose.
  const blocks = last ? [...last.querySelectorAll('pre code')]
    .map(el => (el.textContent || '').trim()).filter(Boolean) : [];
  const jsonBlock = blocks.find(text => {
    try { const value = JSON.parse(text); return value && Array.isArray(value.items); }
    catch (_) { return false; }
  });
  const content = last && (last.querySelector('.markdown') || last);
  const text = jsonBlock || (content ? (content.innerText || content.textContent || '').trim() : '');
  const stopVisible = [...document.querySelectorAll(
    '[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Dừng"], ' +
    'button[title*="Stop"], button[title*="Dừng"]'
  )].some(shown);
  const generating = stopVisible || !!(last && last.querySelector('[data-is-streaming="true"], .result-streaming'));
  return {site:true, assistantCount:assistantRows.length, text, lastText, generating, stopVisible, textLength:text.length};
})()"""
