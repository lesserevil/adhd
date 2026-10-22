"""Pure reviewed-plan/report/once guards; no Docker, hub or provider processes."""
import json
from pathlib import Path
import tempfile
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
    print('PASS image core4: reviewed hash, actual driver, durable once admission, actual passed report')


if __name__ == '__main__':
    main()
