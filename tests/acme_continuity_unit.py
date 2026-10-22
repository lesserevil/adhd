"""Pure custody checks, no provider process/socket or hub starts."""
from http.cookiejar import Cookie
from types import SimpleNamespace
import unittest

from acme_continuity import redirect_to, secure_cookies


def cookie(secure=True, rest=None):
    return Cookie(version=0,name='session',value='not-a-real-session',port=None,port_specified=False,
                  domain='one.acme.test',domain_specified=False,domain_initial_dot=False,path='/',path_specified=True,
                  secure=secure,expires=None,discard=True,comment=None,comment_url=None,
                  rest={'HttpOnly':None,'SameSite':'Lax'} if rest is None else rest,rfc2109=False)


class ContinuityChecks(unittest.TestCase):
    def test_redirect_follows_only_exact_owned_authority(self):
        base='https://one.acme.test:18443'
        self.assertEqual(redirect_to(base+'/admin/oidc/callback?state=fixed&code=fixed',base),
                         '/admin/oidc/callback?state=fixed&code=fixed')
        for value in ('http://one.acme.test:18443/admin/oidc/callback',
                      'https://foreign.acme.test:18443/admin/oidc/callback',
                      'https://one.acme.test:18444/admin/oidc/callback',
                      'https://user@one.acme.test:18443/admin/oidc/callback',
                      base+'/admin/oidc/callback#fragment'):
            with self.assertRaises(AssertionError):redirect_to(value,base)

    def test_cookie_checks_require_all_security_attributes(self):
        secure_cookies(SimpleNamespace(cookies=[cookie()]))
        for cookies in ([],[cookie(secure=False)],[cookie(rest={'SameSite':'Lax'})],
                        [cookie(rest={'HttpOnly':None,'SameSite':'None'})]):
            with self.assertRaises(AssertionError):secure_cookies(SimpleNamespace(cookies=cookies))


if __name__=='__main__':unittest.main()
