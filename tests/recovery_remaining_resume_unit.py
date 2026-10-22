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
    matrix={'passed':False,'artifact_sha256':'artifact','image_config_identity':'image','rows':[{'name':name,'passed':i<8,'exit_code':0 if i<8 else 1,'started':True}for i,name in enumerate(names[:9])],'unrun':names[9:],'executed':names[:9],'attempted':names[:9]}
    assert remainder_names(basis,matrix,'artifact','image')==names[8:] and len(names[8:])==34
    for key,value in [('passed',True),('artifact_sha256','other'),('image_config_identity','other'),('unrun',names[10:]),('executed',names[:8])]:
        bad=copy.deepcopy(matrix);bad[key]=value;denied(lambda bad=bad:remainder_names(basis,bad,'artifact','image'))
    for index,key,value in [(0,'passed',False),(0,'exit_code',1),(8,'passed',True),(8,'started',False),(8,'name','wrong-failure')]:
        bad=copy.deepcopy(matrix);bad['rows'][index][key]=value;denied(lambda bad=bad:remainder_names(basis,bad,'artifact','image'))
    assert matrix['passed'] is False and matrix['unrun']==names[9:]
    print('PASS recovery resume pure11: exact8wholepasses retained/failed+33unrun34selection, green/wrongartifact/image/reordered/omitted/unstarted/failureidentity/mismatchedexit denials; originalmatrixunchanged, runtime/provider starts0')


if __name__=='__main__':main()
