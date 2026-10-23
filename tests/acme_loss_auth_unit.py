"""Pure trusted postrestart auth/absolute-budget guards; no network starts."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import acme_image_faults as module

class LossAuthentication(unittest.TestCase):
    def exercise(self,*,request_error=None,late=False):
        runtime=SimpleNamespace(identities=[{'started_monotonic':0}]);keys={'actual-key':'public-witness'}
        client=Mock();client.handshakes=[{'der':b'actual-public-DER'}]
        clock={'value':1}
        def request(path,data=None,**kwargs):
            self.assertNotIn('headers',kwargs)  # Normal client Origin follows verified two hostname.
            self.assertGreater(kwargs['timeout'],0);self.assertLessEqual(kwargs['timeout'],5)
            if request_error:raise request_error
            if path=='/health':return 200,{},{}
            if path=='/admin/login':
                self.assertEqual(data,{'username':'admin','password':'private-fixture'})
                if late:clock['value']=42
                return 200,{},{}
            if path=='/admin/session':return 200,{'authenticated':True,'user':{'role':'Admin'},'csrf':'actual-session-csrf'},{}
            self.assertEqual(path,'/admin/api');self.assertEqual(data,{'op':'tls_status'})
            self.assertEqual(client.csrf,'actual-session-csrf')
            return 200,{'https_state':'ready','active_domains':['two.acme.test'],'certificate':{'sha256':'new-public-leaf'}},{}
        client.request.side_effect=request
        with patch.object(module,'PublicClient',return_value=client)as construct,\
             patch.object(module,'active_generation',side_effect=['a'*32,'b'*32]),\
             patch.object(module,'account_facts',return_value=(keys,{})),\
             patch.object(module,'certificate_facts',return_value={'leaf_der_sha256':'new-public-leaf'})as cert,\
             patch.object(module.time,'monotonic',side_effect=lambda:clock['value']),patch.object(module.time,'sleep'):
            result=module.authenticate_resumed_loss(runtime,Path('/owned'),'/owned/issuer.pem','private-fixture',
              'a'*32,'old-public-leaf',keys)
        construct.assert_called_once_with('https://two.acme.test:18443',trust='/owned/issuer.pem')
        self.assertEqual([call.args[0]for call in client.request.call_args_list],['/health','/admin/login','/admin/session','/admin/api'])
        cert.assert_called_once();self.assertEqual(cert.call_args.args[:2],(b'actual-public-DER',['two.acme.test']))
        self.assertTrue(result[1]['automatic_durable_resume_without_manual_renew'])
        self.assertNotIn('private-fixture',str(result));self.assertNotIn('actual-session-csrf',str(result))

    def test_fresh_verified_https_session_uses_aligned_origin_without_manual_renew(self):self.exercise()

    def test_tls_error_propagates_and_late_login_cannot_pass_absolute40(self):
        import ssl
        from urllib.error import URLError
        error=URLError(ssl.SSLCertVerificationError('synthetic name/trust failure'))
        with self.assertRaises(URLError)as caught:self.exercise(request_error=error)
        self.assertIs(caught.exception,error)
        with self.assertRaisesRegex(AssertionError,'exceeded40s'):self.exercise(late=True)

if __name__=='__main__':unittest.main()
