"""Pure copied-input guards; no CLI, VM, CA, socket or process starts."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from acme_rebind_acceptance import inventory, disjoint, request_for


class RebindChecks(unittest.TestCase):
    def test_disjoint_and_redirected_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            old=root/'old';old.mkdir()
            self.assertEqual(disjoint(old,root/'new'),(old,root/'new'))
            for bad in (old,old/'nested',root):
                with self.assertRaises(AssertionError):disjoint(old,bad)
            (root/'redirect').symlink_to(old,target_is_directory=True)
            with self.assertRaises(AssertionError):disjoint(root/'redirect',root/'new')

    def test_inventory_never_follows_or_accepts_linked_private_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);private=root/'key';private.write_bytes(b'pure-placeholder')
            self.assertEqual(set(inventory(root)),{'key'})
            (root/'redirect').symlink_to(private)
            with self.assertRaises(AssertionError):inventory(root)
            (root/'redirect').unlink()
            os.link(private,root/'hardlink')
            with self.assertRaises(AssertionError):inventory(root)

    def test_complete_request_maps_actual_new_files_not_old_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            config=new/'hub.json';config.write_text('{}')
            projects={}
            for name in ('red','blue'):
                (new/(name+'.dets')).write_bytes(('owned-'+name).encode())
                (new/(name+'.dets.snapshot')).write_bytes(('snapshot-'+name).encode())
                projects[name]={'initialized':True,'storage_anchor':str(old/(name+'.dets')),'generation':7}
            projects['unused']={'initialized':False,'storage_anchor':str(old/'absent'),'generation':0}
            registry={'config_file':str(old/'hub.json'),'server_id':'0'*32,'projects':projects}
            Path(str(config)+'.stores').write_text(json.dumps(registry))
            for suffix in ('.recovery','.stores.marker'):
                Path(str(config)+suffix).write_text('{}')
            request=request_for(config)
            self.assertEqual({row['project_id']for row in request['stores']},{'red','blue'})
            self.assertTrue(all(Path(row['store_path']).parent==new for row in request['stores']))
            self.assertIsNone(request['expected_config_journal_sha256'])
            self.assertTrue(request['confirm_stopped'])
            registry['projects']['red']['storage_anchor']=str(root/'foreign.dets')
            Path(str(config)+'.stores').write_text(json.dumps(registry))
            with self.assertRaises(AssertionError):request_for(config)

    def test_preload_refuses_changed_or_untrusted_module_names_before_dispatch(self):
        import hashlib
        from acme_runtime import verified_preload_code
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);beams={}
            for index in range(64):
                name='Elixir.Capsule.Module'+str(index)+'.beam'
                path=root/name;path.write_bytes(('trusted-module-'+str(index)).encode())
                beams[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            code=verified_preload_code(root,{'beams':beams})
            self.assertEqual(code.count('Elixir.Capsule.Module'),64)
            self.assertIn('Code.ensure_loaded(module)',code)
            name=next(iter(beams));(root/name).write_bytes(b'changed')
            with self.assertRaisesRegex(AssertionError,'closure changed'):
                verified_preload_code(root,{'beams':beams})
            bad=dict(beams);bad['../../snapshot-data.beam']=bad.pop(name)
            with self.assertRaises(AssertionError):verified_preload_code(root,{'beams':bad})


if __name__=='__main__':unittest.main()
