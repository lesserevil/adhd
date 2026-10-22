# One independent foreign-owner rejection against the exact frozen runtime.
[artifact,path,project,report]=System.argv()
[prefix|_]=String.split(File.read!(artifact),"\nunless Code.ensure_loaded?(ADHD.CLI) do",parts: 2)
Code.compile_string(prefix,artifact)
uid=File.stat!("/proc/self").uid;before=File.stat!(path)
true=before.uid != uid
bytes=File.read!(path);identity=ADHD.RecoveryFiles.identity(before)
tracer=spawn(fn->
 loop=fn recur,calls->receive do {:trace,_,:call,{m,f,a}}->recur.(recur,[{m,f,length(a)}|calls]);{:get,p}->send(p,{:calls,calls}) end end
 loop.(loop,[])
end)
patterns=[{:dets,:open_file},{:file,:change_mode},{:file,:write_file},{:file,:rename},{:httpc,:request}]
for {m,f}<-patterns,do: (Code.ensure_loaded!(m);:erlang.trace_pattern({m,f,:_},true,[:local]))
:erlang.trace(self(),true,[:call,:set_on_spawn,{:tracer,tracer}])
outcome=try do
 ADHD.Storage.local_legacy_state(path,project,nil,ADHD.LocalLegacy.limits())
 :accepted
catch {:recovery,code,reason}->{code,reason} end
:erlang.trace(self(),false,[:all]);barrier=:erlang.trace_delivered(:all)
receive do {:trace_delivered,:all,^barrier}->:ok after 3000->raise "trace barrier" end
send(tracer,{:get,self()});calls=receive do {:calls,c}->c after 3000->raise "trace result" end
for {m,f}<-patterns,do: :erlang.trace_pattern({m,f,:_},false,[:local])
unchanged=identity==ADHD.RecoveryFiles.identity(File.stat!(path)) and bytes==File.read!(path)
result=%{"schema"=>"adhd/local-foreign-owner-native@1","passed"=>outcome=={"RESTORE_INVALID_BACKUP","path"} and unchanged and calls==[],"server_uid"=>uid,"observed_foreign_uid"=>before.uid,"mode"=>Integer.to_string(Bitwise.band(before.mode,0o7777),8),"links"=>before.links,"outcome"=>inspect(outcome),"input_unchanged"=>unchanged,"forbidden_calls"=>Enum.map(calls,&inspect/1),"artifact_sha256"=>ADHD.RecoveryFiles.sha(File.read!(artifact)),"checkpoint_sha256"=>ADHD.RecoveryFiles.sha(bytes),"harness_sha256"=>ADHD.RecoveryFiles.sha(File.read!(__ENV__.file)),"scope"=>"One unprivileged actual runtime local-reader call on valid foreign-owned checkpoint; helper container only changes owned fixture metadata, not application image qualification"}
File.write!(report,JSON.encode!(result));IO.puts(JSON.encode!(result));if not result["passed"],do: System.halt(1)
