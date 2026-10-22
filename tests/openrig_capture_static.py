"""Pure real-terminal wrapping checks; no rigs, models or CLI execution."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from openrig_acceptance import captured_adapter

class CaptureGuards(unittest.TestCase):
 def value(self,content,session='seat@rig',ok=True):return json.dumps({'ok':ok,'sessionName':session,'content':content})
 def test_actual_full_adapter_path_spanning_terminal_rows(self):
  adapter=Path('/private/frozen/scripts/openrig_hub.py');text='/private/frozen/scripts/op\nenrig_hub.py --binding /private/credential-file\n'
  self.assertEqual(captured_adapter(self.value(text),'seat@rig',adapter)['sessionName'],'seat@rig')
 def test_foreign_path_same_basename_does_not_qualify(self):
  with self.assertRaises(AssertionError):captured_adapter(self.value('/foreign/scripts/openrig_hub.py'),'seat@rig',Path('/private/frozen/scripts/openrig_hub.py'))
 def test_wrong_session_not_ok_or_nontext_rejected(self):
  for value in [self.value('/expected','foreign'),self.value('/expected',ok=False),self.value(42)]:
   with self.assertRaises(AssertionError):captured_adapter(value,'seat@rig',Path('/expected'))
 def test_malformed_json_rejected(self):
  with self.assertRaises(json.JSONDecodeError):captured_adapter('{','seat@rig',Path('/expected'))

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No CLI/runtime start')):unittest.main()
