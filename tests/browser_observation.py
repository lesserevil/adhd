"""Strict browser diagnostics with allowances bound to actual Request objects."""
import hashlib
import re
from pathlib import Path


class BrowserObservation:
    def __init__(self, page, origin):
        self.origin=origin;self.responses=[];self.failed=[];self.console=[];self.errors=[];self.expected=[]
        page.on('response',lambda response:self.responses.append((response.request,response.status)) if response.status>=400 else None)
        page.on('requestfailed',lambda request:self.failed.append((request,request.failure)))
        page.on('console',lambda message:self.console.append((message.text,message.location)) if message.type=='error' else None)
        page.on('pageerror',lambda error:self.errors.append(str(error)))

    def allow(self,request,*,op,status=None,project=None,aborted=False):
        # Register only from the test's actual held route or expected response.
        assert request.url==self.origin+'/admin/api' and request.method=='POST'
        body=request.post_data_json
        assert isinstance(body,dict) and body.get('op')==op
        if project is not None:assert body.get('project_id')==project
        assert status in (None,401,403,404) and (status is not None or aborted)
        self.expected.append((request,status,aborted))

    def check(self):
        http=[];failed=[];console=[];allowed_http=[];allowed_aborts=[]
        for request,status in self.responses:
            if any(request is actual and status==code for actual,code,_ in self.expected):
                allowed_http.append((request,status))
            else:http.append({'url':request.url,'status':status})
        for request,error in self.failed:
            if error=='net::ERR_ABORTED' and any(request is actual and abort for actual,_,abort in self.expected):
                allowed_aborts.append(request)
            else:failed.append({'url':request.url,'error':error})
        # Chromium console messages lack Request identity. Allow their exact
        # resource URL/status text only when a matching actual expected response
        # was observed, at most once per response. Every HTTP event is still
        # independently checked by Request identity above.
        remaining=list(allowed_http)
        for text,location in self.console:
            match=re.fullmatch(r'Failed to load resource: the server responded with a status of (\d+)(?: \([^\n]*\))?',text)
            index=next((i for i,(request,status) in enumerate(remaining)
                if match and int(match[1])==status and location.get('url')==request.url),None)
            if index is None:console.append({'text':text,'location':location})
            else:remaining.pop(index)
        result={'page_errors':list(self.errors),'unexpected_http':http,'unexpected_request_failures':failed,
            'unexpected_console_errors':console,'expected_http_observed':len(allowed_http),
            'expected_aborts_observed':len(allowed_aborts),'captured_console_errors':len(self.console)}
        assert not (self.errors or http or failed or console),result
        return result


async def capture(page,directory,label):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not await page.get_by_text(re.compile(r'^(NaN|[+-]?Infinity)$')).count()
    assert not await page.locator('[href="undefined"],[href="null"],[src="undefined"],[src="null"]').count()
    png=directory/(label+'.png');structure=directory/(label+'.txt')
    await page.screenshot(path=str(png),full_page=True)
    structure.write_text(await page.locator('body').aria_snapshot())
    return {'name':label,'path':str(png),'structure_path':str(structure),
        'png_sha256':hashlib.sha256(png.read_bytes()).hexdigest(),
        'structure_sha256':hashlib.sha256(structure.read_bytes()).hexdigest()}
