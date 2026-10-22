"""Pure exactfailed-plus-unrun selection guards; no runtimes or providers."""
import copy
from image_recovery_remaining_matrix import remainder_names


def denied(call):
    try:call()
    except AssertionError:return
    raise AssertionError('Invalid prior qualification selection admitted')


def main():
    names=['whole'+str(i)for i in range(8)]+['crash-damaged-after-install-snapshot']+['unrun'+str(i)for i in range(33)]
    basis={'jobs':[{'name':name}for name in names]}
    matrix={'planned':42,'passed':False,'artifact_sha256':'artifact','image_config_identity':'image','rows':[{'name':name,'passed':i<8,'exit_code':0 if i<8 else 1,'started':True}for i,name in enumerate(names[:9])],'unrun':names[9:],'executed':names[:9],'attempted':names[:9]}
    assert remainder_names(basis,matrix,'artifact','image')==names[8:] and len(names[8:])==34
    for key,value in [('passed',True),('artifact_sha256','other'),('image_config_identity','other'),('unrun',names[10:]),('executed',names[:8])]:
        bad=copy.deepcopy(matrix);bad[key]=value;denied(lambda bad=bad:remainder_names(basis,bad,'artifact','image'))
    for index,key,value in [(0,'passed',False),(0,'exit_code',1),(8,'passed',True),(8,'started',False),(8,'name','wrong-failure')]:
        bad=copy.deepcopy(matrix);bad['rows'][index][key]=value;denied(lambda bad=bad:remainder_names(basis,bad,'artifact','image'))
    assert matrix['passed'] is False and matrix['unrun']==names[9:]
    names34=['crash-'+str(i) for i in range(15)]+['primitive-allocator']+['component-'+str(i) for i in range(16)]+['rebind','rebind-hostile']
    prior={'jobs':[{'name':n}for n in names34]}
    terminal={'planned':34,'passed':False,'artifact_sha256':'artifact','image_config_identity':'image',
        'rows':[{'name':n,'passed':i<15,'exit_code':0 if i<15 else 1,'started':True}for i,n in enumerate(names34[:16])],
        'unrun':names34[16:],'executed':names34[:16],'attempted':names34[:16]}
    assert remainder_names(prior,terminal,'artifact','image')==names34[15:] and len(names34[15:])==19
    for key,value in [('planned',33),('passed',True),('unrun',names34[17:])]:
        bad=copy.deepcopy(terminal);bad[key]=value;denied(lambda bad=bad:remainder_names(prior,bad,'artifact','image'))
    for index,key,value in [(14,'passed',False),(15,'name','other'),(15,'exit_code',0)]:
        bad=copy.deepcopy(terminal);bad['rows'][index][key]=value;denied(lambda bad=bad:remainder_names(prior,bad,'artifact','image'))
    names19=['primitive-allocator','primitive-epoch']+['component-'+str(i)for i in range(15)]+['rebind','rebind-hostile']
    basis19={'jobs':[{'name':n}for n in names19]}
    terminal19={'planned':19,'passed':False,'artifact_sha256':'artifact','image_config_identity':'image',
        'rows':[{'name':n,'passed':i==0,'exit_code':0 if i==0 else 1,'started':True}for i,n in enumerate(names19[:2])],
        'unrun':names19[2:],'executed':names19[:2],'attempted':names19[:2]}
    assert len(remainder_names(basis19,terminal19,'artifact','image'))==18
    for key,value in [('planned',18),('passed',True),('unrun',names19[3:])]:
        bad=copy.deepcopy(terminal19);bad[key]=value;denied(lambda bad=bad:remainder_names(basis19,bad,'artifact','image'))
    for index,key,value in [(0,'passed',False),(1,'name','other'),(1,'exit_code',0)]:
        bad=copy.deepcopy(terminal19);bad['rows'][index][key]=value;denied(lambda bad=bad:remainder_names(basis19,bad,'artifact','image'))
    print('PASS recovery resume pure25: exact8wholepasses retained/failed+33unrun34selection, green/wrongartifact/image/reordered/omitted/unstarted/failureidentity/mismatchedexit denials; originalmatrixunchanged, runtime/provider starts0')


if __name__=='__main__':main()
