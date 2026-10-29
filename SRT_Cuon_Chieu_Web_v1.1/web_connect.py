"""Bounded ChatGPT Web integration helpers for an embedded Qt web view.

The connection test only checks the site and chat editor; it never sends a message.
The translation flow reads the latest assistant text only to validate its JSON.
No login automation, CAPTCHA solving, rate-limit handling, or scraping is used.
Since chatgpt.com can change its HTML, this is best effort only.
"""

# Both probes use the same canonical assistant nodes in document order.
_DOM_HELPERS = r"""
  const shown = el => !!el && !!el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden';
  const assistantRows = [...document.querySelectorAll('[data-message-author-role="assistant"]')];
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
  return {site:true, editor:!!editor, assistantCount:assistantRows.length};
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
  const generating = [...document.querySelectorAll(
    '[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Dừng"], ' +
    'button[title*="Stop"], button[title*="Dừng"]'
  )].some(shown) || !!(last && last.querySelector('[data-is-streaming="true"], .result-streaming'));
  return {site:true, assistantCount:assistantRows.length, text, generating, textLength:text.length};
})()"""
