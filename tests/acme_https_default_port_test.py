"""Actual nested HTTPS client default-port guard with mocked TLS/socket only."""
import importlib.util
import socket
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import HTTPSHandler

spec=importlib.util.spec_from_file_location('acme_runtime_default_port_review',Path(__file__).with_name('acme_runtime.py'))
runtime=importlib.util.module_from_spec(spec)
# These tests never instantiate a native launcher/process observer.
with patch.dict('sys.modules',{'acme_process_observer':SimpleNamespace(Descendants=object)}):spec.loader.exec_module(runtime)

class DefaultPort(unittest.TestCase):
 def connection(self,base,authority):
  context=SimpleNamespace(minimum_version=None)
  transport=SimpleNamespace(getpeercert=lambda binary_form:b'actual-test-der',version=lambda:'TLSv1.3')
  context.wrap_socket=lambda sock,server_hostname:transport
  handlers=[]
  def opener(*values):handlers.extend(values);return SimpleNamespace()
  with patch.object(runtime.ssl,'create_default_context',return_value=context),patch.object(runtime,'build_opener',side_effect=opener):
   client=runtime.PublicClient(base,trust=Path('/unused/mock-root.pem'))
  handler=next(h for h in handlers if isinstance(h,HTTPSHandler))
  def do_open(connection,request):
   value=connection(authority,timeout=3);value.connect();return value
  handler.do_open=do_open
  with patch.object(runtime.socket,'create_connection',return_value=object()) as connect:
   try:value=handler.https_open(object())
   except AssertionError:
    connect.assert_not_called();raise
   connect.assert_called_once_with(('127.0.0.1',value.port),3)
  self.assertTrue(client.handshakes[-1]['verified_chain_and_hostname'])
  return value
 def test_implicit_and_explicit_default_443_use_actual_443(self):
  for base in ['https://one.acme.test','https://one.acme.test:443']:
   with self.subTest(base=base):self.assertEqual(self.connection(base,'one.acme.test').port,443)
 def test_nondefault_port_remains_exact(self):
  self.assertEqual(self.connection('https://one.acme.test:18443','one.acme.test:18443').port,18443)
 def test_wrong_port_or_hostname_never_connect(self):
  for base,authority in [('https://one.acme.test','one.acme.test:444'),('https://one.acme.test:18443','one.acme.test:443'),('https://one.acme.test','other.acme.test')]:
   with self.subTest(base=base,authority=authority),self.assertRaises(AssertionError):self.connection(base,authority)

if __name__=='__main__':unittest.main()
