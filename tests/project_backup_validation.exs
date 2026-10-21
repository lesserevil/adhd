# Independent offline validation vectors over retained, actual native snapshots.
[baseline,validator,fixture_file,report]=System.argv()
[modules|_]=String.split(File.read!(baseline),"unless Code.ensure_loaded?(ADHD.CLI)",parts: 2)
Code.compile_string(modules)
validator_bytes=File.read!(validator)
Code.compile_string(validator_bytes,validator)
defmodule BackupValidationVectors do
  def sha(b),do: Base.encode16(:crypto.hash(:sha256,b),case: :lower)
  def bundle(s,c),do: %{state: s,config: c,manifest: %{"server_id"=>s.server_id,"project_id"=>s.project,"aliases"=>Enum.sort(Enum.reject(s.aliases,&(&1==s.project))),"source"=>%{"sequence"=>s.seq,"storage_generation"=>Map.get(s,:storage_generation,0),"route_generation"=>Map.get(s,:route_generation,0),"project_epoch"=>Map.get(s,:project_epoch),"allocation_epoch"=>Map.get(s,:allocation_epoch)}}}
  def run_case(name,b,c,expected,limits \\ %{}) do
    opts=Map.merge(%{"max_records"=>1000000,"scan_batch_records"=>32,"deadline_ms"=>System.monotonic_time(:millisecond)+30000},limits)
    actual=try do
      r=ADHD.ProjectBackupValidation.validate(b,c,b.manifest["project_id"],opts,fn _->:ok end)
      # All accepted feature collections, qualifications and receipts stay intact.
      for field<-[:optimization,:retrieval_selection,:retrieval_index,:feedback,:history_queries,:retrieval_queries,:archive_queries,:replay_queries,:idempotency,:sources,:admin_idempotency],Map.has_key?(b.state,field),do: true=(r.state[field]==b.state[field])
      {:ok,r}
    catch {:recovery,code,_}->{:error,code} end
    case {expected,actual} do
      {:ok,{:ok,r}}->%{"id"=>name,"passed"=>true,"records"=>r.records,"references"=>r.references}
      {code,{:error,code}}->%{"id"=>name,"passed"=>true,"error"=>code}
      _->raise "#{name}: #{inspect(actual)} expected #{inspect(expected)}"
    end
  end
  def owned(c,provider \\ "local") do
    u=if provider=="local",do: %{"id"=>"owner","provider"=>"local","username"=>"owner"},else: %{"id"=>"owner","provider"=>"oidc","oidc"=>%{"provider_id"=>"org","issuer"=>"https://issuer.example","subject"=>"original-subject"}}
    c |> Map.put("users",[u]) |> Map.put("agent_owners",Map.new(c["agents"],fn {id,_}->{id,"owner"} end))
  end
  def trace_loop(calls) do
    receive do
      {:trace,_,:call,{module,function,args}}->trace_loop([%{"module"=>Atom.to_string(module),"function"=>Atom.to_string(function),"arity"=>length(args)}|calls])
      {:get,parent}->send(parent,{:calls,Enum.reverse(calls)});trace_loop(calls)
    end
  end
  def run(fixtures) do
    pairs=Enum.map(fixtures,fn f->
      bytes=File.read!(f["snapshot"]);<<"ADHDSTATE",1,digest::binary-size(32),body::binary>>=bytes
      true=(:crypto.hash(:sha256,body)==digest)
      s=:erlang.binary_to_term(body,[:safe]);c=ADHD.JSON.decode!(File.read!(f["configuration"])) |> Map.put("server_id",s.server_id)
      {f,bundle(s,c),c}
    end)
    tracer=spawn(fn->trace_loop([]) end)
    for {module,function}<-[{:dets,:open_file},{:httpc,:request},{ADHD.Config,:root},{ADHD.Config,:get},{ADHD.Store,:upgrade}],do: (Code.ensure_loaded!(module);true=(:erlang.trace_pattern({module,function,:_},true,[:local])>0))
    :erlang.trace(self(),true,[:call,:set_on_spawn,{:tracer,tracer}])
    base=Enum.map(pairs,fn {f,b,c}->run_case("retained-"<>f["id"],b,c,:ok) end)
    [{_,legacy,lc},{_,modern,mc}|_]=pairs
    [{pub,_}|_]=Map.to_list(legacy.state.publications)
    [{job,_}|_]=Map.to_list(legacy.state.jobs)
    [{agent,_}|_]=Map.to_list(lc["agents"])
    owned=owned(lc);ob=%{legacy|config: owned}
    rotated=put_in(owned,["agents",agent],String.duplicate("r",32))
    disabled=Map.update!(rotated,"users",&Enum.map(&1,fn u->Map.merge(u,%{"disabled"=>true,"role"=>"Viewer","project_ids"=>[]}) end))
    oidc=owned(lc,"oidc");oidcb=%{legacy|config: oidc}
    cases=[
      run_case("owned-current-credential-rotation",ob,rotated,:ok),
      run_case("disabled-owner-provenance-no-grant-import",ob,disabled,:ok),
      run_case("oidc-stable-original-provider-link",oidcb,oidc,:ok),
      run_case("oidc-issuer-drift",oidcb,update_in(oidc,["users"],fn [u]->[put_in(u,["oidc","issuer"],"https://other.example")] end),"RESTORE_CONFLICT"),
      run_case("oidc-subject-drift",oidcb,update_in(oidc,["users"],fn [u]->[put_in(u,["oidc","subject"],"different")] end),"RESTORE_CONFLICT"),
      run_case("owned-agent-reassignment",ob,put_in(owned,["agent_owners",agent],"other"),"RESTORE_CONFLICT"),
      run_case("missing-original-owner",%{ob|config: Map.put(owned,"users",[])},owned,"RESTORE_CONFLICT"),
      run_case("missing-current-owner",ob,Map.put(owned,"users",[]),"RESTORE_CONFLICT"),
      run_case("missing-current-agent",legacy,update_in(lc,["agents"],&Map.delete(&1,agent)),"RESTORE_CONFLICT"),
      run_case("unowned-credential-change-unprovable",legacy,put_in(lc,["agents",agent],String.duplicate("n",32)),"RESTORE_CONFLICT"),
      run_case("manifest-server-mismatch",put_in(legacy,[:manifest,"server_id"],String.duplicate("a",32)),lc,"RESTORE_INVALID_BACKUP"),
      run_case("snapshot-sequence-mismatch",put_in(legacy,[:manifest,"source","sequence"],legacy.state.seq+1),lc,"RESTORE_INVALID_BACKUP"),
      run_case("unknown-native-version",put_in(legacy,[:state,:schema],5),lc,"RESTORE_INVALID_BACKUP"),
      run_case("unknown-native-family",put_in(legacy,[:state,:unreviewed_family],%{}),lc,"RESTORE_INVALID_BACKUP"),
      run_case("dangling-job-original",put_in(legacy,[:state,:jobs,job,:publication_id],"absent"),lc,"RESTORE_INVALID_BACKUP"),
      run_case("broken-context-origin",put_in(legacy,[:state,:contexts,"absent"],%{"context"=>nil,"links"=>[]}),lc,"RESTORE_INVALID_BACKUP"),
      run_case("corrupt-retrieval-index-cannot-reset",put_in(legacy,[:state,:retrieval_index,"active"],%{"bad"=>true}),lc,"RESTORE_INVALID_BACKUP"),
      run_case("corrupt-feedback-cache-cannot-rebuild-away",put_in(legacy,[:state,:feedback,"cohorts","bad"],%{}),lc,"RESTORE_INVALID_BACKUP"),
      run_case("malformed-idempotency-key",put_in(legacy,[:state,:idempotency,:bad],%{command: %{},result: %{}}),lc,"RESTORE_INVALID_BACKUP"),
      run_case("unknown-retry-publication",put_in(legacy,[:state,:idempotency,{agent,"invented"}],%{command: %{"op"=>"publish","text"=>"x"},result: %{"publication"=>Map.put(legacy.state.publications[pub].value,"id","absent")}}),lc,"RESTORE_INVALID_BACKUP"),
      run_case("record-limit",legacy,lc,"RESTORE_INVALID_BACKUP",%{"max_records"=>10}),
      run_case("expired-frozen-deadline",legacy,lc,"RESTORE_TIMEOUT",%{"deadline_ms"=>System.monotonic_time(:millisecond)-1})
    ]
    s=modern.state |> Map.merge(%{schema: 4,route_generation: 1,project_epoch: String.duplicate("a",32),allocation_epoch: String.duplicate("b",32),allocation_counter: 0})
    history=%{binding: s.eventing.binding,next_offset: s.eventing.next_offset,quarantine: s.eventing.quarantine,gap: s.eventing.gap,last_error: s.eventing.last_error,offsets: Map.new(s.eventing.events,fn {id,r}->{id,r.offset} end)}
    s=put_in(s,[:eventing,:restore_history],[history]) |> Map.put(:recovery_work_audit,[%{"project_epoch"=>s.project_epoch,"at"=>"2026-10-20T00:00:00Z","work"=>[]}])
    b=bundle(s,mc)
    extra=[
      run_case("schema4-preserves-old-physical-history",b,mc,:ok),
      run_case("history-foreign-event",put_in(b,[:state,:eventing,:restore_history],[put_in(history,[:offsets,"absent"],0)]),mc,"RESTORE_INVALID_BACKUP"),
      run_case("history-invalid-binding",put_in(b,[:state,:eventing,:restore_history],[%{history|binding: "invalid"}]),mc,"RESTORE_INVALID_BACKUP"),
      run_case("audit-dangling-query",put_in(b,[:state,:recovery_work_audit],[%{"project_epoch"=>s.project_epoch,"at"=>"2026-10-20T00:00:00Z","work"=>[%{"kind"=>"queries","id"=>"absent","action"=>"expired"}]}]),mc,"RESTORE_INVALID_BACKUP")
    ]
    opts=%{"max_records"=>1000000,"scan_batch_records"=>32,"deadline_ms"=>System.monotonic_time(:millisecond)+30000,"max_backup_bytes"=>1073741824}
    staged=ADHD.ProjectBackupValidation.validate_staged(s,mc,s.project,opts,fn _->:ok end)
    true=(staged.state==s and staged.records>Enum.at(base,1)["records"])
    stage_limit=try do
      ADHD.ProjectBackupValidation.validate_staged(s,mc,s.project,Map.put(opts,"max_records",Enum.at(base,1)["records"]),fn _->:ok end)
      false
    catch {:recovery,"RESTORE_INVALID_BACKUP",_}->true end
    true=stage_limit
    byte_limit=try do
      ADHD.ProjectBackupValidation.validate_staged(s,mc,s.project,Map.put(opts,"max_backup_bytes",16),fn _->:ok end)
      false
    catch {:recovery,"RESTORE_INVALID_BACKUP",_}->true end
    true=byte_limit
    extra=extra++[%{"id"=>"staged-final-state-validated-unchanged","passed"=>true,"records"=>staged.records},%{"id"=>"staged-appended-records-counted","passed"=>true},%{"id"=>"staged-final-byte-bound","passed"=>true}]
    :erlang.trace(self(),false,[:all]);Process.sleep(20);send(tracer,{:get,self()})
    calls=receive do {:calls,c}->c after 1000->raise "missing call trace" end
    true=(calls==[])
    %{"checks"=>base++cases++extra,"forbidden_calls"=>calls,"trace_patterns"=>["dets.open_file/*","httpc.request/*","Config.root/0","Config.get/0","Store.upgrade/*"],"inputs"=>Enum.map(fixtures,fn f->Map.merge(Map.take(f,~w(id)),%{"snapshot_sha256"=>sha(File.read!(f["snapshot"])),"configuration_sha256"=>sha(File.read!(f["configuration"]))}) end)}
  end
end
fixtures=ADHD.JSON.decode!(File.read!(fixture_file))
result=BackupValidationVectors.run(fixtures) |> Map.merge(%{"schema"=>"adhd/project-backup-validator-check@1","passed"=>true,"scope"=>"Pure offline state/reference/principal validator only; no bundle-reader/service/install/complete-recovery claim","baseline_artifact_sha256"=>BackupValidationVectors.sha(File.read!(baseline)),"validator_sha256"=>BackupValidationVectors.sha(validator_bytes)})
File.write!(report,JSON.encode!(result)<>"\n")
IO.puts("PASS "<>Integer.to_string(length(result["checks"]))<>" offline checks; no forbidden calls")
