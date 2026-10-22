"""Pure attempt/cap/privacy checks; never opens sockets or runs a provider."""
import json
from pathlib import Path
import tempfile
from kafka_model_audit import RelayAudit,verify_audit


def body(publication=None,question=None,case='answer'):
    state={'publication':{'id':publication}} if publication else {'question':question,'records':[]}
    return json.dumps({'state':state,'questions':{case:{'type':'choice'}}}).encode()


def main():
    count=0
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);audit=RelayAudit(root/'audit.json',4,['BLUE-secret','private-secret'],['172.20.0.2'])
        for identifier in ['positive','negative','resumed']:
            ticket=audit.begin(body(identifier),'172.20.0.2')
            saved=json.loads(audit.path.read_text());assert saved[-1]['phase']=='forwarding' and saved[-1]['attempt']==ticket
            audit.finish(ticket,status=200,elapsed_ms=1,typed_response={'answers':{}})
        ticket=audit.begin(body(question='fixed corpus question'),'172.20.0.2')
        audit.finish(ticket,status=200,elapsed_ms=1,typed_response={'answers':{}})
        rows=json.loads(audit.path.read_text());assert verify_audit(rows,['positive','negative','resumed'])['upstream_attempts']==4;count+=1
        try:audit.begin(body(question='fifth'),'172.20.0.2')
        except AssertionError:pass
        else:raise AssertionError('POST cap bypassed')
        assert json.loads(audit.path.read_text())==rows;count+=1
        for request,caller in [(body(question='BLUE-secret'),'172.20.0.2'),(body(question='private-secret'),'172.20.0.2'),(body(question='allowed'),'172.20.0.3')]:
            other=RelayAudit(root/('reject'+str(count)),12,['BLUE-secret','private-secret'],['172.20.0.2'])
            try:other.begin(request,caller)
            except AssertionError:pass
            else:raise AssertionError('Forbidden request admitted')
            assert json.loads(other.path.read_text())==[];count+=1
        failed=RelayAudit(root/'failed',12,['canary'],['172.20.0.2']);ticket=failed.begin(body(question='q'),'172.20.0.2')
        failed.finish(ticket,status=503,elapsed_ms=9,error_type='TimeoutError')
        assert json.loads(failed.path.read_text())[0]['phase']=='failed';count+=1
        try:verify_audit(json.loads(failed.path.read_text()),[])
        except AssertionError:pass
        else:raise AssertionError('Failed upstream qualified')
        count+=1
        # Identical questions from separate actual contexts are not blocked by
        # the relay. Only a duplicate complete request in the single-query
        # qualification corpus is a failed no-retry assertion afterwards.
        duplicate=RelayAudit(root/'duplicate',12,['canary'],['172.20.0.2'])
        for _ in range(2):
            t=duplicate.begin(body(question='same question'),'172.20.0.2');duplicate.finish(t,status=200,elapsed_ms=1)
        assert len(duplicate.rows)==2;count+=1
        try:verify_audit(rows+[dict(rows[-1],attempt=5)],['positive','negative','resumed'])
        except AssertionError:pass
        else:raise AssertionError('Corpus retry qualified')
        count+=1
    print(json.dumps({'passed':True,'checks':count,'runtime_or_provider_started':False}))


if __name__=='__main__':main()
