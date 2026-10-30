"""Bounded ChatGPT Web integration helpers for an embedded Qt web view.

The connection test only checks the site and chat editor; it never sends a message.
The translation flow reads the latest assistant text only to validate its JSON.
No login automation, CAPTCHA solving, or rate-limit bypass is used.
Since chatgpt.com can change its HTML, this is best effort only.
"""

_SERVICE_LIMIT_HELPER = r"""
  const serviceLimit = () => {
    if (!document.body) return null;
    const copy = document.body.cloneNode(true);
    copy.querySelectorAll('script, style, textarea, [contenteditable], pre, code, ' +
      '[data-message-author-role="user"], [data-turn="user"], [hidden], [aria-hidden="true"]')
      .forEach(el => el.remove());
    const text = (copy.textContent || '').replace(/\s+/g, ' ');
    const match = text.match(/we['’]re doing a quick check to keep ChatGPT reliable\.?\s*Try again after\s+(\d{1,2}):(\d{2})\s*([AP]M)/i);
    if (!match) return null;
    let hour = Number(match[1]);
    const minute = Number(match[2]);
    if (hour < 1 || hour > 12 || minute > 59) return {cooldown:true, retryAt:null, clock:'không đọc được giờ'};
    hour = hour % 12 + (match[3].toUpperCase() === 'PM' ? 12 : 0);
    const now = new Date();
    const until = new Date(now);
    until.setHours(hour, minute, 0, 0);
    // Interpret a midnight rollover, but never roll a just-expired notice to tomorrow.
    if (until.getTime() < now.getTime() - 12 * 3600000) until.setDate(until.getDate() + 1);
    if (until.getTime() <= now.getTime()) return null;
    return {site:true, cooldown:true, retryAt:until.getTime()/1000,
      clock:String(hour).padStart(2,'0') + ':' + String(minute).padStart(2,'0')};
  };
"""


def _guard_service_limit(script: str) -> str:
    return ("(() => { if (['chatgpt.com','www.chatgpt.com'].includes(location.hostname)) {" +
            _SERVICE_LIMIT_HELPER + "const limit = serviceLimit(); if (limit) return limit; } return (" + script + "); })()")

# Connection, preparation and send must agree on the actual writable editor.
_EDITOR_HELPER = r"""
  const normalizeDraft = text => (text || '').replace(/\r\n?/g, '\n').replace(/\n+/g, '\n').trim();
  const findChatEditor = () => {
    const selectors = ['#prompt-textarea', 'textarea[name="prompt-textarea"]',
      '[data-testid="prompt-textarea"]', 'textarea#mobile-composer-prompt',
      '[contenteditable="true"][data-lexical-editor="true"]', '[role="textbox"]', '[contenteditable]'];
    for (const selector of selectors) {
      for (const candidate of document.querySelectorAll(selector)) {
        const nodes = candidate.matches('textarea, [contenteditable]') ? [candidate] :
          [...candidate.querySelectorAll('textarea, [contenteditable]')];
        for (const node of nodes) {
          if (node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden' &&
              !node.disabled && !node.readOnly &&
              (node.tagName.toLowerCase() === 'textarea' || node.isContentEditable)) return node;
        }
      }
    }
    return null;
  };
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
  /*EDITOR_HELPER*/
  const editor = findChatEditor();
  return {site:true, editor:!!editor, assistantCount:responseCount, lastText, editorKind:editor ? editor.tagName.toLowerCase() : ''};
})()""".replace("/*EDITOR_HELPER*/", _EDITOR_HELPER)

def make_send_message_js(message: str) -> str:
    """Return JavaScript that enters and sends one message in the current chat."""
    import json
    return _guard_service_limit(r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {ok:false, why:'Trang hiện tại không phải ChatGPT.'};
  }
  const text = %s;
  window.__srtOutboundPrompt = text;
  /*EDITOR_HELPER*/
  const editor = findChatEditor();
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
  return {ok:normalizeDraft(actual) === normalizeDraft(text), prepared:true, why:'Không điền được nội dung lô vào ô chat.'};
})()""".replace("/*EDITOR_HELPER*/", _EDITOR_HELPER) % json.dumps(message, ensure_ascii=False))

# React updates send-button state after the input event. Click in a separate
# invocation, rather than pretending a synthetic Enter was accepted.
SEND_MESSAGE_JS = r"""(() => {
  if (!['chatgpt.com', 'www.chatgpt.com'].includes(location.hostname)) {
    return {ok:false, why:'Trang hiện tại không phải ChatGPT.'};
  }
  const shown = el => el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
  /*EDITOR_HELPER*/
  const editor = findChatEditor();
  if (!editor) return {ok:false, retryable:false, why:'Không còn ô chat trên trang.'};
  const draft = editor.tagName.toLowerCase() === 'textarea' ? editor.value : editor.innerText;
  if (!draft || normalizeDraft(draft) !== normalizeDraft(window.__srtOutboundPrompt)) {
    return {ok:false, retryable:false, why:'Nội dung ô chat đã thay đổi. Chưa bấm gửi để tránh gửi nhầm hoặc gửi trùng.'};
  }
  if ([...document.querySelectorAll('[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Dừng"]')].some(shown)) {
    return {ok:false, retryable:true, why:'Trang vẫn đang tạo câu trả lời trước.'};
  }
  const explicit = ['button#composer-submit-button','button[data-testid="send-button"]',
    'button[aria-label="Send message"]','button[aria-label="Send prompt"]',
    'button[aria-label="Gửi tin nhắn"]'].flatMap(s => [...document.querySelectorAll(s)]);
  const form = editor.closest('form');
  const controls = explicit.concat(form ? [...form.querySelectorAll('button[type="submit"]')] : []);
  const visible = [...new Set(controls)].filter(shown);
  const button = visible.find(el => !el.disabled && el.getAttribute('aria-disabled') !== 'true');
  if (!button) return {ok:false, retryable:true,
    why:visible.length ? 'Nút gửi đang bị vô hiệu hóa.' : 'Chưa tìm thấy nút gửi của ô chat.'};
  button.click();
  return {ok:true};
})()""".replace("/*EDITOR_HELPER*/", _EDITOR_HELPER)

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


PROBE_JS = _guard_service_limit(PROBE_JS)
SEND_MESSAGE_JS = _guard_service_limit(SEND_MESSAGE_JS)
READ_LATEST_RESPONSE_JS = _guard_service_limit(READ_LATEST_RESPONSE_JS)
