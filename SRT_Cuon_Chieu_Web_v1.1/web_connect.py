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
  let fallbackText = '';
  let fallbackMatches = 0;
  let conversationChars = 0;
  if (!assistantRows.length) {
    // Some guest layouts have neither role attributes nor markdown classes.
    // Inspect only conversation containers, excluding user/composer content.
    // Accept complete translation objects, never prompt examples or partial JSON.
    const roots = [...document.querySelectorAll('main, [role="main"], #thread, #conversation')];
    const candidates = [];
    for (const root of roots) {
      const copy = root.cloneNode(true);
      const compact = text => (text || '').replace(/\s/g, '');
      const outbound = compact(window.__srtOutboundPrompt);
      if (outbound) {
        // Guest DOM may omit even the user-role marker. Exclude the exact
        // message this app sent, including any valid JSON examples in it.
        for (const el of [...copy.querySelectorAll('*')]) {
          if (compact(el.textContent) === outbound) el.remove();
        }
      }
      copy.querySelectorAll('[data-message-author-role="user"], [data-turn="user"], ' +
        'form, textarea, [contenteditable], script, style, nav, header, [hidden], [aria-hidden="true"]')
        .forEach(el => el.remove());
      const raw = (copy.textContent || '').slice(-500000);
      conversationChars = Math.max(conversationChars, raw.length);
      const starts = /\{\s*"items"\s*:/g;
      let match;
      while ((match = starts.exec(raw))) {
        let depth = 0, quoted = false, escaped = false;
        for (let i = match.index; i < raw.length; i++) {
          const char = raw[i];
          if (quoted) {
            if (escaped) escaped = false;
            else if (char === '\\') escaped = true;
            else if (char === '"') quoted = false;
          } else if (char === '"') quoted = true;
          else if (char === '{') depth++;
          else if (char === '}' && --depth === 0) {
            try {
              const value = JSON.parse(raw.slice(match.index, i + 1));
              if (Array.isArray(value.items) && value.items.length > 0 && value.items.every(row =>
                  Number.isInteger(row.id) && typeof row.vi === 'string' && row.vi.trim() &&
                  !['...', '…'].includes(row.vi.trim()) && !('zh' in row))) {
                candidates.push(JSON.stringify(value));
              }
            } catch (_) { /* Incomplete/malformed response is not a translation. */ }
            starts.lastIndex = i + 1;
            break;
          }
        }
      }
    }
    const unique = [...new Set(candidates)];
    fallbackMatches = unique.length;
    fallbackText = unique[unique.length - 1] || '';
  }
  const lastReply = assistantRows[assistantRows.length - 1];
  const replyText = el => {
    const content = el && (el.querySelector('.markdown') || el);
    return content ? (content.innerText || content.textContent || '').trim() : '';
  };
  const lastText = replyText(lastReply) || fallbackText;
  const responseCount = assistantRows.length || fallbackMatches;

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
  return {site:true, editor:!!editor, assistantCount:responseCount, lastText};
})()"""

def make_send_message_js(message: str) -> str:
    """Return JavaScript that enters and sends one message in the current chat."""
    import json
    return r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {ok:false, why:'Trang hiện tại không phải ChatGPT.'};
  }
  const text = %s;
  window.__srtOutboundPrompt = text;
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
  const text = jsonBlock || (content ? (content.innerText || content.textContent || '').trim() : '') || fallbackText;
  const stopVisible = [...document.querySelectorAll(
    '[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Dừng"], ' +
    'button[title*="Stop"], button[title*="Dừng"]'
  )].some(shown);
  const generating = stopVisible || !!(last && last.querySelector('[data-is-streaming="true"], .result-streaming'));
  return {site:true, assistantCount:responseCount, text, lastText, generating, stopVisible, textLength:text.length,
    diagnostics:{turns:turns.length, roles:document.querySelectorAll('[data-message-author-role="assistant"]').length,
      conversationChars, fallbackMatches}};
})()"""
