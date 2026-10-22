"""Metadata-only capture. No CLI invocation, generated code, provider or compiler."""
import sys
sys.dont_write_bytecode=True
import os,json,hashlib,stat
from pathlib import Path
from argparse import Namespace
ROOT=Path('/home/horde/src/adhd')
OUT=ROOT/'_build/roadmap/final/eventing-ready41-metadata01'
OLD=ROOT/'.worktrees/ownership/_build/s40'
CANDIDATE=ROOT/'_build/roadmap/final/eventing-ready41-01/retained-source'
CHECKPOINT=ROOT/'_build/roadmap/final/eventing-ready41-01/build/standard-checkpoints'
assert Path.cwd()==ROOT and not OUT.exists()
# Fail before any process execution or write outside the sole fresh output root.
blocked=[]
def audit(event,args):
    if event in ('subprocess.Popen','os.system','os.posix_spawn','os.exec','os.fork'):
        blocked.append(event);raise RuntimeError('Metadata capture forbids process execution')
    if event=='open':
        path,mode,flags=args
        writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
        if writing and (not isinstance(path,(str,bytes,os.PathLike)) or not Path(path).absolute().is_relative_to(OUT)):
            blocked.append('write-outside-output');raise RuntimeError('Metadata output boundary')
    if event in ('os.mkdir','os.remove','os.rename','os.rmdir','os.chmod'):
        path=args[0]
        if not isinstance(path,(str,bytes,os.PathLike)) or not Path(path).absolute().is_relative_to(OUT):
            blocked.append(event);raise RuntimeError('Metadata output boundary')
sys.addaudithook(audit)
from literate_ai.cli.generation import _prepare_generation
from literate_ai.contracts import StandardLifecycleAttemptEvidence,CycloneDxLifecycle,canonical_json_bytes
from literate_ai.adapters.dependencies import build_cyclonedx_bom,validate_cyclonedx_bom
from literate_ai.adapters.models.coding_cli import (_recipe_authority_sbom,_require_recipe_authority_sbom,_acceptance_argument_vectors,_acceptance_result_shape)
from literate_ai.generated_tests import validate_generated_test_suite

def digest(data):return hashlib.sha256(data).hexdigest()
def read(p):
    assert p.resolve(strict=True)==p and p.is_file() and not p.is_symlink()
    return p.read_bytes()
def files(root):
    found={}
    for p in sorted(root.rglob('*')):
        assert not p.is_symlink()
        if p.is_file():found[str(p.relative_to(root))]=digest(read(p))
        else:assert p.is_dir()
    return found
old_before=files(OLD);candidate_before=files(CANDIDATE)
assert len(old_before)==58 and len(candidate_before)==56
assert old_before['tests/litai_test.exs']==candidate_before['tests/litai_test.exs']
lock_path=ROOT/'components/hub/component.lock.json';lock_bytes=read(lock_path)
assert digest(canonical_json_bytes(json.loads(lock_bytes)))=='8ddfce987f2714a74170354bec7da2b31af4081e521f2328c508bc926a1a796a'
prepared=_prepare_generation(Namespace(specification='components/hub',target='host',flavor=[],flavor_root=[],recipe_id=None))
recipe=prepared.recipe;lock=prepared.locked_authority_snapshot.authority.lock
assert lock.identity.uri=='sha256:'+digest(canonical_json_bytes(json.loads(lock_bytes)))
heads=list((CHECKPOINT/'attempt-heads').glob('*.json'));matches=[]
for head in heads:
    ref=json.loads(read(head));raw=read(CHECKPOINT/'objects/blobs/sha256'/ref['digest'][:2]/ref['digest'])
    assert digest(raw)==ref['digest'] and len(raw)==ref['size']
    attempt=StandardLifecycleAttemptEvidence.from_dict(json.loads(raw))
    if attempt.component_revision==lock.root_revision:matches.append((head,ref,attempt))
