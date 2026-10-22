"""Pure diagnostic argv/join tests; no Elixir, Docker, socket or app starts."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from compiler_startup_observer import diagnostic_image_argv,owned_socket_rows

class CompilerObserverGuards(unittest.TestCase):
 def test_original_serve_argument_and_payload_unchanged(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);tracer=root/'compiler-tracer.exs';tracer.write_text('public tracer');image='sha256:'+'a'*64;argument=json.dumps(['serve',str(root/'config.json')]);argv=['docker','run','--name','owned','--mount',f'type=bind,src={root},dst={root}',image,argument]
   result=diagnostic_image_argv(argv,image,root,hashlib.sha256(tracer.read_bytes()).hexdigest())
   self.assertEqual(result[-1],argument);self.assertEqual(result[result.index(image)+1:],['-r',str(tracer),'/app/hub.exs',argument]);self.assertEqual(argv[-2:],[image,argument]);self.assertFalse((root/'compiler-events.tsv').exists())
 def test_existing_trace_or_wrong_hash_refuses_before_launch(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);p=root/'compiler-tracer.exs';p.write_text('tracer');image='image';argv=['docker','run','--mount',f'type=bind,src={root},dst={root}',image,json.dumps(['serve',str(root/'config.json')])]
   with self.assertRaises(AssertionError):diagnostic_image_argv(argv,image,root,'0'*64)
   (root/'compiler-events.tsv').write_text('old')
   with self.assertRaises(AssertionError):diagnostic_image_argv(argv,image,root,hashlib.sha256(p.read_bytes()).hexdigest())
 def test_shared_namespace_foreign_listeners_excluded(self):
  text='0: 0100007F:1234 00000000:0000 0A 0:0 0:0 0 1003 0 111\n1: 0100007F:1235 00000000:0000 0A 0:0 0:0 0 1003 0 222\n16 -> socket:[222]\n'
  value=owned_socket_rows(text);self.assertEqual([r['inode'] for r in value['joined_listeners']],['222']);self.assertNotIn('111',str(value))

if __name__=='__main__':
 with patch('subprocess.Popen',side_effect=AssertionError('No process start')):unittest.main()
