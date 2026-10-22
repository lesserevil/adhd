# Pure local-adoption graph validation; filesystem trust is tested separately.
[artifact,validator,checkpoint,configuration,fixtures_file,report]=System.argv()
[prefix|_]=String.split(File.read!(artifact),"\nunless Code.ensure_loaded?(ADHD.CLI) do",parts: 2)
Code.compile_string(prefix,artifact)
source=File.read!(validator) |> String.replace("defmodule ADHD.ProjectBackupValidation do","defmodule ADHD.LocalCandidateValidation do")
Code.compile_string(source,validator)
defmodule LocalValidationVectors do
  def outcome(s,c,limits \\ %{}) do
    opts=Map.merge(%{"max_records"=>1000000,"scan_batch_records"=>32,"deadline_ms"=>System.monotonic_time(:millisecond)+30000},limits)
    try do
      r=ADHD.LocalCandidateValidation.validate_local(s,c,c["project_id"],opts,fn _->:ok end)
      for field<-[:contexts,:optimization,:retrieval_selection,:retrieval_index,:feedback,:history_queries,:retrieval_queries,:archive_queries,:replay_queries,:idempotency,:sources,:admin_idempotency],Map.has_key?(s,field),do: true=(r.state[field]==s[field])
      {:ok,r.records}
    catch {:recovery,code,reason}->{code,reason} end
  end
  def run(fixtures,old,config) do
    good=Enum.map(fixtures,fn {id,s,c}->{"retained-"<>id,s,c,:ok,%{}} end)
    [{_,s,c}|_]=fixtures
    [{pub,_}|_]=Map.to_list(s.publications)
    [{agent,_}|_]=Map.to_list(c["agents"])
    cases=[{"actual-old-schema1-checkpoint",old,config,:ok,%{}}|good]++[
      {"malformed-derived-index-reject-not-reset",put_in(s,[:retrieval_index,"active"],%{"bad"=>true}),c,"RESTORE_INVALID_BACKUP",%{}},
      {"malformed-feedback-reject-not-rebuild",put_in(s,[:feedback,"cohorts","bad"],%{}),c,"RESTORE_INVALID_BACKUP",%{}},
      {"dangling-context-original",put_in(s,[:contexts,"absent"],%{"context"=>nil,"links"=>[]}),c,"RESTORE_INVALID_BACKUP",%{}},
      {"foreign-server",Map.put(s,:server_id,String.duplicate("f",32)),c,"RESTORE_INVALID_BACKUP",%{}},
      {"unknown-family",Map.put(s,:unknown_native_family,%{}),c,"RESTORE_INVALID_BACKUP",%{}},
      {"foreign-project",Map.put(s,:aliases,["foreign"]),c,"RESTORE_INVALID_BACKUP",%{}},
      {"missing-current-agent",old,Map.put(config,"agents",%{}),"RESTORE_CONFLICT",%{}},
      {"unknown-original-retry",put_in(s,[:idempotency,{agent,"local-negative"}],%{command: %{"op"=>"publish","text"=>"x"},result: %{"publication"=>Map.put(s.publications[pub].value,"id","absent")}}),c,"RESTORE_INVALID_BACKUP",%{}},
      {"record-limit",s,c,"RESTORE_INVALID_BACKUP",%{"max_records"=>1}},
      {"deadline",s,c,"RESTORE_TIMEOUT",%{"deadline_ms"=>System.monotonic_time(:millisecond)-1}},
      {"schema4-excluded-from-local-exception",Map.put(s,:schema,4),c,"RESTORE_INVALID_BACKUP",%{}}]
    Enum.map(cases,fn {id,state,current,expected,limits}->
      result=outcome(state,current,limits)
      passed=if expected==:ok,do: match?({:ok,_},result),else: match?({^expected,_},result)
      %{"id"=>id,"passed"=>passed,"outcome"=>inspect(result)}
    end)
  end
end
{:ok,old}=ADHD.RecoveryCheckpoint.preflight(File.read!(checkpoint),%{})
config=ADHD.JSON.decode!(File.read!(configuration)) |> Map.put("server_id",String.duplicate("1",32))
fixtures=ADHD.JSON.decode!(File.read!(fixtures_file)) |> Enum.map(fn f->
  s=ADHD.ProjectBackup.decode_snapshot(File.read!(f["snapshot"]))
  c=ADHD.JSON.decode!(File.read!(f["configuration"])) |> Map.put("server_id",s.server_id) |> Map.put("project_id",s.project)
  {f["id"],s,c}
end)
rows=LocalValidationVectors.run(fixtures,old,config)
result=%{"schema"=>"adhd/local-state-validation@1","passed"=>Enum.all?(rows,& &1["passed"]),"checks"=>length(rows),"artifact_sha256"=>ADHD.RecoveryFiles.sha(File.read!(artifact)),"validator_sha256"=>ADHD.RecoveryFiles.sha(File.read!(validator)),"harness_sha256"=>ADHD.RecoveryFiles.sha(File.read!(__ENV__.file)),"checkpoint_sha256"=>ADHD.RecoveryFiles.sha(File.read!(checkpoint)),"checks_detail"=>rows,"scope"=>"Pure candidate local state graph validation on actual oldest producer checkpoint and retained learned-workflow/controls/caps snapshots; no filesystem permission policy, startup, staging or official admission claim"}
File.write!(report,JSON.encode!(result));IO.inspect(result,limit: :infinity)
if not result["passed"],do: System.halt(1)
