"""Pure reviewed-plan/report/once guards; no Docker, hub or provider processes."""
import json
from pathlib import Path
import tempfile
import shutil
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import patch
import multi_image_core_matrix
from multi_image_core_matrix import sha, report_passed, reviewed_plan, claim_execution


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        driver = root / 'driver.py'
        driver.write_text('reviewed driver bytes\n')
        plan = {'driver_sha256': sha(driver)}
        (root / 'plan.json').write_text(json.dumps(plan))
        reviewed = sha(root / 'plan.json')
        assert reviewed_plan(root, reviewed, driver) == plan
        other = root / 'unreviewed.py'
        other.write_text('different driver bytes\n')
        for expected, running in (('0' * 64, driver), (reviewed, other)):
            try:
                reviewed_plan(root, expected, running)
            except AssertionError:
                pass
            else:
                raise AssertionError('Unreviewed plan/driver admitted')
        claim_execution(root, reviewed, sha(driver))
        try:
            claim_execution(root, reviewed, sha(driver))
        except FileExistsError:
            pass
        else:
            raise AssertionError('A second execution overwrote the first attempt')
        report = root / 'report.json'
        assert not report_passed(report)
        for value in (None, [], {'passed': 1}, {'passed': False}):
            report.write_text(json.dumps(value))
            assert not report_passed(report)
        report.write_text('{invalid')
        assert not report_passed(report)
        report.write_text('{"passed":true}')
        assert report_passed(report)
    # Exercise the real execute entrypoint, rather than only its helper guards.
    # The mock constructor is the first custody/runtime boundary; reaching it
    # proves execute has passed actual parsing/tree/bindings/once checks without
    # using any Docker or other process launch.
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory).resolve();frozen=work/'frozen';(frozen/'tests').mkdir(parents=True)
        marker=frozen/'tests/marker.py';marker.write_text('# frozen unit marker\n')
        legacy=work/'legacy.exs';legacy.write_text('hash binding only, never executed')
        driver=Path(multi_image_core_matrix.__file__).resolve();shutil.copyfile(driver,work/'driver.py')
        plan={'driver_sha256':sha(driver),'legacy_hub':str(legacy),'legacy_sha256':sha(legacy),
            'frozen_inputs':{'tests/marker.py':sha(marker)},'bound_inputs':{},
            'foundation_flock_sha256':sha(Path('/usr/bin/flock')),'image_config_identity':'sha256:'+'a'*64}
        (work/'plan.json').write_text(json.dumps(plan));reviewed=sha(work/'plan.json')
        calls=[];starts=[]
        class CustodyBoundary(Exception):pass
        class Custody:
            def __init__(self,*args):calls.append(args);raise CustodyBoundary()
        def forbidden(*args,**kwargs):starts.append('attempt');raise AssertionError('No process permitted')
        previous_path=list(sys.path)
        try:
            with patch.object(sys,'argv',['driver','--execute','--repo-root',str(work),'--work',str(work),'--plan-sha256',reviewed]), \
                 patch.dict(sys.modules,{'container_fixture':SimpleNamespace(OwnedImage=Custody),
                                        'multi_eventing_matrix':SimpleNamespace(bounded_jobs=None)}), \
                 patch('subprocess.run',forbidden),patch('subprocess.Popen',forbidden),patch('subprocess.check_output',forbidden):
                try:multi_image_core_matrix.main()
                except CustodyBoundary:pass
                else:raise AssertionError('Actual execute entrypoint missed custody boundary')
        finally:sys.path[:]=previous_path
        assert len(calls)==1 and starts==[] and (work/'execution-started.json').is_file()
    # The interpreter starts importing helpers before main(). A frozen helper
    # import must never create __pycache__, even with the parent env flag absent.
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory).resolve();helper=root/'image_qualification_inputs.py'
        helper.write_text('verify_frozen_inputs=None\nprepare_runtime_cwd=None\n')
        previous_path=list(sys.path);previous_bytecode=sys.dont_write_bytecode
        saved=sys.modules.get('image_qualification_inputs')
        try:
            sys.path.insert(0,str(root))
            with patch('subprocess.run',forbidden),patch('subprocess.Popen',forbidden),patch('subprocess.check_output',forbidden):
                for name in ('multi_image_core_matrix.py','multi_eventing_matrix.py'):
                    sys.modules.pop('image_qualification_inputs',None);sys.dont_write_bytecode=False
                    runpy.run_path(str(Path(__file__).with_name(name)),run_name='pure_import_fixture')
                    assert not list(root.glob('__pycache__/*')), 'Runner imported frozen helper before disabling bytecode'
        finally:
            sys.path[:]=previous_path;sys.dont_write_bytecode=previous_bytecode
            sys.modules.pop('image_qualification_inputs',None)
            if saved is not None:sys.modules['image_qualification_inputs']=saved
        assert starts==[]
    print('PASS image core6: reviewed hash, actual driver, durable once admission, actual passed report, actual execute custody boundary, pre-main import cache denial; process attempts0')



if __name__ == '__main__':
    main()
