"""Qualification-only bounded relay ledger; stores digests, never request bodies.

The original relay remains unchanged unless its explicit qualification mode is
selected. Persistence precedes the one upstream attempt, including on failure.
"""
import hashlib
import json
import os
from pathlib import Path
import threading


class RelayAudit:
    def __init__(self, path, maximum, forbidden, allowed_callers):
        assert 1 <= maximum <= 12
        assert forbidden and all(isinstance(x, str) and x for x in forbidden)
        assert allowed_callers and len(set(allowed_callers)) == len(allowed_callers)
        self.path=Path(path);self.maximum=maximum;self.forbidden=tuple(forbidden)
        self.allowed_callers=frozenset(allowed_callers);self.rows=[];self.lock=threading.Lock()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('x') as output:
            output.write('[]\n');output.flush();os.fsync(output.fileno())
        self.path.chmod(0o600)

    def _persist(self):
        temporary=self.path.with_name(self.path.name+'.pending')
        with temporary.open('x') as output:
            output.write(json.dumps(self.rows,indent=2)+'\n');output.flush();os.fsync(output.fileno())
        temporary.chmod(0o600);os.replace(temporary,self.path)
        descriptor=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)

    def deny(self, reason):
        assert isinstance(reason,str) and reason and len(reason)<=128
        with self.lock:
            path=self.path.with_name(self.path.name+'.denied')
            with path.open('a') as output:
                output.write(reason+'\n');output.flush();os.fsync(output.fileno())
            path.chmod(0o600)

    def begin(self, body, caller):
        """Return a ticket only after its durable authorization-to-forward row."""
        with self.lock:
            assert caller in self.allowed_callers, 'Unreviewed relay caller'
            value=json.loads(body);assert isinstance(value,dict)
            # Scan the complete decoded request, including escaped strings. A
            # foreign/private canary is never sent to the existing provider.
            serialized=json.dumps(value,ensure_ascii=False)
            assert not any(x in serialized for x in self.forbidden), 'Privacy canary in model request'
            assert len(self.rows)<self.maximum, 'Upstream POST budget exhausted'
            state=value.get('state',{});assert isinstance(state,dict)
            publication=state.get('publication',{})
            row={'attempt':len(self.rows)+1,'phase':'forwarding','caller':caller,
                 'request_sha256':hashlib.sha256(body).hexdigest(),
                 'state_sha256':hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest(),
                 'publication_id':publication.get('id') if isinstance(publication,dict) else None,
                 'question_sha256':hashlib.sha256(json.dumps(state.get('question'),sort_keys=True).encode()).hexdigest(),
                 'question_keys':sorted(value.get('questions',{})),
                 'request_privacy_checked':True}
            self.rows.append(row);self._persist();return row['attempt']

    def finish(self, ticket, *, status, elapsed_ms, typed_response=None, error_type=None):
        with self.lock:
            row=self.rows[ticket-1];assert row['attempt']==ticket and row['phase']=='forwarding'
            row.update(phase='responded' if error_type is None else 'failed',status=status,elapsed_ms=elapsed_ms)
            if typed_response is not None:row['typed_response']=typed_response
            if error_type is not None:row['error_type']=error_type
            self._persist()


def verify_audit(rows, publications, maximum=12):
    """One filtered subscription and one history query are the closed corpus.

    No global duplicate-question policy: distinct jobs may legitimately ask the
    same question. Only this fixture's publication IDs bind its three filter
    jobs, and the original semantic query is represented by its request context.
    """
    assert 1 <= len(rows) <= maximum
    assert [r['attempt'] for r in rows]==list(range(1,len(rows)+1))
    assert all(r['phase']=='responded' and r['status']==200 and r['request_privacy_checked'] for r in rows)
    filtered=[r for r in rows if r['publication_id'] is not None]
    assert sorted(r['publication_id'] for r in filtered)==sorted(publications)
    semantic=[r for r in rows if r['publication_id'] is None]
    assert semantic and all(r['question_keys'] for r in semantic)
    # The relay never retries. Duplicate complete requests for this single
    # accepted history query are a failed no-retry qualification, not blocked
    # traffic or an assertion about unrelated legitimate query jobs.
    assert len({r['request_sha256'] for r in semantic})==len(semantic)
    return {'upstream_attempts':len(rows),'filter_attempts':len(filtered),
            'semantic_attempts':len(semantic),'maximum_upstream_posts':maximum,
            'no_retry_forwards':True,'all_requests_privacy_checked':True}
