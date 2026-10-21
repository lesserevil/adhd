#!/usr/bin/env python3
"""Independently validate published schemas and actual HTTP messages."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
from urllib.request import Request
from urllib.error import HTTPError
import jsonschema
from openapi_spec_validator import validate as validate_openapi
from foundation_acceptance import Runtime, Client, ModelFixture

def max_bytes(validator,bound,instance,schema):
    if isinstance(instance,str) and len(instance.encode('utf-8'))>bound:
        yield jsonschema.ValidationError('UTF-8 byte bound exceeded')

def min_bytes(validator,bound,instance,schema):
    if isinstance(instance,str) and len(instance.encode('utf-8'))<bound:
        yield jsonschema.ValidationError('UTF-8 byte minimum not reached')

def integer_token(validator,bound,instance,schema):
    if bound and (not isinstance(instance,int) or isinstance(instance,bool)):
        yield jsonschema.ValidationError('Integer JSON token required')

def unique_by(validator,field,instance,schema):
    if not isinstance(instance,list):return
    selected=[item[field] for item in instance if isinstance(item,dict) and field in item]
    keys=[json.dumps(value,sort_keys=True,separators=(',',':')) for value in selected]
    if len(keys)!=len(set(keys)):
        yield jsonschema.ValidationError('Duplicate identity selected by '+field)


def canonical_bytes(validator,bound,instance,schema):
    if isinstance(instance,dict) and len(json.dumps(instance,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())>bound:
        yield jsonschema.ValidationError('Canonical JSON byte bound exceeded')

def snapshot_hash(validator,fields,instance,schema):
    if isinstance(instance,dict):
        for digest,source in fields.items():
            if digest in instance and (not isinstance(instance.get(source),str) or instance[digest]!=hashlib.sha256(instance[source].encode()).hexdigest()):
                yield jsonschema.ValidationError('Snapshot SHA256 differs')

def strict_json(text):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate JSON key')
            value[key]=item
        return value
    def nonfinite(value):raise ValueError('Nonfinite JSON number')
    def finite_float(text):
        import math
        value=float(text)
        if not math.isfinite(value):raise ValueError('Nonfinite JSON number')
        return value
    return json.loads(text,object_pairs_hook=pairs,parse_constant=nonfinite,parse_float=finite_float)


def json_equal(a,b):
    if isinstance(a,bool) or isinstance(b,bool):return type(a) is type(b) and a==b
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(json_equal(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(json_equal(x,y) for x,y in zip(a,b))
    return a==b


def json_of(validator,fields,instance,schema):
    if isinstance(instance,dict):
        for raw,parsed in fields.items():
            if raw in instance and isinstance(instance[raw],str):
                try:equal=json_equal(strict_json(instance[raw]),instance.get(parsed))
                except (ValueError,TypeError):equal=False
                if not equal:yield jsonschema.ValidationError('JSON body differs from parsed sibling')


def choice_distribution(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    probabilities=instance.get('probabilities');confidence=instance.get('confidence');chosen=instance.get('choice')
    if not isinstance(probabilities,dict) or not probabilities:return
    def finite_probability(n):
        import math
        return isinstance(n,(int,float)) and not isinstance(n,bool) and 0<=n<=1 and math.isfinite(n)
    if not all(finite_probability(n) for n in probabilities.values()) or not finite_probability(confidence):
        yield jsonschema.ValidationError('Invalid finite probability or confidence');return
    if not isinstance(chosen,str) or chosen not in probabilities:
        yield jsonschema.ValidationError('Choice is absent from the distribution');return
    if abs(sum(probabilities.values())-1)>0.00001 or probabilities[chosen]!=max(probabilities.values()) or abs(confidence-probabilities[chosen])>0.00001:
        yield jsonschema.ValidationError('Distribution sum, selected maximum or confidence differs')


def choice_exchange(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    request,response=instance.get('request'),instance.get('response')
    if not isinstance(request,dict) or not isinstance(response,dict):return
    questions,answers=request.get('questions'),response.get('answers')
    if not isinstance(questions,dict) or not isinstance(answers,dict):return
    if request.get('model')!=response.get('model') or questions.keys()!=answers.keys():
        yield jsonschema.ValidationError('Model or question IDs differ from request');return
    for key,question in questions.items():
        answer=answers[key]
        if not isinstance(question,dict) or not isinstance(answer,dict):continue
        criteria,probabilities=question.get('criteria'),answer.get('probabilities')
        if isinstance(criteria,dict) and isinstance(probabilities,dict) and criteria.keys()!=probabilities.keys():
            yield jsonschema.ValidationError('Probabilities differ from offered criteria')


def history_choices(validator,rule,instance,schema):
    if not isinstance(instance,dict):return
    try:
        records=instance['state']['records'];criteria=instance['questions']['answer']['criteria'];prefix=rule['prefix']
        if not isinstance(records,list) or not isinstance(criteria,dict):return
        expected={'joint','unknown','conflict'}|{'quote_'+str(i) for i in range(len(records))}
        if criteria.keys()!=expected:yield jsonschema.ValidationError('Quote criteria do not match all records');return
        for i,record in enumerate(records):
            value=criteria['quote_'+str(i)];publication=record['publication']
            if not isinstance(value,str) or not value.startswith(prefix):yield jsonschema.ValidationError('Quote criterion prefix differs');continue
            original=value[len(prefix):]
            if publication['text']:
                if original!=publication['text']:yield jsonschema.ValidationError('Quote does not preserve the original text')
            else:
                try:equal=json_equal(strict_json(original),publication['data'])
                except (ValueError,TypeError):equal=False
                if not equal:yield jsonschema.ValidationError('Quote does not preserve original JSON data')
    except (KeyError,TypeError):return


def ordered_times(validator,fields,instance,schema):
    if not isinstance(instance,dict) or not all(k in instance for k in fields):return
    from datetime import datetime
    try:
        values=[datetime.fromisoformat(instance[k].replace('Z','+00:00')) for k in fields]
        if any(x.tzinfo is None for x in values) or values[0]>values[1]:raise ValueError('Invalid occurrence order')
    except (ValueError,TypeError,AttributeError):yield jsonschema.ValidationError('Occurrence bounds must be ordered zoned timestamps')


def utf8_span(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    start,end,text=instance.get('start'),instance.get('end'),instance.get('text')
    if not (type(start) is int and type(end) is int and isinstance(text,str)):
        yield jsonschema.ValidationError('UTF-8 span requires integer offsets and text');return
    if start<0 or end<start or end-start!=len(text.encode('utf-8')):
        yield jsonschema.ValidationError('UTF-8 span differs from fragment bytes')


def noul_exchange(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    import math
    request,response=instance.get('request'),instance.get('response')
    if not isinstance(request,dict) or not isinstance(response,dict):return
    questions,answers=request.get('questions'),response.get('answers')
    if not isinstance(questions,dict) or not isinstance(answers,dict):return
    if request.get('model')!=response.get('model') or set(questions)!= {'useful'} or set(answers)!= {'useful'}:
        yield jsonschema.ValidationError('Noul model or exact usefulness question differs');return
    question,answer=questions['useful'],answers['useful']
    if not isinstance(question,dict) or not isinstance(answer,dict):return
    probability=answer.get('noul')
    if (question.get('type')!='noul' or answer.get('type')!='noul' or set(answer)!= {'type','noul'}
            or not isinstance(probability,(int,float)) or isinstance(probability,bool)
            or not math.isfinite(probability) or not 0<=probability<=1):
        yield jsonschema.ValidationError('A finite typed usefulness probability is required')


def fragment_projection(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    try:
        candidate=instance['request']['state']['candidate']
        fragments=[{key:fragment[key] for key in ('origin_publication_id','field','text')}
                   for fragment in instance['fragments']]
        equal=(json_equal(candidate['fragments'],fragments)
               and candidate['publication_id']==instance['publication_id']
               and json_equal(candidate['truncated'],instance['fragment_truncated']))
    except (KeyError,TypeError):equal=False
    if not equal:yield jsonschema.ValidationError('Model fragment projection differs from recorded provenance')


def byte_length_of(validator,fields,instance,schema):
    if not isinstance(instance,dict):return
    for count,raw in fields.items():
        if isinstance(instance.get(raw),str) and instance.get(count)!=len(instance[raw].encode('utf-8')):
            yield jsonschema.ValidationError('Declared byte length differs from exact UTF-8 request')


def archive_sample(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    try:
        rate=instance['rate_ppm'];denominator=1<<256;numerator=rate*denominator//1000000
        if type(rate) is not int or not 0<=rate<=1000000:return
        eligible=instance['eligible'];draw=instance['draw_hex'];selected=instance['selected']
        if instance['probability_denominator']!=str(denominator) or instance['probability_numerator']!=str(numerator):
            yield jsonschema.ValidationError('Audit probability differs from the exact uniform256 threshold')
        if eligible:
            if not isinstance(draw,str) or len(draw)!=64 or any(c not in '0123456789abcdef' for c in draw):
                yield jsonschema.ValidationError('Eligible sample requires its exact 256-bit draw');return
            if selected!=(int(draw,16)<numerator) or instance['population']!='successful_search':
                yield jsonschema.ValidationError('Audit eligibility, population or threshold selection differs')
        elif draw is not None or selected is not False or instance['population']=='successful_search':
            yield jsonschema.ValidationError('Ineligible plan must conceal the draw and remain unselected')
    except (KeyError,TypeError,ValueError):return


def archive_usage(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    try:
        stages=['planner','retrieval','assessment','scan','audit'];total=instance['total']
        for key,value in total.items():
            if value!=sum(instance[stage][key] for stage in stages):
                yield jsonschema.ValidationError('Archive total differs from independent stage counters')
        for stage in stages:
            for key in ['records','calls','bytes','time_ms','uncertain_calls']:
                if instance[stage]['cumulative_'+key]<instance[stage][key]:
                    yield jsonschema.ValidationError('Cumulative cost is smaller than its run cost')
    except (KeyError,TypeError):return


def archive_originals(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    try:
        records=instance['request']['state']['records']
        if instance['record_ids']!=[r['publication']['id'] for r in records] or instance['context_identities']!=[r['context_identity'] for r in records]:
            yield jsonschema.ValidationError('Assessment provenance differs from the supplied original records')
    except (KeyError,TypeError):return


def archive_bindings(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    try:
        if instance['plan_id']!=instance['sample']['plan_id'] or instance['policy']['audit_rate_ppm']!=instance['sample']['rate_ppm']:
            yield jsonschema.ValidationError('Archive plan or frozen sample policy differs')
        for stage,field in [('retrieval','search'),('scan','scan'),('audit','audit')]:
            child=instance[field];ref=instance['children'][stage]
            if child is None:
                if ref is not None:yield jsonschema.ValidationError('Child reference has no cached child view')
                continue
            if ref is None or child['id']!=ref['query_id'] or child['run']!=ref['run']:
                yield jsonschema.ValidationError('Child reference differs from its recorded run');continue
            if any(child[k]!=instance[k] for k in ['owner_id','question','scope','snapshot']):
                yield jsonschema.ValidationError('Child does not belong to the same frozen owner/question/corpus')
        for evaluation in instance['evaluations']:
            model=instance['policy']['planner' if evaluation['stage']=='planner' else 'history']['model']
            if evaluation['request']['model']!=model or evaluation['request']['state']['question']!=instance['question']:
                yield jsonschema.ValidationError('Evaluation question or model differs from its frozen archive policy')
        if instance['sample']['eligible'] and (instance['assessment'] is None or instance['assessment']['answer']['assessment']!='direct'):
            yield jsonschema.ValidationError('Only direct original support is eligible for successful-search auditing')
    except (KeyError,TypeError):return


def replay_usage(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    try:
        usage=instance['usage']
        for key,value in usage['total'].items():
            if value!=sum(usage[b][key] for b in ['baseline','candidate']):
                yield jsonschema.ValidationError('Replay total differs from independent branch counters')
        for b in ['baseline','candidate']:
            if usage[b]!=instance[b]['usage']:
                yield jsonschema.ValidationError('Replay branch usage differs from parent totals')
            for k in ['records','calls','bytes','time_ms','uncertain_calls']:
                if usage[b]['cumulative_'+k]<usage[b][k]:
                    yield jsonschema.ValidationError('Replay cumulative cost is smaller than its run cost')
    except (KeyError,TypeError):return


def replay_bindings(validator,enabled,instance,schema):
    if not enabled or not isinstance(instance,dict):return
    try:
        import hashlib
        def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        if instance['policy']['identity']!=digest({k:v for k,v in instance['policy'].items() if k!='identity'}):
            yield jsonschema.ValidationError('Replay policy identity differs from frozen interpretation descriptors')
        for b in ['baseline','candidate']:
            branch=instance[b];policy=instance['policy'][b+'_evaluator'];ref=instance['children'][b];scan=branch['scan']
            expected_recipe=digest({'adapter_version':'adhd-native-retrieval-v1','runtime':instance['policy']['runtime'],'recipe':branch['recipe']})
            if branch['recipe_identity']!=expected_recipe:
                yield jsonschema.ValidationError('Replay primitive recipe differs from its runtime-bound digest')
            if branch['recipe_identity']!=policy['policy']['recipe_identity']:
                yield jsonschema.ValidationError('Replay recipe differs from its frozen evaluator')
            if branch['coverage']['returned_ids']!=[c['publication_id'] for c in branch['candidates']]:
                yield jsonschema.ValidationError('Returned coverage differs from actual candidate roots')
            assessment=branch['assessment']
            if assessment is not None:
                if assessment['record_ids']!=branch['coverage']['assessed_ids'] or assessment['evaluator']!=instance['policy']['history_evaluator']:
                    yield jsonschema.ValidationError('Replay original assessment differs from its coverage or policy')
            elif branch['coverage']['assessed_ids']:
                yield jsonschema.ValidationError('Replay claims assessed original inputs without assessment')
            if scan is None:
                if ref is not None:yield jsonschema.ValidationError('Replay child reference lacks its cached evidence')
            else:
                if ref is None or scan['id']!=ref['query_id'] or scan['run']!=ref['run']:
                    yield jsonschema.ValidationError('Replay scan differs from its expected child run')
                if any(scan[k]!=instance[k] for k in ['owner_id','question','scope','snapshot']) or scan['complete'] is not True:
                    yield jsonschema.ValidationError('Replay child differs from its frozen owner/question/full corpus')
            if branch['metrics']['fallback']!=(ref is not None):
                yield jsonschema.ValidationError('Replay fallback metric differs from real child execution')
            if branch['metrics']['eligible'] and instance['label'] is not None:
                gold=instance['label']['support_ids'];retrieved=sum(v in branch['coverage']['assessed_ids'] for v in gold)
                if (branch['metrics']['expected_gold'],branch['metrics']['retrieved_gold'],branch['metrics']['retrieval_recall_ppm'])!=(len(gold),retrieved,1000000 if not gold else retrieved*1000000//len(gold)):
                    yield jsonschema.ValidationError('Replay confirmed recall differs from actually supplied candidate originals')
            if instance['corpus']=='current' and branch['metrics']['eligible']:
                yield jsonschema.ValidationError('Changed corpus cannot qualify retrieval improvement')
            if not instance['evidence_available'] and branch['metrics']['eligible']:
                yield jsonschema.ValidationError('Retired evidence cannot qualify retrieval improvement')
        label=instance['label']
        if label is not None and label['identity']!=digest({k:v for k,v in label.items() if k!='identity'}):
            yield jsonschema.ValidationError('Replay confirmed label identity differs from its assertion/actor/evidence')
        if (0 if label is None else label['revision'])!=instance['label_revision']:
            yield jsonschema.ValidationError('Replay label revision differs from frozen assertion')
        if instance['corpus']=='frozen' and instance['snapshot']!=instance['original_snapshot']:
            yield jsonschema.ValidationError('Frozen replay changed the original watermark')
        for ev in instance['evaluations']:
            model=instance['policy'][ev['branch']+'_evaluator']['model'] if ev['stage']=='retrieval' else instance['policy']['history_evaluator']['model']
            if ev['request']['model']!=model or ev['request']['state']['question']!=instance['question']:
                yield jsonschema.ValidationError('Replay evaluation differs from frozen branch question/model')
        comparison=instance['comparison'];a=instance['baseline']['metrics'];b=instance['candidate']['metrics']
        if comparison['eligible']!=(a['eligible'] and b['eligible']):
            yield jsonschema.ValidationError('Replay comparison eligibility differs from branch evidence')
        if comparison['eligible']:
            if comparison['retrieval_gain_ppm']!=b['retrieval_recall_ppm']-a['retrieval_recall_ppm']:
                yield jsonschema.ValidationError('Replay gain differs from confirmed retrieval recall')
            for k in ['calls','bytes','time_ms']:
                if comparison[k+'_delta']!=instance['candidate']['comparison_usage'][k]-instance['baseline']['comparison_usage'][k]:
                    yield jsonschema.ValidationError('Replay cost delta differs from actual paired work')
    except (KeyError,TypeError):return


from optimization_validation import optimization_bindings,optimization_usage

ByteValidator=jsonschema.validators.extend(jsonschema.Draft202012Validator,
    {'x-maxBytes':max_bytes,'x-minBytes':min_bytes,'x-integerToken':integer_token,'x-maxCanonicalBytes':canonical_bytes,'x-sha256Of':snapshot_hash,
     'x-uniqueBy':unique_by,'x-jsonOf':json_of,'x-choiceDistribution':choice_distribution,'x-choiceExchange':choice_exchange,'x-historyChoices':history_choices,'x-orderedTimes':ordered_times,
     'x-utf8Span':utf8_span,'x-noulExchange':noul_exchange,'x-fragmentProjection':fragment_projection,'x-byteLengthOf':byte_length_of,
     'x-archiveSample':archive_sample,'x-archiveUsage':archive_usage,'x-archiveOriginals':archive_originals,'x-archiveBindings':archive_bindings,'x-replayBindings':replay_bindings,'x-replayUsage':replay_usage,'x-optimizationBindings':optimization_bindings,'x-optimizationUsage':optimization_usage})



def check_critical_annotations(schema):
    """Reject an unimplemented critical extension without walking literal data."""
    supported={key for key in ByteValidator.VALIDATORS if key.startswith('x-')}
    mappings={'$defs','properties','patternProperties','dependentSchemas'}
    singles={'additionalProperties','unevaluatedProperties','propertyNames','items','contains','not','if','then','else','unevaluatedItems','contentSchema'}
    arrays={'allOf','anyOf','oneOf','prefixItems'}
    def visit(value):
        if not isinstance(value,dict):return
        missing={key for key in value if key.startswith('x-')}-supported
        if missing:raise ValueError('Unsupported critical schema annotations: '+','.join(sorted(missing)))
        for key in mappings:
            if isinstance(value.get(key),dict):
                for child in value[key].values():visit(child)
        for key in singles:visit(value.get(key))
        for key in arrays:
            if isinstance(value.get(key),list):
                for child in value[key]:visit(child)
    visit(schema)


def normalized_schema_required(schema):
    """Only JSON Schema required-name ordering is insignificant.

    Traverse schema-bearing keywords, keeping const/enum/default and unknown
    annotations opaque so arbitrary source payloads cannot be normalized away.
    """
    import copy
    value=copy.deepcopy(schema)
    if not isinstance(value,dict):return value
    if isinstance(value.get('required'),list):value['required']=sorted(value['required'])
    for key in ('$defs','definitions','properties','patternProperties','dependentSchemas'):
        if isinstance(value.get(key),dict):value[key]={k:normalized_schema_required(v) for k,v in value[key].items()}
    for key in ('additionalProperties','unevaluatedProperties','additionalItems','unevaluatedItems','items','contains','propertyNames','not','if','then','else'):
        if isinstance(value.get(key),(dict,bool)):value[key]=normalized_schema_required(value[key])
    for key in ('allOf','anyOf','oneOf','prefixItems'):
        if isinstance(value.get(key),list):value[key]=[normalized_schema_required(v) for v in value[key]]
    return value


def normalized_openapi_required(value):
    if isinstance(value,list):return [normalized_openapi_required(v) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key.startswith('x-') or key in ('example','examples','const','enum','default'):result[key]=item
        elif key=='schemas' and isinstance(item,dict):result[key]={k:normalized_schema_required(v) for k,v in item.items()}
        elif key=='schema':result[key]=normalized_schema_required(item)
        else:result[key]=normalized_openapi_required(item)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--command',required=True)
    p.add_argument('--image',help='Run HTTP and CLI checks against this immutable container image')
    p.add_argument('--eventing-rest-url', default='http://127.0.0.1:18082', help='Actual Kafka REST service for profile 2')
    p.add_argument('--port-lock', type=Path, default=Path('_build/roadmap/foundation-port.lock'))
    p.add_argument('--profile-version', choices=['1.7.0','2.0.0'], default='2.0.0', help='Exact application profile expected; legacy 1.7 requires explicit selection')
    p.add_argument('--published-schema', type=Path, default=Path('docs/protocol/schema.json'))
    p.add_argument('--published-openapi', type=Path, default=Path('docs/protocol/openapi.json'))
    p.add_argument('--report',default='verification/protocol-acceptance.json')
    args=p.parse_args();command=json.loads(args.command)
    args.port_lock.parent.mkdir(parents=True,exist_ok=True)
    port_lock=args.port_lock.open('a')
    fcntl.flock(port_lock,fcntl.LOCK_EX)
    parent=Path('_build/roadmap/tests').resolve();parent.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='protocol-',dir=parent))
    runtime=Runtime(root/'hub',command,args.image);model=ModelFixture();cases=[]
    cli=['docker','run','--rm','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',args.image] if args.image else command
    def record(name):cases.append({'case':name,'passed':True});print('PASS',name,flush=True)
    try:
        runtime.start();client=Client(runtime)
        status,schema,_=client.get('/protocol/schema');assert status==200
        jsonschema.Draft202012Validator.check_schema(schema)
        exported=json.loads(subprocess.check_output(cli+[json.dumps(['protocol-schema'])],text=True))
        assert exported==schema
        assert normalized_schema_required(schema)==normalized_schema_required(json.loads(args.published_schema.read_text()))
        # These literals intentionally resemble schemas. Preserve them exactly.
        probe={'type':'object','required':['b','a'],'properties':{'value':{'const':{'required':['b','a']}}},'x-literal':{'required':['b','a']}}
        import copy
        reordered=copy.deepcopy(probe);reordered['required'].reverse()
        assert normalized_schema_required(probe)==normalized_schema_required(reordered)
        for changed in ('membership','constraint','literal','annotation'):
            bad=copy.deepcopy(probe)
            if changed=='membership':bad['required'].pop()
            elif changed=='constraint':bad['type']='array'
            elif changed=='literal':bad['properties']['value']['const']['required'].reverse()
            else:bad['x-literal']['required'].reverse()
            assert normalized_schema_required(probe)!=normalized_schema_required(bad),changed
        api_probe={'components':{'schemas':{'Probe':probe}},'x-literal':{'schema':copy.deepcopy(probe)}}
        api_reordered=copy.deepcopy(api_probe);api_reordered['components']['schemas']['Probe']['required'].reverse()
        assert normalized_openapi_required(api_probe)==normalized_openapi_required(api_reordered)
        api_literal=copy.deepcopy(api_probe);api_literal['x-literal']['schema']['required'].reverse()
        assert normalized_openapi_required(api_probe)!=normalized_openapi_required(api_literal)
        check_critical_annotations(schema)
        try:check_critical_annotations({'$defs':{'Unsupported':{'type':'object','x-unimplementedCritical':True}}})
        except ValueError:pass
        else:raise AssertionError('Unknown critical annotation was silently ignored')
        # An arbitrary source-data literal is not itself a schema annotation.
        check_critical_annotations({'const':{'x-literal-source-data':True}})
        record('critical-annotations-all-have-independent-handlers-and-unknown-extensions-fail-closed')
        def valid(name,value,expected=True):
            profile={'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/'+name}
            actual=ByteValidator(profile,format_checker=jsonschema.FormatChecker()).is_valid(value)
            assert actual==expected,(name,expected,value)
        valid('AgentCard',client.get('/.well-known/agent-card.json')[1])
        valid('Descriptor',client.get('/protocol')[1])
        for op in ('list_retrieval_attempts','get_retrieval_attempt','replay_retrieval','get_retrieval_replay','continue_retrieval_replay','cancel_retrieval_replay','query_archive','get_archive_query','continue_archive_query','cancel_archive_query','retrieve','get_retrieval','continue_retrieval','cancel_retrieval','retrieval_index','publish_record','get_record','query_history','get_history_query','continue_history_query','cancel_history_query','federation_directory','identity_matches','source_query','get_source_query','cancel_source_query','whoami','subscribe','list_subscriptions','unsubscribe','publish','send','poll','ack','get','search','federated_query','get_federated_query','cancel_federated_query'):
            assert 'agent_'+op in schema['$defs'] and 'result_'+op in schema['$defs']
        vectors=[
            ('agent_whoami',{'op':'whoami'},True),
            ('agent_whoami',{'op':'whoami','unexpected':1},False),
            ('agent_subscribe',{'op':'subscribe','description':'API changes'},True),
            ('agent_subscribe',{'op':'subscribe','description':''},False),
            ('agent_subscribe',{'op':'subscribe','description':'x'*4097},False),
            ('agent_subscribe',{'op':'subscribe','description':'λ'*2049},False),
            ('agent_subscribe',{'op':'subscribe','description':'   '},False),
            ('agent_poll',{'op':'poll','limit':1},True),
            ('agent_poll',{'op':'poll','limit':True},False),
            ('agent_poll',{'op':'poll','limit':101},False),
            ('agent_ack',{'op':'ack','delivery_ids':['one']},True),
            ('agent_ack',{'op':'ack','delivery_ids':['one','one']},False),
            ('agent_publish',{'op':'publish','data':[1,None,{'nested':True}]},True),
            ('agent_publish',{'op':'publish'},False),
            ('agent_publish',{'op':'publish','text':'hello','source':{'kind':'github','id':'r','unknown':'x'}},False),
            ('admin_config_get',{'op':'config_get'},True),
            ('admin_config_get',{'op':'config_get','patch':{}},False),
            ('admin_config_update',{'op':'config_update','patch':{'auth':{'session_ttl_ms':90000}},'expected_revision':3,'confirm':True,'message_id':'partial-nested'},True),
            ('login',{'username':'admin','password':'password'},True),
            ('login',{'username':'admin','password':'password','role':'Admin'},False),
            ('peer_v1_command',{'op':'status','protocol_version':1,'origin_project_id':'other','query_id':'q'},True),
            ('peer_v1_command',{'op':'status','protocol_version':2,'origin_project_id':'other','query_id':'q'},False),
        ]
        for name,value,expected in vectors:valid(name,value,expected)
        fixtures=json.loads(Path('docs/protocol/examples.json').read_text())
        assert json.loads(args.published_openapi.read_text())['info']['version']==args.profile_version
        assert fixtures['profile_version'] in ({'1.7.0','2.0.0'} if args.profile_version=='2.0.0' else {'1.7.0'})
        for example in fixtures['cases']:valid(example['definition'],example['body'],example['valid'])
        record('independent-draft202012-schema-and-positive-negative-vectors')
        password=(runtime.root/'initial-admin-password.txt').read_text().split('Password: ')[1].strip()
        client.login('admin',password)
        for operation in ('config_get','overview','users','agents'):
            valid('admin_result_'+operation,client.api({'op':operation}))
        token=secrets.token_urlsafe(32)
        grants={'project_ids':[runtime.config['project_id']]} if args.profile_version=='2.0.0' else {}
        if args.profile_version=='2.0.0':
            client.api({'op':'config_update','patch':{'eventing':{'enabled':True,'rest_url':args.eventing_rest_url}}},mutation=True)
        client.api({'op':'create_agent','agent_id':'protocol-agent','token':token,**grants},mutation=True)
        for body in ({'op':'whoami'},{'op':'publish','data':[1,None,{'arbitrary':True}]},{'op':'poll'},{'op':'search','query':'unseen-needle'}):
            valid('agent_'+body['op'],body)
            result=client.rpc(body,token)
            valid('result_'+body['op'],result)
        record('actual-a2a-responses-conform-to-independent-validator')
        client.api({'op':'config_update','patch':{'matcher':{'url':model.url,'model':'Nemotron-Deciffusion-8B-v2.1','timeout_ms':3000,'retry_ms':100}}},mutation=True)
        client.rpc({'op':'subscribe','description':'API response changes'},token)
        client.rpc({'op':'publish','text':'An API response now includes a status field.'},token)
        import time
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and not model.requests:time.sleep(.05)
        assert model.requests
        for request in model.requests:valid('SystemOneRequest',request)
        valid('SystemOneResponse',{'model':runtime.config['matcher']['model'],'answers':{'relevance':{'type':'noul','noul':.99}}})
        record('actual-short-response-model-requests-and-typed-answer-contract')

        from history_support import ChoiceFixture
        import copy
        choices=ChoiceFixture()
        try:
            client.api({'op':'config_update','patch':{'history':{'url':choices.url,'request_bytes':16384}}},mutation=True)
            q=client.rpc({'op':'query_history','question':'Which original evidence was published?'},token)['query']
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                q=client.rpc({'op':'get_history_query','query_id':q['id']},token)['query']
                if q['status']!='pending':break
                time.sleep(.05)
            assert q['status']=='completed',q['error']
            valid('HistoryQuery',q)
            evaluation=q['evaluations'][0]
            exchange={'request':evaluation['request'],'response':{'model':evaluation['request']['model'],'answers':evaluation['answers']}}
            valid('HistoryModelExchange',exchange)
            for path,value in [(['response','model'],'wrong-model'),(['response','answers','assessment','confidence'],.3),(['response','answers','answer','probabilities','invented'],0)]:
                bad=copy.deepcopy(exchange);target=bad
                for key in path[:-1]:target=target[key]
                target[path[-1]]=value;valid('HistoryModelExchange',bad,False)
            for raw in ['{"duplicate":1,"duplicate":1}', '{"numeric":1e999}', '{"numeric":NaN}', evaluation['request_json'].replace('"model":','"extra":true,"model":',1)]:
                bad=copy.deepcopy(evaluation);bad['request_json']=raw;bad['request_sha256']=hashlib.sha256(raw.encode()).hexdigest();valid('HistoryEvaluation',bad,False)
            bad=copy.deepcopy(evaluation);bad['request_sha256']='0'*64;valid('HistoryEvaluation',bad,False)
            bad=copy.deepcopy(exchange);bad['request']['questions']['answer']['criteria']['quote_0']='Changed original';valid('HistoryModelExchange',bad,False)
            record('actual-history-choice-exchanges-originals-exact-bytes-and-independent-semantic-negatives')
        finally:choices.close()

        from retrieval_support import NoulFixture
        useful=NoulFixture()
        try:
            client.api({'op':'config_update','patch':{'retrieval':{'url':useful.url}}},mutation=True)
            client.rpc({'op':'publish_record','text':'A protocol retrieval original.','information_type':'protocol-retrieval'},token)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                index=client.rpc({'op':'retrieval_index'},token)['index']
                if index['status']=='ready':break
                time.sleep(.05)
            valid('RetrievalIndexRead',index)
            assert ByteValidator(schema).is_valid({'op':'retrieval_index'})
            q=client.rpc({'op':'retrieve','question':'What original is available?','scope':{'information_type':'protocol-retrieval'}},token)['query']
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                q=client.rpc({'op':'get_retrieval','query_id':q['id']},token)['query']
                if q['status']!='pending':break
                time.sleep(.05)
            assert q['status']=='completed',q['error'];valid('RetrievalQuery',q)
            evaluation=q['evaluations'][0];valid('RetrievalEvaluation',evaluation)
            # Keep raw-byte/digest checks satisfied to isolate the semantic projection.
            bad=copy.deepcopy(evaluation);bad['request']['state']['candidate']['fragments'][0]['text']='Substituted evidence'
            bad['request_json']=json.dumps(bad['request'],ensure_ascii=False,separators=(',',':'));bad['request_sha256']=hashlib.sha256(bad['request_json'].encode()).hexdigest()
            valid('RetrievalEvaluation',bad,False)
            exchange={'request':evaluation['request'],'response':evaluation['response']}
            valid('RetrievalRecordedModelExchange',exchange)
            bad=copy.deepcopy(exchange);bad['response']['model']='different';valid('RetrievalRecordedModelExchange',bad,False)
            bad=copy.deepcopy(evaluation['fragments'][0]);bad['end']+=1;valid('RetrievalFragment',bad,False)
            record('actual-retrieval-exact-model-pairing-utf8-and-independent-fragment-projection')
        finally:useful.close()

        client.api({'op':'config_update','patch':{'federation':{'description':'Protocol test project','peers':[
            {'project_id':'other','url':'http://127.0.0.1:1','token':'o'*32,'inbound_token':'i'*32}]}}},mutation=True)
        for path,raw,expected in [
            ('/admin/api',b'{"op":"overview","op":"config_get"}',400),
            ('/admin/api',b'{"op":"overview","unknown":true}',400),
            ('/admin/api',b'{"op":"jobs","limit":true}',400),
            ('/federation/v3' if args.profile_version=='2.0.0' else '/federation/v2',b'{"protocol_version":3,"op":"status"}',426),
            *([('/federation/v2',b'{"protocol_version":2,"op":"status"}',401)] if args.profile_version=='2.0.0' else []),
            ('/federation/v1',b'{"protocol_version":true,"op":"status","origin_project_id":"other","query_id":"q"}',400),
            ('/federation/v1',b'{"protocol_version":1,"protocol_version":1,"op":"status","origin_project_id":"other","query_id":"q"}',400),
        ]:
            hs={'Content-Type':'application/json','Origin':runtime.base,'X-CSRF-Token':client.csrf}
            if path.startswith('/federation'):hs['Authorization']='Bearer '+'i'*32
            req=Request(runtime.base+path,data=raw,headers=hs)
            try:r=client.opener.open(req,timeout=10)
            except HTTPError as e:r=e
            with r:
                value=json.load(r)
                assert r.status==expected,(path,r.status,value)
                if expected==426:
                    assert value['error']['code']=='UNSUPPORTED_VERSION' and value['supported']==([1,2] if args.profile_version=='2.0.0' else [1])
                    valid('UnsupportedVersion',value)
                else:valid('PeerV2Error' if path=='/federation/v2' and args.profile_version=='2.0.0' else 'PeerV1Error' if path=='/federation/v1' else 'Error',value)
        record('actual-http-rejects-duplicates-unknown-fields-bool-integers-and-versions')
        status,api,_=client.get('/protocol/openapi');assert status==200
        validate_openapi(api)
        for path in api['paths'].values():
            for operation in path.values():
                for requirement in operation.get('security',[]):
                    assert set(requirement)<=set(api['components']['securitySchemes'])
        assert normalized_openapi_required(api)==normalized_openapi_required(json.loads(args.published_openapi.read_text()))
        assert api==json.loads(subprocess.check_output(cli+[json.dumps(['protocol-openapi'])],text=True))
        assert api['openapi']=='3.1.0' and api['info']['version']==args.profile_version
        for path in ('/a2a','/admin/login','/admin/session','/admin/api','/admin/logout','/admin/oidc/start','/admin/oidc/callback','/federation','/federation/v1'):
            assert path in api['paths'],path
        if args.profile_version=='2.0.0':
            assert '/federation/v2' in api['paths']
            for op in ('list_projects','update_subscription'):
                assert 'agent_'+op in schema['$defs'] and 'result_'+op in schema['$defs']
            for op in ('list_projects','resource_status','eventing_status','repair_eventing','replay_events','eventing_replay','eventing_audit'):
                assert 'admin_'+op in schema['$defs'] and 'admin_result_'+op in schema['$defs']
        record('http-cli-identical-openapi-and-complete-interface-inventory')
        report={'schema':'adhd/protocol-conformance@1','passed':True,'protocol_version':int(args.profile_version.split('.')[0]),'schema_id':schema['$id'],'api_profile_version':api['info']['version'],'foundation_fixture_profile':fixtures['profile_version'],'schema_sha256':hashlib.sha256(json.dumps(schema,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),'cases':cases,'artifact_sha256':hashlib.sha256(Path(command[-1]).read_bytes()).hexdigest(),'input_sha256':{
            Path(x).name:hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in command if Path(x).is_file()}}
        if args.image:report['image']=args.image
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    finally:runtime.stop();model.close();port_lock.close()

if __name__=='__main__':main()
