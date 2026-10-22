# Independent local-file adoption component probe; never opens original DETS.
[baseline,source,legacy_config,work,report]=System.argv()
[prefix,_]=String.split(File.read!(baseline),"\nunless Code.ensure_loaded?(ADHD.CLI) do",parts: 2)
Code.compile_string(prefix,baseline)
Code.compiler_options(ignore_module_conflict: true)
for file<-~w(project_backup_validation.exs storage.exs projects.exs storage_registry.exs migration.exs config.exs),do: Code.compile_file(Path.join(source,file))
File.mkdir_p!(work);File.chmod!(work,0o700)
original=ADHD.JSON.decode!(File.read!(legacy_config));original_path=original["store_path"]
original_stat=File.stat!(original_path);original_bytes=File.read!(original_path)
original_identity=ADHD.RecoveryFiles.identity(original_stat)
path=Path.join(work,"local.dets");File.write!(path,original_bytes);File.chmod!(path,0o664)
config=Map.put(original,"store_path",path);project=config["project_id"]
check=fn true->:ok;_->raise "Local adoption invariant failed" end
rejected=fn callback->
  try do callback.();false catch {:recovery,_,_}->true;{:domain,_}->true end
end
snapshot=fn state->body=ADHD.Storage.bytes(state);<<"ADHDSTATE",1,(:crypto.hash(:sha256,body))::binary,body::binary>> end
budget=ADHD.LocalLegacy.limits(config)
{:ok,raw}=ADHD.RecoveryCheckpoint.preflight(original_bytes,budget)
check.(raw.schema==1 and not Map.has_key?(raw,:server_id))
{:module,:dets}=Code.ensure_loaded(:dets)
installed=:erlang.trace_pattern({:dets,:open_file,:_},true,[:local]);check.(installed>0)
collector=spawn(fn->
  count=fn recur,n->receive do {:trace,_,:call,{:dets,:open_file,_}}->recur.(recur,n+1);{:count,p}->send(p,{:calls,n});recur.(recur,n) end end
  count.(count,0)
end)
:erlang.trace(self(),true,[:call,{:tracer,collector}])
cases=[]
proof=ADHD.Storage.local_legacy_state(path,project,nil,budget) |> ADHD.LocalLegacy.validate(config,project)
check.(is_binary(proof.validated.server_id) and byte_size(proof.validated.server_id)==32)
check.(proof.state==raw and Map.keys(proof.validated.publications)==Map.keys(raw.publications))
for {id,row}<-raw.publications do
  next=proof.validated.publications[id]
  check.(next.seq==row.seq and Enum.all?(row.value,fn {k,v}->next.value[k]==v end))
  check.(Map.keys(next.value)--Map.keys(row.value) |> Enum.all?(&(&1 in ~w(information_type source occurred_at))))
end
:ok=ADHD.Storage.verify_local_legacy(proof)
explicit=String.duplicate("d",32)
bound=ADHD.Storage.local_legacy_state(path,project,explicit,ADHD.LocalLegacy.limits(config)) |> ADHD.LocalLegacy.validate(Map.put(config,"server_id",explicit),project)
check.(bound.validated.server_id==explicit)

cases=[%{"case"=>"actual-oldest-schema1-mode0664-safe-full-proof-provisional-genesis","passed"=>true}|cases]
for mode<-[0o600,0o640,0o644,0o660,0o664] do
  File.chmod!(path,mode)
  p=ADHD.Storage.local_legacy_state(path,project,nil,ADHD.LocalLegacy.limits(config)) |> ADHD.LocalLegacy.validate(config,project)
  :ok=ADHD.Storage.verify_local_legacy(p);check.(p.state==raw and Bitwise.band(File.stat!(path).mode,0o777)==mode)
