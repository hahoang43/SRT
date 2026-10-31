"""Read-only detection of service blocks; never reset identities or solve challenges."""

WEB_BLOCK_JS = r"""(() => {
  const host = location.hostname;
  const path = location.pathname || '';
  if (host === 'challenges.cloudflare.com' ||
      /\/cdn-cgi\/challenge-platform(?:\/|$)/.test(path))
    return {blocked:'challenge', why:'Trang đang yêu cầu xác minh Cloudflare.'};
  if (!['chatgpt.com', 'www.chatgpt.com', 'gemini.google.com'].includes(host)) return null;
  if (!document.body || !document.querySelectorAll) return null;
  const shown = el => !!el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).opacity !== '0' &&
    // A hidden native widget can have a zero-width viewport. Keep detecting
    // challenge forms there, but exclude zero-area invisible CAPTCHA frames.
    (el.tagName !== 'IFRAME' || [...el.getClientRects()].some(rect => rect.width > 0 && rect.height > 0));
  const challenges = document.querySelectorAll(
    '#challenge-running, #challenge-stage, #challenge-form, .cf-turnstile, ' +
    'iframe[src*="challenges.cloudflare.com"], iframe[src*="/recaptcha/"][src*="/anchor"], ' +
    'iframe[src*="/recaptcha/"][src*="/bframe"], iframe[src*="hcaptcha.com"][title*="challenge"]');
  if ([...challenges].some(shown) || /^(just a moment|attention required!.*cloudflare)/i.test(document.title || ''))
    return {blocked:'challenge', why:'Trang đang yêu cầu xác minh Cloudflare/CAPTCHA.'};
  // Service notices only: quoted subtitles, drafts and model replies must not
  // trigger an interruption merely because they mention a limit or a CAPTCHA.
  const excluded = 'script, style, textarea, [contenteditable], pre, code, ' +
    '[data-message-author-role], [data-turn], model-response, user-query, .markdown, ' +
    '[hidden], [aria-hidden="true"]';
  const noticeText = el => {
    if (el.matches(excluded)) return '';
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return '';
    return [...el.childNodes].map(node => node.nodeType === 3 ? node.textContent :
      node.nodeType === 1 ? noticeText(node) : '').join(' ');
  };
  const text = noticeText(document.body).replace(/\s+/g, ' ');
  if (/too many requests|you['’]ve reached (?:our|the|your) (?:usage )?limit|you have reached (?:our|the|your) (?:usage )?limit|rate limit exceeded/i.test(text))
    return {blocked:'rate_limit', why:'Dịch vụ thông báo đã đạt hạn mức. Chờ theo thông báo trên Web rồi bắt đầu lại.'};
  if (/403\s*(?:forbidden|access denied)|access denied\s*(?:403)?/i.test(text))
    return {blocked:'access_denied', why:'Dịch vụ từ chối truy cập. Kiểm tra quyền truy cập trên Web.'};
  return null;
})()"""


def guard_web_state(script):
    return '(() => { const block = (' + WEB_BLOCK_JS + '); if (block) return block; return (' + script + '); })()'
