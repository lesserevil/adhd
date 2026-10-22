# Focused isolated component checks over the exact frozen application modules.
[artifact, work, report] = System.argv()
[prefix | _] = String.split(File.read!(artifact), "\nunless Code.ensure_loaded?(ADHD.CLI) do", parts: 2)
Code.compile_string(prefix, artifact)
Application.ensure_all_started(:inets)
Application.ensure_all_started(:ssl)
File.mkdir_p!(work)
File.chmod!(work, 0o700)
Application.put_env(:retirement_review, :work, Path.expand(work))
ExUnit.start(autorun: false)

defmodule RetirementReview do
  use ExUnit.Case, async: false
  alias ADHD.{Scope, Resources, StorageRegistry, Storage, RecoveryFiles, Store, Net}
  defp epoch(x), do: String.duplicate(x, 32)
  defp publish(red) do
    entries = for {id, captured, allocation} <- [{"red",red,epoch("c")},{"blue",epoch("b"),epoch("d")}], into: %{} do
      {id,%{"server_id"=>epoch("f"),"project_id"=>id,"aliases"=>[],"initialized"=>true,"generation"=>1,"project_epoch"=>captured,"allocation_epoch"=>allocation,"topic_generation"=>nil,"storage_anchor"=>"/isolated-review/"<>id<>".dets","state_sha256"=>String.duplicate("0",64),"sequence"=>0,"storage_generation"=>0,"availability"=>"ready"}}
    end
    value=%{"schema"=>1,"config_file"=>"/isolated-review/config.json","server_id"=>epoch("f"),"projects"=>entries,"reserved_epochs"=>Enum.uniq([epoch("a"),epoch("b"),epoch("c"),epoch("d"),red])}|>StorageRegistry.seal()
    StorageRegistry.publish("/isolated-review/config.json",value)
  end
  setup do
    :persistent_term.put({ADHD.Config,:config},%{"config_revision"=>1,"project_id"=>"red","store_path"=>"/isolated-review/red.dets","agents"=>%{},"agent_projects"=>%{},"users"=>[],"projects"=>[%{"id"=>"red","name"=>"Red","status"=>"active","settings"=>%{}},%{"id"=>"blue","name"=>"Blue","status"=>"active","settings"=>%{}}],"resources"=>%{"network_concurrency"=>2,"project_network_concurrency"=>1}})
    publish(epoch("a"));Scope.put("red");Scope.begin_work()
    on_exit(fn ->
      if pid=Process.whereis(Resources),do: GenServer.stop(pid)
      for key <- [{ADHD.Config,:config},{StorageRegistry,:current},{Resources,:required}],do: :persistent_term.erase(key)
    end)
    :ok
  end
  defp peer(parent,name) do
    {:ok,listener}=:gen_tcp.listen(0,[:binary,active: false,reuseaddr: true,ip: {127,0,0,1}])
    {:ok,{_,port}}=:inet.sockname(listener)
    pid=spawn_link(fn ->
      {:ok,socket}=:gen_tcp.accept(listener,3000);:gen_tcp.close(listener)
      {:ok,request}=:gen_tcp.recv(socket,0,3000);send(parent,{:request,name,request})
      receive do :reply ->
        result=:gen_tcp.send(socket,"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{\"ok\":true}")
        send(parent,{:sent,name,result})
      after 6000 -> send(parent,{:peer_timeout,name}) end
      :gen_tcp.close(socket)
    end)
    {pid,"http://127.0.0.1:#{port}/held"}
  end
  defp request(parent,name,url,project,captured) do
    spawn_link(fn ->
      Scope.put(project);Scope.put_epoch(captured)
      result=try do {:ok,Net.request(:get,url,nil,[],5000)} catch {:domain,code}->{:rejected,code} end
      send(parent,{:result,name,result})
    end)
  end
  test "retired active HTTP wakes before release while Blue keeps its live slot" do
    :ok=Resources.start()
    {red_peer,red_url}=peer(self(),:red);{blue_peer,blue_url}=peer(self(),:blue)
    request(self(),:red,red_url,"red",epoch("a"));request(self(),:blue,blue_url,"blue",epoch("b"))
    assert_receive {:request,:red,_},2000;assert_receive {:request,:blue,_},2000
    publish(epoch("e"));:ok=Resources.refresh()
    assert_receive {:result,:red,{:rejected,_}},500
    refute_receive {:result,:blue,_},20
    assert Resources.stats()["lanes"]["network"]["projects"]["blue"]["active"]==1
    send(red_peer,:reply);send(blue_peer,:reply)
    assert_receive {:sent,:red,_},1000;assert_receive {:sent,:blue,:ok},1000
    assert_receive {:result,:blue,{:ok,{200,%{"ok"=>true}}}},1000
    assert Resources.stats()["lanes"]["network"]["active"]==0
  end
  test "twenty ordinary real HTTP completions do not inject unmatched failure messages" do
    :ok=Resources.start();parent=self()
    {:ok,listener}=:gen_tcp.listen(0,[:binary,active: false,reuseaddr: true,ip: {127,0,0,1}]);{:ok,{_,port}}=:inet.sockname(listener)
    server=spawn_link(fn ->
      for n<-1..20 do
        {:ok,socket}=:gen_tcp.accept(listener,3000);{:ok,_}=:gen_tcp.recv(socket,0,3000)
        :ok=:gen_tcp.send(socket,"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{\"ok\":true}")
        :gen_tcp.close(socket);send(parent,{:served,n})
      end
      :gen_tcp.close(listener)
    end)
    monitor=Process.monitor(server)
    Scope.put_epoch(epoch("a"))
    for n<-1..20 do
      assert {200,%{"ok"=>true}}==Net.request(:get,"http://127.0.0.1:#{port}/normal",nil,[],1000)
      assert_receive {:served,^n},1000
      refute_receive {:http,_},5
    end
    assert Resources.stats()["lanes"]["network"]["active"]==0
    assert_receive {:DOWN,^monitor,:process,^server,:normal},1000
  end
  test "Eventing keeps beginning independent work after missing writer rejects failure recording" do
    config=ADHD.Config.root() |> Map.delete("projects") |> Map.put("eventing",%{"enabled"=>true,"retry_ms"=>100,"timeout_ms"=>1000,"rest_url"=>"http://127.0.0.1:1"})
    :persistent_term.put({ADHD.Config,:config},config)
    assert Process.whereis(Store)==nil
    worker=ADHD.Eventing.start()
    true=:erlang.trace_pattern({Scope,:begin_work,0},true,[:local])>0
    true=:erlang.trace_pattern({Store,:call,1},true,[:local])>0
    :erlang.trace(worker,true,[:call,{:tracer,self()}])
    try do
      Process.sleep(450)
      assert Process.alive?(worker)
      calls=collect([])
      assert Enum.count(calls,&(&1=={Scope,:begin_work}))>=3
      assert Enum.count(calls,&(&1=={Store,:call}))>=6
    after
      Process.exit(worker,:kill)
      :erlang.trace_pattern({Scope,:begin_work,0},false,[:local]);:erlang.trace_pattern({Store,:call,1},false,[:local])
    end
  end
  defp collect(acc) do
    receive do {:trace,_,:call,{module,fun,_}} -> collect([{module,fun}|acc]) after 20 -> acc end
  end
  defp state(gen \\ 7) do
    %{schema: 4,project: "red",server_id: epoch("f"),aliases: ["red"],seq: gen,storage_generation: gen,project_epoch: epoch("a"),allocation_epoch: epoch("c"),allocation_counter: gen,route_generation: 1}
  end
  defp fixture do
    root=Path.join(Application.fetch_env!(:retirement_review,:work),Integer.to_string(System.unique_integer([:positive])))
    File.mkdir!(root);File.chmod!(root,0o700);stage_dir=Path.join(root,"stage");File.mkdir!(stage_dir);File.chmod!(stage_dir,0o700)
    stage=Path.join(stage_dir,"state.dets");target=Path.join(root,"installed.dets");proof=Storage.write_closed(stage,state())
    e=Map.merge(proof,%{"stage"=>stage,"stage_dir"=>stage_dir,"target"=>target,"route_generation"=>1,"project_epoch"=>epoch("a"),"allocation_epoch"=>epoch("c")})
    {root,e}
  end
  defp uid,do: File.stat!("/proc/self").uid
  test "decision-owned snapshot and checkpoint half-link crashes both resume into nlink1 files" do
    for half<-[:snapshot,:checkpoint] do
      {root,e}=fixture()
      try do
        if half==:snapshot do
          :ok=File.ln(e["stage"]<>".snapshot",e["target"]<>".snapshot")
          assert catch_throw(RecoveryFiles.read(e["stage"]<>".snapshot",1000000,uid()))=={:recovery,"RESTORE_INVALID_BACKUP","path"}
        else
          :ok=File.rename(e["stage"]<>".snapshot",e["target"]<>".snapshot")
          :ok=File.ln(e["stage"],e["target"])
          assert catch_throw(RecoveryFiles.read(e["target"],1000000,uid()))=={:recovery,"RESTORE_INVALID_BACKUP","path"}
        end
        :ok=Store.install_moves([e])
        assert File.stat!(e["target"]).links==1 and File.stat!(e["target"]<>".snapshot").links==1
        assert Storage.read_snapshot(e["target"])==state()
        assert not File.exists?(e["stage_dir"])
      after File.rm_rf!(root) end
    end
  end
  test "third hard link and different-inode target never authorize owned-alias removal" do
    for foreign<-[:third,:different] do
      {root,e}=fixture();extra=Path.join(root,"extra")
      try do
        :ok=File.ln(e["stage"]<>".snapshot",extra)
        if foreign==:third do :ok=File.ln(extra,e["target"]<>".snapshot") else File.write!(e["target"]<>".snapshot",File.read!(extra));File.chmod!(e["target"]<>".snapshot",0o600);:ok=File.ln(e["target"]<>".snapshot",Path.join(root,"foreign-target-alias")) end
        original=File.read!(extra)
        assert catch_throw(Store.install_moves([e]))=={:domain,"INVALID_PARAMS"}
        assert File.exists?(e["stage"]<>".snapshot") and File.read!(extra)==original
      after File.rm_rf!(root) end
    end
  end
  test "a valid advanced target is retained instead of replaced by older stage files" do
    {root,e}=fixture()
    try do
      Storage.write_closed(e["target"],state(8));before=File.read!(e["target"]<>".snapshot")
      :ok=Store.install_moves([e])
      assert File.read!(e["target"]<>".snapshot")==before and Storage.read_snapshot(e["target"])==state(8)
    after File.rm_rf!(root) end
  end
end
result=ExUnit.run()
value=%{"schema"=>"adhd/epoch-retirement-component-review@1","passed"=>result.failures==0,"checks"=>result.total,"failures"=>result.failures,"artifact_sha256"=>ADHD.RecoveryFiles.sha(File.read!(artifact)),"harness_sha256"=>ADHD.RecoveryFiles.sha(File.read!(__ENV__.file)),"scope"=>"Isolated actual HTTP, missing-writer loop and actual staged file/link component checks; no full hub/Kafka/crash/lifecycle claim"}
File.write!(report,JSON.encode!(value))
if result.failures != 0,do: System.halt(1)
