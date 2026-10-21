"""Independently authored profile 1.7 semantic bindings and actual-work arithmetic."""
import hashlib,json
import jsonschema


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def failure(message):return jsonschema.ValidationError(message)


def optimization_bindings(validator,enabled,v,schema):
    if not enabled or not isinstance(v,dict):return
    try:
        variants={item['recipe_identity']:item for item in v['variants']}
        if len(variants)!=len(v['variants']):yield failure('Optimizer repeats a candidate identity')
        if v['base_identity']!=digest(v['base_recipe']):yield failure('Optimizer primitive base differs from its authority digest')
        structural=['tokenizer','chunk_bytes','context_depth','context_limit','include_context']
        for identity,item in variants.items():
            expected=digest({'adapter_version':'adhd-native-retrieval-v1','runtime':v['runtime'],'recipe':item['recipe']})
            if identity!=expected:yield failure('Optimizer variant differs from its runtime-bound primitive recipe')
            if item['changes_index']!=any(item['recipe'][key]!=v['baseline_recipe'][key] for key in structural):yield failure('Optimizer structural reuse claim differs from its recipe')
            if item['status']=='qualified' and (item['summary'] is None or item['summary']['passed'] is not True):yield failure('Optimizer variant qualifies without passing training')
        winner=v['winner_identity']
        if winner is not None and winner not in variants:yield failure('Frozen optimizer winner is outside the candidate set')
        if v['operation']=='optimize' and winner is not None:
            passing=sorted((i for i in variants.values() if i['summary'] is not None and i['summary']['passed']),key=lambda i:(-i['summary']['mean_recall_gain_ppm'],i['summary']['total_calls_delta'],i['summary']['total_bytes_delta'],i['recipe_identity']))
            if not passing or passing[0]['recipe_identity']!=winner:yield failure('Optimizer winner differs from deterministic training selection')
        children={r['replay_id']:r for r in v['children']}
        if len(children)!=len(v['children']):yield failure('Optimizer child references are duplicated')
        cohorts={'training':'training_attempt_ids','held_out':'held_out_attempt_ids','regression':'regression_attempt_ids'}
        for cohort,field in cohorts.items():
            count_field={'training':'training_groups','held_out':'held_out_groups','regression':'regression_groups'}[cohort]
            if len(v[field])!=v[count_field]:yield failure('Optimizer cohort count differs from its frozen membership')
        group_cohorts={}
        for row in v['cases']:
            ref=children.get(row['replay_id'])
            if ref is None or any(ref[k]!=row[k] for k in ['run','attempt_id','cohort','variant_identity']):yield failure('Optimizer case differs from its expected owned child run')
            if row['attempt_id'] not in v[cohorts[row['cohort']]]:yield failure('Optimizer case is outside frozen cohort membership')
            if row['policy_identity']!=v['policy_identity']:yield failure('Optimizer case changed frozen qualification policy')
            if row['variant_identity'] not in variants:yield failure('Optimizer case refers to an unknown variant')
            if row['cohort']!='training' and row['variant_identity']!=winner:yield failure('Optimizer final cohort evaluated another candidate')
            if row['group_id'] in group_cohorts and group_cohorts[row['group_id']]!=row['cohort']:yield failure('Optimizer leaks one independent group across cohorts')
            group_cohorts[row['group_id']]=row['cohort']
            a,b=row['baseline'],row['candidate'];comp=row['comparison']
            if comp['eligible']!=(a['eligible'] and b['eligible']):yield failure('Optimizer case eligibility differs from raw branch eligibility')
            for branch in [a,b]:
                if branch['eligible']:
                    gold=branch['expected_gold'];retrieved=branch['retrieved_gold']
                    if retrieved>gold or branch['retrieval_recall_ppm']!=(1000000 if not gold else retrieved*1000000//gold):yield failure('Optimizer branch recall differs from confirmed gold counts')
            if a['eligible'] and b['eligible'] and a['expected_gold']!=b['expected_gold']:yield failure('Optimizer paired branches changed their confirmed gold')
            if comp['eligible']:
                if comp['retrieval_gain_ppm']!=b['retrieval_recall_ppm']-a['retrieval_recall_ppm']:yield failure('Optimizer gain differs from confirmed original recall')
                if comp['answer_regressions']!=int(a['answer_pass'] and not b['answer_pass']) or comp['false_supports']!=int(b['false_support']):yield failure('Optimizer comparison hides answer regression or false support')
        if v['status']=='qualified' and v['operation']=='optimize':
            if not v['evidence_available'] or not v['global_evidence_available'] or v['evaluation'] is None or not v['evaluation']['passed']:yield failure('Optimizer qualified without available passing final evidence')
        if v['index_manifest'] is not None:
            manifest=v['index_manifest'];build=v['build']
            if manifest['recipe_identity']!=winner or manifest['runtime']!=v['runtime'] or manifest['source_watermark']!=v['watermark']:yield failure('Optimizer global generation differs from frozen winner/runtime/watermark')
            for key,source in [('native_bytes','bytes'),('manifest_identity','source_manifest_identity'),('indexed','indexed'),('total','total')]:
                if build[key]!=manifest[source]:yield failure('Optimizer build summary differs from actual native manifest')
            if v['status']=='qualified' and (manifest['status']!='ready' or manifest['excluded']!=0):yield failure('Optimizer qualifies incomplete global rows')
    except (KeyError,TypeError,ValueError):return


def optimization_usage(validator,enabled,v,schema):
    if not enabled or not isinstance(v,dict):return
    try:
        keys=['records','calls','bytes','time_ms','uncertain_calls']
        sums={k:0 for k in keys}
        for row in v['cases']:
            usage=row['usage']
            for k in keys:
                for prefix in ['', 'cumulative_']:
                    key=prefix+k
                    if usage['total'][key]!=usage['baseline'][key]+usage['candidate'][key]:yield failure('Optimizer case total differs from actual paired branch work')
                sums[k]+=usage['total']['cumulative_'+k]
                if usage['total']['cumulative_'+k]<usage['total'][k]:yield failure('Optimizer pair erased prior-run charges')
            for k in ['calls','bytes','time_ms']:
                if row['comparison'][k+'_delta']!=usage['candidate']['cumulative_'+k]-usage['baseline']['cumulative_'+k]:yield failure('Optimizer case omits unsuccessful or retried model work')
        for k in keys:
            if v['usage']['cumulative_'+k]<v['usage'][k] or v['usage']['cumulative_'+k]<sums[k]:yield failure('Optimizer parent understates actual case costs')
        if v['usage']['cumulative_records']<sums['records']+v['build']['processed']:yield failure('Optimizer parent omits constructed native rows')
        full=len(v['cases'])==v['case_count']
        def check_evaluation(ev,rows):
            if ev is None:return
            if ev['cases']!=len(rows) or ev['groups']!=len({r['group_id'] for r in rows}):yield failure('Optimizer evaluation support differs from independent case groups')
            eligible=bool(rows) and all(r['comparison']['eligible'] and r['baseline']['eligible'] and r['candidate']['eligible'] for r in rows)
            if ev['eligible']!=eligible:yield failure('Optimizer aggregate eligibility differs from actual pairs')
            if eligible:
                for target,source in [('total_calls_delta','calls_delta'),('total_bytes_delta','bytes_delta'),('total_time_ms_delta','time_ms_delta'),('answer_regressions','answer_regressions'),('false_supports','false_supports')]:
                    if ev[target]!=sum(r['comparison'][source] for r in rows):yield failure('Optimizer aggregate arithmetic differs from actual case work')
                total=sum(r['comparison']['retrieval_gain_ppm'] for r in rows);mean=(abs(total)//len(rows))*(1 if total>=0 else -1)
                if ev['mean_recall_gain_ppm']!=mean:yield failure('Optimizer mean confirmed recall gain is incorrect')
                failures=sum(not r['baseline']['answer_pass'] or not r['candidate']['answer_pass'] for r in rows)
                if ev['answer_failures']!=failures:yield failure('Optimizer conceals failed asserted answers')
            if ev['passed'] and (any(r['comparison']['eligible'] and r['comparison']['retrieval_gain_ppm']<0 for r in rows) or not ev['eligible'] or ev['answer_failures'] or ev['answer_regressions'] or ev['false_supports'] or ev['mean_recall_gain_ppm']<=0):yield failure('Optimizer passes ineligible or regressing evidence')
        if full:
            for variant in v['variants']:
                yield from check_evaluation(variant['summary'],[r for r in v['cases'] if r['cohort']=='training' and r['variant_identity']==variant['recipe_identity']])
            yield from check_evaluation(v['evaluation'],[r for r in v['cases'] if r['cohort']!='training'])
    except (KeyError,TypeError,ValueError):return
