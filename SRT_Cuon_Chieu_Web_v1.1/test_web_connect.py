import json
import shutil
import subprocess
import unittest
from web_connect import PROBE_JS, READ_LATEST_RESPONSE_JS


class WebConnectionTests(unittest.TestCase):
    def test_connection_probe_does_not_send_or_extract_messages(self):
        self.assertNotIn('Xin chào', PROBE_JS)
        self.assertNotIn('.click(', PROBE_JS)
        self.assertNotIn('.click(', PROBE_JS)
        # Probe reads only the latest reply fingerprint to correlate batches.
        self.assertIn("host !== 'chatgpt.com'", PROBE_JS)

    def run_dom(self, script, replies, *, host='chatgpt.com', stop=False):
        if not shutil.which('node'):
            self.skipTest('Node.js is required for DOM fixture tests')
        fixture = r'''
const replies = DATA.map(data => ({
  innerText:data.wrapper, textContent:data.wrapper,
  querySelectorAll: selector => selector === 'pre code' ?
    data.blocks.map(text => ({textContent:text})) : [],
  querySelector: selector => selector === '.markdown' ?
    {innerText:data.wrapper} : null
}));
global.location = {hostname:HOST}; global.window = {location};
global.getComputedStyle = () => ({visibility:'visible'});
const editor = {getClientRects:()=>[1],getAttribute:()=>null};
global.document = {querySelectorAll: selector => {
  if(selector === '[data-testid^="conversation-turn-"]' || selector === 'main .markdown, main pre code') return [];
  if(selector === '[data-message-author-role="assistant"]') return replies;
  if(selector.includes('#prompt-textarea')) return [editor];
  if(selector.includes('stop-button')) return STOP ? [editor] : [];
  throw new Error('Unexpected selector: '+selector);
}};
process.stdout.write(JSON.stringify(SCRIPT));
'''
        fixture = fixture.replace('DATA', json.dumps(replies)).replace('HOST', json.dumps(host)).replace('STOP', json.dumps(stop)).replace('SCRIPT', script)
        result = subprocess.run(['node', '-e', fixture], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_same_count_before_and_after_new_reply(self):
        old = {'wrapper':'old reply', 'blocks':[]}
        baseline = self.run_dom(PROBE_JS, [old])
        current = self.run_dom(READ_LATEST_RESPONSE_JS, [old])
        self.assertTrue(baseline['editor'])
        self.assertEqual(baseline['assistantCount'], current['assistantCount'])
        new = {'wrapper':'new reply', 'blocks':[]}
        current = self.run_dom(READ_LATEST_RESPONSE_JS, [old, new])
        self.assertEqual(current['assistantCount'], baseline['assistantCount']+1)
        self.assertEqual(current['text'], 'new reply')

    def test_json_excludes_copy_button_and_prose(self):
        payload = '{"items":[{"id":1,"vi":"Xin chào"}]}'
        reply = {'wrapper':'Here is the result\njson\nCopy code\n'+payload,
                 'blocks':['invalid block', payload]}
        result = self.run_dom(READ_LATEST_RESPONSE_JS, [reply])
        self.assertEqual(result['text'], payload)
        self.assertFalse(result['generating'])
        self.assertTrue(self.run_dom(READ_LATEST_RESPONSE_JS, [reply], stop=True)['generating'])

    def test_other_domain_does_not_read_messages(self):
        for script in (PROBE_JS, READ_LATEST_RESPONSE_JS):
            result = self.run_dom(script, [], host='example.com')
            self.assertFalse(result['site'])
            self.assertEqual(result['assistantCount'], 0)


if __name__ == '__main__':
    unittest.main()
