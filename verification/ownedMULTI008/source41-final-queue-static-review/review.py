"""Read-only static review, using the project-pinned pure Markdown helpers."""
from pathlib import Path
from literate_ai.documentation import markdown_anchors, _visible_markdown_lines
import hashlib
import json
import os
import re
import subprocess

ROOT = Path('/home/horde/src/adhd')

def digest(path):
    assert path.is_file() and not path.is_symlink(), str(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    queue = ROOT / 'docs/roadmap/active-work.md'
    text = queue.read_text()
    parents = re.findall(r'^### \[([ x])\] ([A-Z]+-\d+) —', text, re.M)
    leaves = re.findall(r'^  - \[([ x])\]', text, re.M)
    assert len(parents) == 47 and all(flag == 'x' for flag, _ in parents)
    assert len(leaves) == 271 and all(flag == 'x' for flag in leaves)
    files = [ROOT / 'PROJECT.md', *sorted((ROOT / 'docs/roadmap').glob('*.md')),
             *sorted((ROOT / 'docs/history/roadmap').glob('*.md'))]
    link_count = 0
    for source in files:
        visible = '\n'.join(_visible_markdown_lines(source.read_text()))
        for link in re.findall(r'\]\(([^)]+)\)', visible):
            if '://' in link or link.startswith(('mailto:', 'app:')):
                continue
            name, _, fragment = link.partition('#')
            target = Path(os.path.normpath(str(source.parent / name))) if name else source
            assert target.exists(), (str(source), link)
            if fragment and target.suffix == '.md':
                assert fragment in markdown_anchors(target.read_text()), (str(source), link)
            link_count += 1
    before = subprocess.check_output(['git', 'show', '617e5e7^:docs/roadmap/active-work.md'], cwd=ROOT, text=True)
    anchors = []
    for parent in ('MULTI-007', 'KAFKA-007', 'KAFKA-008', 'KAFKA-009', 'MULTI-008', 'INTEROP-001'):
        heading = re.search(r'^### \[ \] ' + parent + r' — .+$', before, re.M).group(0)
        anchor = next(iter(markdown_anchors(heading)))
        assert '<a id="' + anchor + '"></a>' in text
        anchors.append({'parent': parent, 'preclose_heading': heading, 'stable_anchor': anchor})
    aliases = ('fed-003--publish-information-catalogs-and-route-queries-to-canonical-source-owners',
               'proto-001--specify-and-verify-every-federated-system-wire-protocol-rigorously')
    for anchor in aliases:
        assert '<a id="' + anchor + '"></a>' in text
        assert '#' + anchor in (ROOT / 'PROJECT.md').read_text()
    plans = []
    for name in ('multi-project', 'kafka-pubsub', 'project-restore'):
        old = ROOT / f'docs/roadmap/{name}.md'
        archive = ROOT / f'docs/history/roadmap/{name}.md'
        prior = subprocess.check_output(['git', 'show', f'617e5e7^:docs/roadmap/{name}.md'], cwd=ROOT, text=True)
        assert markdown_anchors(prior) <= markdown_anchors(old.read_text())
        assert '- **Status:** completed' in old.read_text()
        assert '- **Status:** historical' in archive.read_text()
        plans.append({'name': name, 'original_anchor_count': len(markdown_anchors(prior)),
                      'compatibility_sha256': digest(old), 'archive_sha256': digest(archive)})
    bridge_path = ROOT / 'verification/source41-final-documentation-bridge/manifest.json'
    bridge = json.loads(bridge_path.read_text())
    assert bridge['passed'] and bridge['complete_context_file_directory_set_and_bytes_equal']
    assert bridge['declared_verify_counts'] == {'fail': 0, 'pass': 3, 'skipped': 2}
    assert bridge['native_test_summary'] == {'failed': 0, 'passed': 18, 'skipped': 0, 'total': 18}
    for name, sha in bridge['files'].items():
        assert digest(bridge_path.parent / name) == sha, name
    completion_path = ROOT / 'verification/final-roadmap-completion/manifest.json'
    completion = json.loads(completion_path.read_text())
    assert completion['queue_counts'] == {'parents': 47, 'subtasks': 271, 'unchecked': 0}
    for name, sha in completion['evidence'].items():
        assert digest(ROOT / name) == sha, name
    status_counts = {}
    for source in files:
        if source.name == 'PROJECT.md':
            continue
        status = re.search(r'^- \*\*Status:\*\* (\w+)', '\n'.join(_visible_markdown_lines(source.read_text())), re.M)
        if status:
            status_counts[status[1]] = status_counts.get(status[1], 0) + 1
            assert status[1] in ('completed', 'historical'), (str(source), status[1])
    assert 'Their behavioral requirements and documented operating limits' in text
    assert 'Earlier qualification\nstatus sentences in PROJECT.md' in text
    result = {
        'schema': 'adhd/source41-final-queue-static-review@1', 'passed': True,
        'scope': 'Static final queue/link/anchor/archival accounting; no runtime or lifecycle invocation. Final independent requirement review and final declared verify are separately root-owned.',
        'closed_parents': 47, 'closed_leaf_lines': 271, 'unchecked_parents': 0, 'unchecked_leaf_lines': 0,
        'visible_local_links_verified': link_count, 'link_gaps': [], 'roadmap_lifecycle_header_counts': status_counts,
        'six_stable_closure_anchors': anchors, 'older_PROJECT_aliases': list(aliases), 'three_archive_compatibility_sets': plans,
        'PROJECT_prior_status_disposition': 'Updated queue explicitly treats older pending status prose as prior checkpoints. No new feature or runtime gap; behavioral requirements/operating limits remain applicable.',
        'adaptive_plan_disposition': 'Completed plan retained for useful PROJECT/overview/traceability inbound links; its six passed gates were bound in preceding archive-link review. No third bridge or historical cleanup task introduced.',
        'actual_final_bridge': {'path': str(bridge_path.relative_to(ROOT)), 'sha256': digest(bridge_path), 'passed': True,
                               'declared_verify': bridge['declared_verify_counts'], 'native_tests': bridge['native_test_summary'],
                               'all_retained_sibling_hashes_verified': len(bridge['files']), 'context_set_and_bytes_equal': True},
        'completion_manifest_snapshot': {'path': str(completion_path.relative_to(ROOT)), 'sha256': digest(completion_path),
                                         'passed_at_review': completion['passed'], 'status_at_review': completion['status']},
        'full_goal_completion_asserted_by_this_static_review': False,
        'input_sha256': {str(p.relative_to(ROOT)): digest(p) for p in files},
        'ordinary_docs_receipts_sources_resources_unmodified': True}
    print(json.dumps(result, indent=2) + '\n', end='')

if __name__ == '__main__':
    main()
