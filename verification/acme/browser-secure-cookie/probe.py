import asyncio,hashlib,importlib.metadata,json,os,platform,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
TOKEN='owned-synthetic-cookie-witness'
CHROME=Path('/home/horde/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell')
NODE=Path('/home/horde/src/adhd/.worktrees/acceptance/_build/openrig/runtime/node_modules/node/bin/node')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def identity(pid):
    try:
        s=Path(f'/proc/{pid}/stat').read_text();return s[s.rfind(')')+2:].split()[19]
    except FileNotFoundError:return None
def descendants(pid):
    found={}
    try:children=Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
    except FileNotFoundError:return found
    for child in children:
        p=int(child);start=identity(p)
        if start:found[p]=start
        found.update(descendants(p))
    return found
async def main():
    result={'schema':'adhd/chromium-loopback-secure-cookie-probe@1','passed':False,'application_starts':0,'ca_starts':0,'actual_socket_services':0,'network_policy':'Every browser request fulfilled by owned Playwright route; no route.continue and no real server/DNS target required. Synthetic cookie only.','tools':{'python':platform.python_version(),'playwright':importlib.metadata.version('playwright'),'chromium_executable_sha256':sha(CHROME),'node_sha256':sha(NODE)},'observations':[],'owned_processes':{},'cleanup':False}
    primary=None
    try:
      async with async_playwright() as pw:
        context=await pw.chromium.launch_persistent_context(str(ROOT/'profile'),executable_path=str(CHROME),headless=True,args=['--no-sandbox'],viewport={'width':800,'height':600})
        result['tools']['chromium_version']=context.browser.version
        try:
          issued={};sent={}
          async def route(r):
            url=r.request.url
            assert r.request.method=='GET'
            if url.endswith('/admin/set'):
              issued[url]=True
              await r.fulfill(status=200,headers={'content-type':'text/html','Set-Cookie':'adhd_session='+TOKEN+'; Path=/admin; HttpOnly; SameSite=Lax; Secure'},body='<html><title>Owned cookie test</title><body>set</body></html>')
            elif url.endswith('/admin/check'):
              sent[url]=(await r.request.all_headers()).get('cookie','')
              await r.fulfill(status=200,headers={'content-type':'text/html'},body='<html><title>Owned cookie test</title><body>check</body></html>')
            else:raise AssertionError('Unexpected owned test request')
          await context.route('**/*',route)
          page=context.pages[0]
          page.set_default_timeout(10000)
          for scheme,host in [('http','127.0.0.1'),('http','127.0.0.2'),('http','localhost'),('http','cookie-fixture.invalid'),('https','cookie-fixture.invalid')]:
            await context.clear_cookies()
            base=f'{scheme}://{host}:18999'
            await page.goto(base+'/admin/set')
            cookies=await context.cookies()
            await page.goto(base+'/admin/check')
            header=sent[base+'/admin/check']
            row={'scheme':scheme,'host':host,'set_response_observed':issued[base+'/admin/set'],'secure_context':await page.evaluate('isSecureContext'),'cookie_stored':any(c['name']=='adhd_session' for c in cookies),'secure_cookie_sent_on_check':header=='adhd_session='+TOKEN,'httponly_hidden_from_document_cookie':await page.evaluate('document.cookie')=='','stored_cookie_properties':[{k:c[k] for k in ['name','secure','httpOnly','sameSite','path']} for c in cookies]}
            result['observations'].append(row)
          result['owned_processes']={str(p):start for p,start in descendants(os.getpid()).items()}
          assert result['observations'][0]['set_response_observed']
        finally:await context.close()
      result['cleanup']=all(identity(int(p))!=start for p,start in result['owned_processes'].items())
      assert result['cleanup']
      result['passed']=True
    except BaseException as e:
      result['failure_type']=type(e).__name__;primary=e
    finally:
      result['tools']['chromium_executable_unchanged']=sha(CHROME)==result['tools']['chromium_executable_sha256']
      result['tools']['node_unchanged']=sha(NODE)==result['tools']['node_sha256']
      result['probe_sha256']=sha(__file__)
      (ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if primary:raise primary
    print(json.dumps(result))
asyncio.run(main())
