"""Full frozen-tree custody probes; no hub, Docker or provider execution."""
from pathlib import Path
import tempfile
from image_qualification_inputs import verify_frozen_inputs, prepare_runtime_cwd, sha


def denied(root, inputs):
    try:
        verify_frozen_inputs(root, inputs)
    except (AssertionError, OSError):
        return
    raise AssertionError('Changed frozen tree admitted')


def main():
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory).resolve()
        frozen = work / 'frozen'
        (frozen / 'tests').mkdir(parents=True)
        helper = frozen / 'tests/helper.py'
        helper.write_text('original helper\n')
        examples = frozen / 'docs/protocol/examples.json'
        examples.parent.mkdir(parents=True)
        examples.write_text('{"fixture":true}\n')
        inputs = {str(p.relative_to(frozen)): sha(p) for p in (helper, examples)}
        assert verify_frozen_inputs(frozen, inputs)
        runtime, bound = prepare_runtime_cwd(work, frozen, inputs)
        assert runtime.parent == frozen.parent and not runtime.is_relative_to(frozen)
        assert bound == {'runtime/docs/protocol/examples.json': sha(examples)}
        original = helper.read_bytes()
        helper.write_bytes(b'changed helper\n'); denied(frozen, inputs); helper.write_bytes(original)
        shadow = frozen / 'tests/shadow.py'
        shadow.write_text('unlisted module'); denied(frozen, inputs); shadow.unlink()
        extra = frozen / 'empty-unlisted-directory'
        extra.mkdir(); denied(frozen, inputs); extra.rmdir()
        helper.unlink(); helper.symlink_to(examples); denied(frozen, inputs)
        helper.unlink(); helper.write_bytes(original)
        alias = frozen / 'redirected-directory'
        alias.symlink_to(runtime, target_is_directory=True); denied(frozen, inputs); alias.unlink()
        redirected_root = work / 'root-alias'
        redirected_root.symlink_to(frozen, target_is_directory=True); denied(redirected_root, inputs)
        ancestor = work / 'ancestor-alias'
        ancestor.symlink_to(work, target_is_directory=True); denied(ancestor / 'frozen', inputs)
        assert verify_frozen_inputs(frozen, inputs)
    print('PASS frozen inputs9: exact tree, external runtime fixture, changed bytes, shadow module, extra directory, file symlink, directory symlink, root symlink, redirected ancestor')


if __name__ == '__main__':
    main()
