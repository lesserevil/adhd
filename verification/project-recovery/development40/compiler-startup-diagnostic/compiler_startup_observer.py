"""Preparation/analysis helpers only; never launch an app or compiler on import."""
import hashlib
import json
from pathlib import Path
import re


def diagnostic_image_argv(argv,image,root,tracer_hash):
 """Keep payload and original serve argument; add a public -r compiler tracer."""
 assert isinstance(argv,list) and argv[:2]==['docker','run'] and argv.count(image)==1
 assert '--entrypoint' not in argv and not any(v.startswith('--entrypoint=') for v in argv)
 assert '--pid' not in argv and not any(v.startswith('--pid=') for v in argv)
 root=Path(root);assert root.is_absolute() and root.resolve()==root
 mounts=[argv[i+1] for i,v in enumerate(argv) if v=='--mount']
 assert any(value==f'type=bind,src={root},dst={root}' for value in mounts)
 position=argv.index(image);original=argv[position+1:];assert len(original)==1 and json.loads(original[0])==['serve',str(root/'config.json')]
 tracer=root/'compiler-tracer.exs';assert tracer.is_file() and not tracer.is_symlink() and hashlib.sha256(tracer.read_bytes()).hexdigest()==tracer_hash
 log=root/'compiler-events.tsv';assert not log.exists() and not log.is_symlink()
 return argv[:position]+['--entrypoint','elixir','--env','ADHD_COMPILER_TRACE_FILE='+str(log),image,'-r',str(tracer),'/app/hub.exs',*original]


def owned_socket_rows(text):
 """Join namespace TCP tables only to positively observed PID1 socket FDs."""
 inodes=set(re.findall(r'socket:\[(\d+)\]',text));rows=[]
 for line in text.splitlines():
  parts=line.split()
  if len(parts)>9 and re.fullmatch(r'\d+:',parts[0]) and parts[9] in inodes:
   rows.append({'local_address':parts[1],'remote_address':parts[2],'state_hex':parts[3],'inode':parts[9]})
 return {'owned_socket_inodes':sorted(inodes),'joined_tcp_rows':rows,'joined_listeners':[v for v in rows if v['state_hex']=='0A']}
