import sys,json,hashlib,os
from pathlib import Path
sys.path.insert(0,'/home/horde/src/adhd/_build/acme/image42-plans03/frozen/tests')
from acme_image_target import AcceptedImageTarget
root=Path('/home/horde/src/adhd/_build/acme/image42-plans03/runtime/foundation')
plan=json.loads(Path('/home/horde/src/adhd/_build/acme/image42-plans03/plans/foundation/plan.json').read_text())
target=AcceptedImageTarget(plan);image=target.image(root);image.image_id=target.value['image']
flags='+S 2:2 -public_key cacerts_path '+"'"+json.dumps(str(root/'hub/owned-peer-root.pem'))+"'"+' -kernel inetrc '+"'"+json.dumps('/home/horde/src/adhd/.worktrees/config-acceptance/_build/acme/peer-env04/corrected.inetrc')+"'"
old=image.docker

def docker(*args,check=True):
    if args and args[0]=='run':args=(args[0],'--user',str(os.getuid())+':'+str(os.getgid()),'--env','ERL_FLAGS='+flags,'--mount','type=bind,src='+str(root)+',dst='+str(root)+',readonly','--mount','type=bind,src='+'/home/horde/src/adhd/.worktrees/config-acceptance/_build/acme/peer-env04'+',dst='+'/home/horde/src/adhd/.worktrees/config-acceptance/_build/acme/peer-env04'+',readonly',*args[1:])
    return old(*args,check=check)
image.docker=docker
code='''Application.ensure_all_started(:public_key)
IO.inspect(Application.get_env(:public_key,:cacerts_path),label: "cacerts_path")
IO.inspect(Application.get_env(:kernel,:inetrc),label: "inetrc")
IO.inspect(:inet.getaddr(~c"one.acme.test",:inet),label: "one")
IO.inspect(:inet.getaddr(~c"two.acme.test",:inet),label: "two")
try do
 roots=:public_key.cacerts_get()
 IO.inspect(length(roots),label: "root_count")
 IO.inspect(Enum.map(roots,fn {:cert,der,_}->Base.encode16(:crypto.hash(:sha256,der),case: :lower); der when is_binary(der)->Base.encode16(:crypto.hash(:sha256,der),case: :lower); _->"unrecognized_shape" end),label: "root_der_hashes")
rescue e->IO.inspect(e.__struct__,label: "root_error_class")
catch k,_->IO.inspect(k,label: "root_error_kind")
end
'''
try:
    raw=image.probe('/usr/local/bin/elixir','-e',code)
    print(raw.decode())
finally:
    Path('_build/acme/peer-env04/result.json').write_text(json.dumps({'flags':flags,'events':image.probe_events,'probe_cleanup_blocked':image.probe_cleanup_blocked},indent=2)+'\n')
