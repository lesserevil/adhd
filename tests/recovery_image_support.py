"""Narrow retained-image custody and final evidence for owned HTTP recovery tests."""
import sys
from image_filesystem_fault import RetainedImage


def retained_recovery_fixture(fixture):
    if fixture.args.image:
        fixture.image_runtime=RetainedImage(fixture.args.image,fixture.args.image_manifest,fixture.root)
    return fixture


async def close_recovery_fixture(fixture,evidence):
    # Called from the owning main's finally, so preserve its in-flight exception
    # while still closing and writing the final actual image lifecycle.
    primary=sys.exception();errors=[]
    try:await fixture.close()
    except BaseException as error:errors.append(error)
    runtime=getattr(fixture,'image_runtime',None)
    if errors and runtime is not None and runtime.name is not None:
        # An SDK client's close can fail before Fixture reaches image cleanup.
        # Still attempt the independently owned container closure; retain the
        # first close failure even when this fallback establishes absence.
        try:
            runtime.stop()
            if fixture.process:fixture.process.wait(timeout=15)
        except BaseException as error:errors.append(error)
    try:fixture.bind_evidence(evidence)
    except BaseException as error:errors.append(error)
    if primary is not None or errors:
        failure=primary or errors[0]
        evidence.value.update(passed=False,failure_type=type(failure).__name__)
    if errors:
        evidence.value['cleanup_failure_types']=[type(error).__name__ for error in errors]
        if primary is not None:primary.add_note('Recovery fixture cleanup failure: '+','.join(type(error).__name__ for error in errors))
    try:evidence.write()
    except BaseException as error:
        if primary is not None:primary.add_note('Recovery fixture evidence failure: '+type(error).__name__)
        elif errors:errors[0].add_note('Recovery fixture evidence failure: '+type(error).__name__)
        else:raise
    if errors and primary is None:raise errors[0]
