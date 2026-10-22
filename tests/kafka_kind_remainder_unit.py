"""No runtimes: explicit remainder defaults and complete layer/config proofs."""
from types import SimpleNamespace
import hashlib
import json
from unittest.mock import patch
from kafka_platform_matrix import selected_platforms,image_overrides,verify_equivalence
from kafka_image_equivalence import verify_pair
from kafka_oauth_custody import NamespaceLease


def denied(call):
    try:call()
    except AssertionError:return
    raise AssertionError('Invalid preparation accepted')


def main():
    assert selected_platforms(SimpleNamespace())==['compose','k8s']
    assert selected_platforms(SimpleNamespace(platforms=['k8s']))==['k8s']
    for values in [[],['k8s','k8s'],['unknown']]:denied(lambda values=values:selected_platforms(SimpleNamespace(platforms=values)))
    assert image_overrides(SimpleNamespace())=={}
    denied(lambda:image_overrides(SimpleNamespace(broker_image='mutable:tag')))
    config=json.dumps({'rootfs':{'diff_ids':['sha256:'+'1'*64,'sha256:'+'2'*64]}}).encode();c='sha256:'+hashlib.sha256(config).hexdigest()
    manifest=json.dumps({'config':{'digest':c},'layers':[{'mediaType':'application/vnd.oci.image.layer.v1.tar','digest':value} for value in ['sha256:'+'1'*64,'sha256:'+'2'*64]]}).encode();m='sha256:'+hashlib.sha256(manifest).hexdigest()
    original={'Id':c,'RootFS':{'Layers':['sha256:'+'1'*64,'sha256:'+'2'*64]}}
    def read(argv):
        if argv[1:3]==['image','inspect']:return json.dumps([original]).encode()
        return config if argv[-1]==c else manifest
    proof=verify_pair('owned','imported@'+m,'original',read);assert proof['layers']==original['RootFS']['Layers'] and proof['layer_count']==2
    original['RootFS']['Layers'][1]='sha256:'+'3'*64;denied(lambda:verify_pair('owned','imported@'+m,'original',read));original['RootFS']['Layers'][1]='sha256:'+'2'*64
    denied(lambda:verify_pair('owned','imported@sha256:'+'0'*64,'original',read))
    lease=NamespaceLease('adhd-final-40c-kind','1'*32,prefix='adhd-final-');document=lease.document();assert lease.issued
    assert lease.deletion({'metadata':{**document['metadata'],'uid':'first'}})['preconditions']=={'uid':'first'}
    denied(lambda:lease.deletion({'metadata':{**document['metadata'],'uid':'replacement'}}))
    print('PASS Kind remainder pure7: originalbothdefaults, explicitKindonly, duplicate/invalidsubset and mutableimage denial, all2layer/config equality and tampering denial, namespace issued-before-create and UID-precondition replacement denial; apps/providers0')


if __name__=='__main__':main()
