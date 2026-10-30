"""Retain complete batch JSON across short-lived conversation DOM updates."""
import json
from web_connect import _guard_service_limit


def with_reply_capture(script, cues, request_id):
    expected = [{'id': cue.number, 'lines': cue.source.count('\n') + 1} for cue in cues]
    setup = r"""(() => {
      if (!document.body || typeof MutationObserver === 'undefined') return;
      if (window.__srtReplyCapture) window.__srtReplyCapture.observer.disconnect();
      const expected = EXPECTED;
      const state = {requestId:REQUEST_ID, text:'', matches:0};
      const baseline = new Set();
      const blocked = el => !el || el.closest('form, textarea, [contenteditable], script, style, pre[data-user], ' +
        'user-query, [data-message-author-role="user"], [data-turn="user"]') ||
        (location.hostname === 'gemini.google.com' && !el.closest('model-response'));
      const objects = raw => {
        const found = [];
        const starts = /\{\s*"items"\s*:/g;
        let match;
        while ((match = starts.exec(raw))) {
          let depth=0, quoted=false, escaped=false;
          for (let i=match.index; i<raw.length; i++) {
            const char=raw[i];
            if (quoted) {
              if (escaped) escaped=false;
              else if (char==='\\') escaped=true;
              else if (char==='"') quoted=false;
            } else if (char==='"') quoted=true;
            else if (char==='{') depth++;
            else if (char==='}' && --depth===0) {
              try {
                const value=JSON.parse(raw.slice(match.index,i+1));
                if (Array.isArray(value.items) && value.items.length===expected.length) {
                  const rows=new Map();
                  for (const row of value.items) {
                    if (!Number.isInteger(row.id) || typeof row.vi!=='string' || !row.vi.trim() ||
                        ['...', '…'].includes(row.vi.trim()) || rows.has(row.id) || 'zh' in row) break;
                    rows.set(row.id,row.vi.trim());
                  }
                  if (rows.size===expected.length && expected.every(cue => rows.has(cue.id) &&
                      rows.get(cue.id).replace(/\r\n?/g,'\n').split('\n').length===cue.lines)) {
                    found.push(JSON.stringify({items:expected.map(cue=>({id:cue.id,vi:rows.get(cue.id)}))}));
                  }
                }
              } catch (_) {}
              starts.lastIndex=i+1;
              break;
            }
          }
        }
        return found;
      };
      // Old replies remain on screen when a new batch starts. Never import one
      // simply because a parent container changed or was re-rendered.
      for (const root of document.querySelectorAll('main, [role="main"], #thread, #conversation, chat-window, #chat-history')) {
        for (const text of objects((root.textContent || '').slice(-500000))) baseline.add(text);
      }
      const inspect = el => {
        if (!el || el.nodeType!==1 || blocked(el)) return;
        const root=el.closest('main, [role="main"], #thread, #conversation, chat-window, #chat-history');
        if (!root) return;
        const raw=el.textContent || '';
        if (raw.length>150000 || raw.indexOf('"items"')<0) return;
        const compact=text=>(text || '').replace(/\s/g,'');
        const outbound=compact(window.__srtOutboundPrompt);
        if (outbound && compact(raw).includes(outbound)) return;
        for (const text of objects(raw)) {
          if (!baseline.has(text) && text!==state.text) { state.text=text; state.matches++; }
        }
      };
      state.observer=new MutationObserver(changes=>{
        const nodes=new Set();
        for (const change of changes) {
          let el=change.target.nodeType===1 ? change.target : change.target.parentElement;
          for (let depth=0; el && depth<6; depth++,el=el.parentElement) nodes.add(el);
          for (const added of change.addedNodes || []) if (added.nodeType===1) nodes.add(added);
        }
        nodes.forEach(inspect);
      });
      state.observer.observe(document.body,{subtree:true,childList:true,characterData:true});
      window.__srtReplyCapture=state;
    })()"""
    setup = setup.replace('EXPECTED', json.dumps(expected)).replace('REQUEST_ID', str(int(request_id)))
    return _guard_service_limit('(() => { ' + setup + '; return (' + script + '); })()')


def read_with_capture(script, request_id):
    return _guard_service_limit(r"""(() => {
      const result=(SCRIPT);
      if (!result || !result.site || result.cooldown) return result;
      const capture=window.__srtReplyCapture;
      const active=!!capture && capture.requestId===REQUEST_ID;
      const diagnostics={...result.diagnostics,captureInstalled:active,capturedReplies:active ? capture.matches : 0};
      if (!active || !capture.text) return {...result,diagnostics};
      return {...result,text:capture.text,lastText:capture.text,captured:true,diagnostics};
    })()""".replace('REQUEST_ID', str(int(request_id))).replace('SCRIPT', script))


STOP_CAPTURE_JS = "if (window.__srtReplyCapture) { window.__srtReplyCapture.observer.disconnect(); delete window.__srtReplyCapture; }"
