"""Pure HTTP recovery fixture finalization and retained-image selection."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from multi_support import Evidence
from recovery_image_support import retained_recovery_fixture,close_recovery_fixture


async def case(root,name,primary=None,cleanup=None,bind_error=None):
    evidence=Evidence(root/(name+'.json'),'synthetic-close');evidence.finish();calls=[]
    runtime=SimpleNamespace(name='synthetic-owned')
    def stop():calls.append('independent-image-stop');runtime.name=None
    runtime.stop=stop
    async def close():
        calls.append('fixture-close')
        if cleanup:raise cleanup
        runtime.name=None
    def bind(value):
        calls.append('bind-after-cleanup')
        if bind_error:raise bind_error
        value.value['runtime']={'cleanup_confirmed':runtime.name is None}
    fixture=SimpleNamespace(close=close,bind_evidence=bind,image_runtime=runtime,
        process=SimpleNamespace(wait=lambda **kwargs:calls.append('client-wait')))
    observed=None
    try:
        try:
            if primary:raise primary
        finally:await close_recovery_fixture(fixture,evidence)
    except BaseException as error:observed=error
    result=json.loads((root/(name+'.json')).read_text())
    assert calls[0]=='fixture-close' and calls[-1]=='bind-after-cleanup'
    if cleanup:assert calls==['fixture-close','independent-image-stop','client-wait','bind-after-cleanup']
    if primary:assert observed is primary and result['passed'] is False
    elif cleanup:assert observed is cleanup and result['passed'] is False
    elif bind_error:assert observed is bind_error and result['passed'] is False
    else:assert observed is None and result['passed'] is True
    if primary and cleanup:assert any('cleanup failure' in note for note in primary.__notes__)


async def checks(root):
    await case(root,'success')
    await case(root,'close-failed',cleanup=OSError('Synthetic close failure'))
    await case(root,'primary-only',primary=RuntimeError('Synthetic scenario failure'))
    await case(root,'both',primary=RuntimeError('Original scenario failure'),cleanup=OSError('Synthetic close failure'))
    await case(root,'binding-failed',bind_error=ValueError('Synthetic runtime proof failure'))


def main():
    with tempfile.TemporaryDirectory() as directory,patch('subprocess.Popen',side_effect=AssertionError('No actual process')),patch('subprocess.run',side_effect=AssertionError('No actual process')):
        root=Path(directory)
        native=SimpleNamespace(args=SimpleNamespace(image=None),image_runtime=None)
        assert retained_recovery_fixture(native) is native and native.image_runtime is None
        image=SimpleNamespace(args=SimpleNamespace(image='sha256:'+'a'*64,image_manifest=root/'manifest.json'),root=root)
        fake=object()
        with patch('recovery_image_support.RetainedImage',return_value=fake):assert retained_recovery_fixture(image).image_runtime is fake
        asyncio.run(checks(root))
    print('PASS HTTP recovery image support7: native untouched, explicit retained image, post-cleanup identity, close/binding failure false, primary preserved with independent image closure; process attempts0')


if __name__=='__main__':main()
