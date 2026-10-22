#!/usr/bin/env python3
"""Browser regression for the embedded console after a full hub rebuild.

Requires the SDK test requirements and the optional Playwright/Chromium test tools.
Screenshots and accessibility snapshots stay under the ignored work directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright, expect

from federation_acceptance import Hub
from hub_acceptance import ModelFixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command', required=True, help='JSON argv excluding application JSON argument')
    parser.add_argument('--work-dir', default='_build/federation/browser')
    parser.add_argument('--report', default='verification/federation-browser.json')
    args = parser.parse_args()
    parent = Path(args.work_dir).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    model = ModelFixture()
    hub = Hub(json.loads(args.command), root / 'hub', 'console-regression', model.url)
    hub.config.pop('federation')
    results = []
    try:
        hub.start()
        hub.call({'op': 'publish', 'text': 'Federation upgrade regression publication',
                  'information_type': 'status', 'data': {'literal': '<script>throw 1</script>'}})
        hub.call({'op': 'send', 'recipient_id': 'bob', 'text': 'PRIVATE_UI_SENTINEL'})
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            for name, viewport in [('desktop', {'width': 1440, 'height': 1000}),
                                   ('mobile', {'width': 390, 'height': 844})]:
                context = browser.new_context(viewport=viewport)
                page = context.new_page()
                failures = []
                page.on('pageerror', lambda error: failures.append(str(error)))
                page.on('console', lambda message: failures.append(message.text) if message.type == 'error' else None)
                page.on('requestfailed', lambda req: failures.append('request failed: ' + req.url))
                page.on('response', lambda res: failures.append('HTTP ' + str(res.status)) if res.status >= 400 else None)
                page.goto(hub.base + '/admin')
                page.get_by_label('Administrator token').fill(hub.config['admin_token'])
                page.get_by_role('button', name='Sign in', exact=True).click()
                expect(page.get_by_role('heading', name='Overview', exact=True)).to_be_visible()
                page.get_by_role('button', name='Information', exact=True).click()
                page.get_by_label('Search text').fill('Federation upgrade regression')
                page.get_by_role('button', name='Search', exact=True).click()
                expect(page.get_by_text('Federation upgrade regression publication', exact=True)).to_be_visible()
                page.get_by_role('button', name='View details', exact=True).click()
                expect(page.get_by_role('heading', name='Publication details')).to_be_visible()
                expect(page.locator('pre').first).to_contain_text('<script>throw 1</script>')

                page.get_by_role('button', name='Subscriptions', exact=True).click()
                page.get_by_label('Owner agent').select_option('bob')
                page.get_by_label('Subscription description').fill('Browser regression client updates')
                page.get_by_role('button', name='Create subscription', exact=True).click()
                expect(page.get_by_text('Browser regression client updates', exact=True)).to_be_visible()
                page.once('dialog', lambda dialog: dialog.dismiss())
                page.get_by_role('button', name='Remove', exact=True).click()
                expect(page.get_by_text('Browser regression client updates', exact=True)).to_be_visible()
                page.once('dialog', lambda dialog: dialog.accept())
                page.get_by_role('button', name='Remove', exact=True).click()
                expect(page.get_by_text('Browser regression client updates', exact=True)).not_to_be_visible()

                page.get_by_role('button', name='Activity', exact=True).click()
                expect(page.get_by_role('heading', name='Deliveries', exact=True)).to_be_visible()
                assert 'PRIVATE_UI_SENTINEL' not in page.locator('body').inner_text()
                page.get_by_role('button', name='Overview', exact=True).click()
                page.get_by_role('button', name='Refresh', exact=True).click()
                expect(page.get_by_text('Service reachable', exact=True)).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not page.get_by_text('NaN', exact=True).count()
                screenshot = root / (name + '.png')
                page.screenshot(path=str(screenshot), full_page=True)
                (root / (name + '-accessibility.txt')).write_text(page.locator('body').aria_snapshot())
                assert not failures, failures
                page.get_by_role('button', name='Log out', exact=True).click()
                expect(page.get_by_label('Administrator token')).to_be_visible()
                assert 'console-regression' not in page.locator('body').inner_text()
                assert page.evaluate('localStorage.length + sessionStorage.length') == 0
                assert not context.cookies()
                page.reload()
                expect(page.get_by_label('Administrator token')).to_be_visible()
                results.append({'viewport': viewport, 'passed': True, 'normal_path_errors': failures,
                                'screenshot': str(screenshot.relative_to(Path.cwd()))})
                context.close()
            browser.close()
        Path(args.report).write_text(json.dumps({'schema': 'adhd/console-regression@1',
                                                'passed': True, 'artifact_sha256': hashlib.sha256(Path(json.loads(args.command)[-1]).read_bytes()).hexdigest(), 'viewports': results}, indent=2) + '\n')
        print('PASS console browser regression at desktop and mobile widths')
    finally:
        hub.stop()
        model.close()


if __name__ == '__main__':
    main()