assert len(matches)==1
head,ref,attempt=matches[0]
# The actual failed lifecycle's node recipe is distinct from the aggregate
# metadata preparation recipe. Bind its exact recorded identity, never guess.
current_recipe_identity=attempt.recipe_identity.uri
assert current_recipe_identity=='sha256:e71bcacddf5d48f65db0d32b14fa6f139ab20abfd0322dd2b0f43fafe7a65a95'
assert current_recipe_identity!=lock.root_revision.uri
manifest=json.loads(read(OLD/'tests/manifest.json'))
original_cases=canonical_json_bytes(manifest['cases'])
assert len(manifest['cases'])==18 and len({c['case_id']for c in manifest['cases']})==18
old_recipe_identity=manifest['recipe_identity'];manifest['recipe_identity']=current_recipe_identity
encoded=canonical_json_bytes(manifest)
suite=validate_generated_test_suite(encoded,recipe_identity=current_recipe_identity,specification_references=recipe.non_acceptance_document_paths,acceptance_arguments=_acceptance_argument_vectors(recipe),result_shape=_acceptance_result_shape(recipe))
assert original_cases==canonical_json_bytes(manifest['cases'])
extras,edges=_recipe_authority_sbom(recipe)
bom,binding=build_cyclonedx_bom(lifecycle=CycloneDxLifecycle.SOURCE,managed_graph=recipe.managed_sbom_graph,additional_components=extras,additional_edges=edges,composition_aggregate='complete')
validated=validate_cyclonedx_bom(bom,lifecycle=CycloneDxLifecycle.SOURCE,managed_graph=recipe.managed_sbom_graph)
assert binding==validated
_require_recipe_authority_sbom(bom,recipe)
assert read(lock_path)==lock_bytes and old_before==files(OLD) and candidate_before==files(CANDIDATE)
assert blocked==[]
OUT.mkdir(mode=0o700);(OUT/'tests').mkdir(mode=0o700);(OUT/'.literate').mkdir(mode=0o700)
(OUT/'tests/manifest.json').write_bytes(encoded);(OUT/'.literate/sbom.cdx.json').write_bytes(bom)
projection=json.loads(bom);root=projection['metadata']['component']
assert root['bom-ref']=='urn:literate-ai:component:'+lock.root_revision.digest
report={
 'schema':'adhd/source41-sidecar-metadata-capture@1','passed':True,'metadata_only':True,
 'current_component_lock_identity':lock.identity.uri,'current_component_revision':lock.root_revision.uri,
 'official_failed_attempt_head':str(head.relative_to(ROOT)),'official_failed_attempt_head_sha256':digest(read(head)),
 'official_attempt_blob_sha256':ref['digest'],'official_node_recipe_identity':current_recipe_identity,
 'aggregate_preparation_recipe_identity':recipe.identity,'recipe_identity_equals_component_revision':False,
 'old_manifest_recipe_identity':old_recipe_identity,'test_cases':18,'exact_case_records_conserved':True,'case_records_sha256':digest(original_cases),
 'native_test_sha256':candidate_before['tests/litai_test.exs'],'manifest_validator_passed':True,'BOM_validator_passed':True,'recipe_authority_BOM_validator_passed':True,
 'BOM_schema':projection['$schema'],'BOM_version':projection['specVersion'],'BOM_graph_identity':recipe.managed_sbom_graph.resolved_graph_identity.uri,
 'BOM_root_ref':root['bom-ref'],'BOM_authority_components':len(extras),'BOM_authority_edges':len(edges),
 'old_58_files_unchanged':old_before==files(OLD),'candidate_56_files_unchanged':candidate_before==files(CANDIDATE),
 'old_sidecar_sha256':{n:old_before[n]for n in ('tests/manifest.json','.literate/sbom.cdx.json')},
 'new_sidecar_sha256':{'tests/manifest.json':digest(encoded),'.literate/sbom.cdx.json':digest(bom)},
 'source_runtime_compiler_provider_or_CLI_executions':0,'receipt_writes':0,'blocked_forbidden_operations':blocked,
 'framework_module_paths':{'recipe_preparation':'literate_ai.cli.generation._prepare_generation','BOM_builder':'literate_ai.adapters.dependencies.build_cyclonedx_bom','suite_validator':'literate_ai.generated_tests.validate_generated_test_suite'},
 'followup':'Root must independently review exact metadata, copy only these two files into a NEW complete58file retained snapshot, recapture treeidentity and fresh authorization, then schedule the properCLI lifecycle. Failed41-01 and oldsidecars remain unchanged.'}
(OUT/'result.json').write_bytes(json.dumps(report,indent=2).encode()+b'\n')
(OUT/'recipe-authority.json').write_bytes(canonical_json_bytes({'managed_graph':recipe.managed_sbom_graph.to_dict(),'authority_components':extras,'authority_edges':edges,'resolved_inputs':recipe.resolved_inputs,'non_acceptance_document_paths':recipe.non_acceptance_document_paths}))
assert old_before==files(OLD) and candidate_before==files(CANDIDATE) and read(lock_path)==lock_bytes
print(json.dumps({'passed':True,'output':str(OUT),'actual_recipe_identity':current_recipe_identity,'result_sha256':digest(read(OUT/'result.json'))}))
