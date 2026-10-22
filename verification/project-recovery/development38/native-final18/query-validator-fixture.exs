# Pure full-state validation of an untouched actual pending-query bundle plus
# explicit derived adversarial vectors. No reader/native opener/HTTP/writer.
[artifact,validator,bundle_dir,report|options]=System.argv()
[prefix|_]=String.split(File.read!(artifact),"\nunless Code.ensure_loaded?(ADHD.CLI) do",parts: 2)
Code.compile_string(prefix,artifact)
bytes=File.read!(validator) |> String.replace("defmodule ADHD.ProjectBackupValidation do","defmodule ADHD.CandidateBackupValidation do")
Code.compile_string(bytes,validator)
defmodule QueryBackupSchemaVectors do
  def outcome(module,b,c) do
    limits=%{"max_records"=>1000000,"scan_batch_records"=>32,"deadline_ms"=>System.monotonic_time(:millisecond)+30000}
    try do
      result=apply(module,:validate,[b,c,b.manifest["project_id"],limits,fn _->:ok end])
      true=result.state.source_queries==b.state.source_queries
      true=result.state.queries==b.state.queries
      :ok
    catch {:recovery,code,reason}->{code,reason} end
  end
  def host(b,host) do
    update_in(b,[:state,:source_queries],fn rows->Map.new(rows,fn {id,q}->
      value=Map.update!(q.value,"results",fn results->Enum.map(results,fn r->r |> Map.update!("requested",&Map.put(&1,"host",host)) |> Map.update!("scope",&Map.put(&1,"host",host)) end) end)
      {id,%{q|value: value}}
    end) end)
  end
  def receipt(b,command) do
    update_in(b,[:state,:admin_idempotency],&Map.put(&1,"schema-boundary-case",%{command: command,result: %{}}))
  end
  def run(b,c) do
    numeric=fn proposals->receipt(b,%{"op"=>"config_validate","expected_revision"=>1,"patch"=>%{"optimization"=>%{"max_active_proposals"=>4,"max_proposals"=>proposals}}}) end
    label=fn expectation,supports->receipt(b,%{"op"=>"save_retrieval_label","attempt_id"=>"retained-attempt","expected_label_revision"=>0,"expected_revision"=>1,"message_id"=>"label-boundary","confirm"=>true,"label"=>%{"expectation"=>expectation,"support_ids"=>supports,"cohort"=>"training","confirmed"=>true,"tags"=>[],"note"=>""}}) end
    cases=[{"untouched-actual-pending-source-and-discovery",b,:ok},
      {"valid-ipv6",host(b,"2001:db8::1"),:ok},{"valid-ipv6-loopback",host(b,"::1"),:ok},
      {"uppercase-host",host(b,"GitHub.com"),:invalid},{"leading-dash-host",host(b,"-bad.example"),:invalid},
      {"malformed-ipv6",host(b,":::"),:invalid},{"extra-ipv6-groups",host(b,"1:2:3:4:5:6:7:8:9"),:invalid},
      {"conditional-number-exact-bound",numeric.(4),:ok},{"conditional-number-below-bound",numeric.(3),:invalid},
      {"noninteger-numeric-boolean",numeric.(true),:invalid},
      {"supported-label-needs-evidence",label.("supported",[]),:invalid},
      {"supported-label-one-evidence",label.("supported",["retained-support"]),:ok},
      {"no-evidence-label-forbids-support",label.("no_evidence",["retained-support"]),:invalid},
      {"no-evidence-label-empty-support",label.("no_evidence",[]),:ok}]
    Enum.map(cases,fn {id,value,expected}->
      actual=outcome(ADHD.CandidateBackupValidation,value,c)
      passed=if expected==:ok,do: actual==:ok,else: match?({"RESTORE_INVALID_BACKUP","schema"},actual)
      %{"id"=>id,"expected"=>Atom.to_string(expected),"actual"=>inspect(actual),"passed"=>passed}
    end)
  end
end
s=ADHD.ProjectBackup.decode_snapshot(File.read!(Path.join(bundle_dir,"project.snapshot")))
c=ADHD.JSON.decode!(File.read!(Path.join(bundle_dir,"server-config.json")))
m=ADHD.JSON.decode!(File.read!(Path.join(bundle_dir,"manifest.json")))
b=%{state: s,config: c,manifest: m}
negative=QueryBackupSchemaVectors.outcome(ADHD.ProjectBackupValidation,b,c)
rows=QueryBackupSchemaVectors.run(b,c)
expected_baseline=if options==["--fixed-baseline"],do: :ok,else: {"RESTORE_INVALID_BACKUP","schema"}
passed=Enum.all?(rows,& &1["passed"]) and negative==expected_baseline
result=%{"schema"=>"adhd/backup-query-schema-check@1","passed"=>passed,"checks"=>length(rows),"baseline_expected"=>inspect(expected_baseline),"baseline_outcome"=>inspect(negative),"artifact_sha256"=>ADHD.RecoveryFiles.sha(File.read!(artifact)),"validator_sha256"=>ADHD.RecoveryFiles.sha(File.read!(validator)),"harness_sha256"=>ADHD.RecoveryFiles.sha(File.read!(__ENV__.file)),"snapshot_sha256"=>ADHD.RecoveryFiles.sha(File.read!(Path.join(bundle_dir,"project.snapshot"))),"checks_detail"=>rows,"scope"=>"Pure full-state validator on actual untouched accepted pending-query bundle, plus explicitly derived hostile/conditional-schema state vectors; no bundle reader, DETS opener, provider, recovery install, container or admission claim"}
File.write!(report,JSON.encode!(result));IO.inspect(result,limit: :infinity)
if not passed,do: System.halt(1)
