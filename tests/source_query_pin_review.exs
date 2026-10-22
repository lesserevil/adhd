# Isolated actual frozen-module tests; no HTTP/callback/restart claim.
[artifact, report] = System.argv()
[prefix | _] = String.split(File.read!(artifact), "\nunless Code.ensure_loaded?(ADHD.CLI) do", parts: 2)
Code.compile_string(prefix, artifact)
ExUnit.start(autorun: false)
defmodule SourceQueryPinReview do
  use ExUnit.Case, async: false
  alias ADHD.{Domain, Directory, SourceQueries}
  defp fixture do
    scope=%{"provider"=>"github","host"=>"github.com","tenant"=>"scope","resource"=>"repo"}
    peer=%{"server_id"=>String.duplicate("b",32),"project_id"=>"remote","url"=>"http://127.0.0.1:9","token"=>String.duplicate("t",32)}
    c=%{"project_id"=>"red","server_id"=>String.duplicate("a",32),"agents"=>%{"agent"=>String.duplicate("x",32)},"users"=>[],"agent_owners"=>%{},"federation"=>%{"retry_ms"=>50,"peers"=>[peer],"catalog"=>%{"visible"=>true,"entries"=>[]}}}
    pin=%{"server_id"=>peer["server_id"],"project_id"=>peer["project_id"],"revision"=>String.duplicate("c",64),"scope"=>scope}
    row=%{"requested"=>scope,"scope"=>scope,"status"=>"pending","owner_server_id"=>peer["server_id"],"owner_project_id"=>peer["project_id"],"response"=>nil}
    value=%{"id"=>"query-pinned","project_id"=>"red","owner_id"=>"agent","question"=>"Original exact question","created_at"=>Domain.now(),"deadline_at"=>Domain.at(Domain.ms()+60000),"status"=>"pending","results"=>[row],"coverage"=>[]}
    job=%{value: value,attempts: %{},peer_ids: [Directory.peer_key(peer)],scope_projects: ["red"]}
    s=%{server_id: c["server_id"],directory: %{},owner_pins: %{Directory.digest(scope)=>pin},source_queries: %{"query-pinned"=>job}}
    :persistent_term.put({ADHD.Config,:config},c)
    {s,c,peer,scope}
  end
  defp prepare(s,c),do: SourceQueries.prepare(s,c,"query-pinned")
  defp value(s),do: s.source_queries["query-pinned"].value
  defp row(s),do: hd(value(s)["results"])
  defp cache(s,peer,scope,claim,status \\ "ready",fresh \\ true) do
    entries=if claim,do: [%{"scope"=>scope,"canonical"=>true}],else: []
    cat=%{"server_id"=>peer["server_id"],"project_id"=>peer["project_id"],"visible"=>true,"revision"=>String.duplicate("c",64),"items"=>entries,"expires_ms"=>Domain.ms()+if(fresh,do: 10000,else: -1)}
    put_in(s,[:directory,Directory.peer_key(peer)],%{"server_id"=>peer["server_id"],"status"=>status,"catalog"=>cat})
  end
  setup do
    on_exit(fn -> :persistent_term.erase({ADHD.Config,:config}) end)
    :ok
  end
  test "already dispatched pin waits without dispatch after cache loss; exact identity and deadline remain" do
    {s,c,_,_}=fixture();before=value(s)
    assert {:idle,next}=prepare(s,c)
    assert value(next)["status"]=="pending" and row(next)["status"]=="pending"
    assert Map.drop(value(next),["coverage"])==Map.drop(before,["coverage"])
    assert next.source_queries["query-pinned"].attempts[0]>Domain.ms()
  end
  test "expired canonical catalog waits, reports unavailable and cannot export a task" do
    {s,c,p,scope}=fixture();s=cache(s,p,scope,true,"ready",false)
    assert {:idle,next}=prepare(s,c)
    assert row(next)["status"]=="pending"
    assert hd(value(next)["coverage"])["status"]=="unavailable"
  end
  test "fresh canonical revalidation dispatches same remote query ID and original deadline" do
    {s,c,p,scope}=fixture();s=cache(s,p,scope,true)
    assert {{:dispatch,task},next}=prepare(s,c)
    assert task.id=="query-pinned" and task.peer==p
    assert task.query["deadline_at"]==value(s)["deadline_at"]
    assert task.query["question"]==value(s)["question"]
    assert row(next)["owner_server_id"]==p["server_id"]
  end
  test "new result without dispatched pin remains terminal unavailable" do
    {s,c,_,_}=fixture()
    s=update_in(s,[:source_queries,"query-pinned",:value,"results"],fn [r]->[%{r|"owner_server_id"=>nil,"owner_project_id"=>nil}] end)
    assert {:idle,next}=prepare(s,c)
    assert value(next)["status"]=="partial" and row(next)["status"]=="unavailable"
  end
  test "explicit peer removal remains terminal" do
    {s,c,_,_}=fixture();c=put_in(c,["federation","peers"],[]);:persistent_term.put({ADHD.Config,:config},c)
    assert {:idle,next}=prepare(Directory.reconcile(s,c),c)
    assert value(next)["status"]=="partial" and row(next)["status"]=="unavailable"
  end
  test "explicit removed owner terminates even while unrelated peer metadata is pending" do
    {s,c,p,_}=fixture()
    other=%{p|"server_id"=>String.duplicate("d",32),"project_id"=>"unrelated"}
    c=put_in(c,["federation","peers"],[other]);:persistent_term.put({ADHD.Config,:config},c)
    assert {:idle,next}=prepare(Directory.reconcile(s,c),c)
    assert value(next)["status"]=="partial" and row(next)["status"]=="unavailable"
  end
  test "explicit identity conflict remains terminal" do
    {s,c,p,scope}=fixture();s=cache(s,p,scope,true,"identity_conflict")
    assert {:idle,next}=prepare(s,c)
    assert value(next)["status"]=="partial" and row(next)["status"]=="unavailable"
    assert hd(value(next)["coverage"])["status"]=="identity_conflict"
  end
  test "fresh canonical revocation remains terminal" do
    {s,c,p,scope}=fixture();s=cache(s,p,scope,false)
    assert {:idle,next}=prepare(s,c)
    assert value(next)["status"]=="partial" and row(next)["status"]=="revoked"
  end
  test "original elapsed deadline terminates rather than extending wait" do
    {s,c,_,_}=fixture();deadline=Domain.at(Domain.ms()-1);s=put_in(s,[:source_queries,"query-pinned",:value,"deadline_at"],deadline)
    assert {:idle,next}=prepare(s,c)
    assert value(next)["status"]=="partial" and row(next)["status"]=="unavailable"
    assert value(next)["deadline_at"]==deadline
  end
  test "current actor revocation still terminates pinned accepted query" do
    {s,c,_,_}=fixture();c=Map.put(c,"agents",%{});:persistent_term.put({ADHD.Config,:config},c)
    assert {:idle,next}=prepare(s,c)
    assert value(next)["status"]=="partial" and row(next)["status"]=="unavailable"
  end
end
result=ExUnit.run()
value=%{"schema"=>"adhd/source-query-pin-component-review@1","passed"=>result.failures==0,"checks"=>result.total,"failures"=>result.failures,"artifact_sha256"=>ADHD.RecoveryFiles.sha(File.read!(artifact)),"harness_sha256"=>ADHD.RecoveryFiles.sha(File.read!(__ENV__.file)),"scope"=>"Isolated actual frozen SourceQueries.prepare and Directory resolution; no HTTP, private reconcile callback, restart, recovery, container or lifecycle-admission claim"}
File.write!(report,JSON.encode!(value))
if result.failures != 0,do: System.halt(1)