end
cases=[%{"case"=>"normal-historical-checkpoint-modes-read-without-permission-changes","passed"=>true}|cases]
File.chmod!(path,0o664)
snap=path<>".snapshot";File.write!(snap,snapshot.(raw));File.chmod!(snap,0o644)
p=ADHD.Storage.local_legacy_state(path,project,nil,ADHD.LocalLegacy.limits(config)) |> ADHD.LocalLegacy.validate(config,project)
check.(p.state==raw);:ok=ADHD.Storage.verify_local_legacy(p)
cases=[%{"case"=>"historical-snapshot-mode0644-and-closed-checkpoint-agree","passed"=>true}|cases]
File.rm!(snap)
# A successful initial proof binds absent authoritative siblings too.
p=ADHD.Storage.local_legacy_state(path,project,nil,ADHD.LocalLegacy.limits(config))
File.write!(snap,snapshot.(raw));File.chmod!(snap,0o600)
check.(rejected.(fn->ADHD.Storage.verify_local_legacy(p) end));File.rm!(snap)
cases=[%{"case"=>"new-authoritative-snapshot-after-proof-rejects-before-decision","passed"=>true}|cases]
cases=Enum.reduce([
  {"world-write",fn->File.chmod!(path,0o666) end,fn->File.chmod!(path,0o664) end},
  {"execute",fn->File.chmod!(path,0o764) end,fn->File.chmod!(path,0o664) end},
  {"hardlink",fn->File.ln!(path,path<>".alias") end,fn->File.rm!(path<>".alias") end},
  {"malformed-checkpoint",fn->File.write!(path,<<0,1,2,3>>) end,fn->File.write!(path,original_bytes);File.chmod!(path,0o664) end}
],cases,fn {name,prepare,restore},cases->
  prepare.();before={File.read!(path),ADHD.RecoveryFiles.identity(File.stat!(path))}
  check.(rejected.(fn->ADHD.Storage.local_legacy_state(path,project,nil,ADHD.LocalLegacy.limits(config)) end))
  check.(before=={File.read!(path),ADHD.RecoveryFiles.identity(File.stat!(path))});restore.()
  [%{"case"=>"reject-"<>name<>"-without-input-change","passed"=>true}|cases]
end)
symlink=Path.join(work,"symbolic.dets");File.ln_s!(path,symlink)
check.(rejected.(fn->ADHD.Storage.local_legacy_state(symlink,project,nil,ADHD.LocalLegacy.limits(config)) end));check.(File.lstat!(symlink).type==:symlink)
cases=[%{"case"=>"reject-symbolic-source-without-following-or-changing-target","passed"=>true}|cases]
check.(rejected.(fn->ADHD.Storage.local_legacy_state(path,"different-project",nil,ADHD.LocalLegacy.limits(config)) end))
cases=[%{"case"=>"reject-wrong-project-before-identity-genesis","passed"=>true}|cases]
File.write!(snap,snapshot.(Map.put(raw,:server_id,String.duplicate("a",32))));File.chmod!(snap,0o644)
check.(rejected.(fn->ADHD.Storage.local_legacy_state(path,project,String.duplicate("b",32),ADHD.LocalLegacy.limits(config)) end));File.rm!(snap)
cases=[%{"case"=>"reject-nonnull-foreign-server-without-replacement-genesis","passed"=>true}|cases]
check.(rejected.(fn->ADHD.RecoveryFiles.read(path,byte_size(original_bytes),File.stat!("/proc/self").uid) end))
cases=[%{"case"=>"imported-bundle-private-reader-still-rejects-local0664","passed"=>true}|cases]
check.(rejected.(fn->ADHD.Storage.local_legacy_state(path,project,nil,Map.put(ADHD.LocalLegacy.limits(config),"max_backup_bytes",4)) end))
check.(rejected.(fn->ADHD.Storage.local_legacy_state(path,project,nil,Map.put(ADHD.LocalLegacy.limits(config),"deadline_ms",System.monotonic_time(:millisecond)-1)) end))
cases=[%{"case"=>"bounded-local-source-bytes-and-deadline","passed"=>true}|cases]
empty_path=Path.join(work,"empty.dets");empty_config=%{"project_id"=>project,"store_path"=>empty_path,"agents"=>%{},"server_id"=>String.duplicate("c",32)}
empty=ADHD.Storage.local_legacy_state(empty_path,project,empty_config["server_id"],ADHD.LocalLegacy.limits(empty_config)) |> ADHD.LocalLegacy.validate(empty_config,project)
check.(empty.validated==nil and Enum.sort(empty.absent)==Enum.sort([empty_path,empty_path<>".snapshot"]))
File.write!(empty_path,"unexpected file");File.chmod!(empty_path,0o600)
check.(rejected.(fn->ADHD.Storage.verify_local_legacy(empty) end))
cases=[%{"case"=>"both-absent-uninitialized-proof-rejects-new-checkpoint","passed"=>true}|cases]
config_path=Path.join(work,"empty-config.json")
File.write!(config_path,JSON.encode!(empty_config));File.chmod!(config_path,0o600)
# Remove the deliberate appearance witness before this separate fresh admission.
File.rm!(empty_path)
migrated=ADHD.Migration.config(config_path,empty_config)
check.(migrated["server_id"]==empty_config["server_id"])
marker=ADHD.JSON.decode!(File.read!(config_path<>".project-upgrade"))
check.(marker["phase"]=="decided" and marker["config"]["server_id"]==empty_config["server_id"])
cases=[%{"case"=>"empty-legacy-migration-preserves-existing-configured-server-id","passed"=>true}|cases]
check.(File.read!(original_path)==original_bytes and ADHD.RecoveryFiles.identity(File.stat!(original_path))==original_identity)
:erlang.trace(self(),false,[:call]);:erlang.trace_pattern({:dets,:open_file,:_},false,[:local])
Process.sleep(20);send(collector,{:count,self()});count=receive do {:calls,n}->n after 2000->raise "Trace result missing" end
check.(count==0);Process.exit(collector,:kill)
cases=[%{"case"=>"zero-native-openers-and-original-producer-input-unchanged","passed"=>true}|cases]
result=%{"schema"=>"adhd/local-legacy-component@1","passed"=>true,"cases"=>Enum.reverse(cases),"native_open_calls"=>count,"native_trace_patterns_installed"=>installed,"baseline_sha256"=>ADHD.RecoveryFiles.sha(File.read!(baseline)),"source_hashes"=>Map.new(~w(project_backup_validation.exs storage.exs projects.exs storage_registry.exs migration.exs config.exs),fn f->{f,ADHD.RecoveryFiles.sha(File.read!(Path.join(source,f)))} end),"harness_sha256"=>ADHD.RecoveryFiles.sha(File.read!(__ENV__.file)),"old_checkpoint_sha256"=>ADHD.RecoveryFiles.sha(original_bytes),"old_checkpoint_mode"=>Integer.to_string(Bitwise.band(original_stat.mode,0o777),8)}
File.write!(report,JSON.encode!(result));IO.puts("PASS local adoption component "<>Integer.to_string(length(cases)))
