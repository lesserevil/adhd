from pathlib import Path
import hashlib,json,time
parent,start=745807,'29172594'
root=Path('/proc');path=Path('_build/acme/finaldocs01/process-cases.jsonl')
rows=json.loads(Path('verification/acceptance/hub.json').read_text())['cases']
def stat(pid):
 try:return (root/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
 except(FileNotFoundError,ProcessLookupError):return None
last=None;count=0;deadline=time.monotonic()+7200
with path.open('x') as out:
 path.chmod(0o600)
 while time.monotonic()<deadline:
  s=stat(parent)
  if s is None or s[19]!=start:break
  try:children=(root/str(parent)/'task'/str(parent)/'children').read_text().split()
  except(FileNotFoundError,ProcessLookupError):continue
  for child in children:
   cs=stat(child)
   if cs is None:continue
   try:args=(root/child/'cmdline').read_bytes().split(b'\0')
   except(FileNotFoundError,ProcessLookupError):continue
   identity=(child,cs[19])
   if identity==last:continue
   matches=[]
   for arg in args:
    try:value=json.loads(arg)
    except(ValueError,UnicodeDecodeError):continue
    matches.extend(row['case_id'] for row in rows if row['arguments']==value)
   event={'monotonic':time.monotonic(),'pid':int(child),'start_ticks':cs[19],'argv_sha256':hashlib.sha256(b'\0'.join(args)).hexdigest(),'authored_case_ids':matches}
   raw=json.dumps(event,separators=(',',':'))+'\n'
   if out.tell()+len(raw)>65500:raise RuntimeError('Owned observation byte cap')
   out.write(raw);out.flush();last=identity;count+=1
  time.sleep(1)
 out.write(json.dumps({'observer_closed':True,'events':count,'parent_original_identity_absent':stat(parent) is None or stat(parent)[19]!=start})+'\n')
print(json.dumps({'observer_closed':True,'events':count,'raw_args_logged':False}))
