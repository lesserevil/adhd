[source,work]=System.argv()
Code.compiler_options(no_warn_undefined: :all)
for name<-~w(domain directory project_backup storage_registry projects config allocator store storage),do: Code.require_file(Path.join(source,name<>".exs"))
File.mkdir_p!(work);File.chmod!(work,0o700)
ExUnit.start()
Application.put_env(:handoff_test,:work,Path.expand(work))
defmodule RecoveryHandoffTest do
  use ExUnit.Case
  defp state do
    %{schema: 4,project: "red",server_id: String.duplicate("a",32),aliases: ["red"],seq: 4,storage_generation: 7,project_epoch: String.duplicate("b",32),allocation_epoch: String.duplicate("c",32),allocation_counter: 11,route_generation: 2}
  end
  test "Store keeps actual shared DETS after loader exits and activation avoids heavyweight loaders" do
    root=Path.join(Application.fetch_env!(:handoff_test,:work),Integer.to_string(System.unique_integer([:positive])))
    File.mkdir!(root);File.chmod!(root,0o700);path=Path.join(root,"state.dets");s=state();uid=File.stat!(root).uid
    {:ok,tab}=:dets.open_file(:recovery_handoff_test,[file: String.to_charlist(path),type: :set,auto_save: :infinity,repair: false])
    File.chmod!(path,0o600);ADHD.Storage.persist(tab,path,s);:dets.close(tab)
    cert=ADHD.RecoveryFiles.sha(File.read!(path))
    stage=%{"target"=>path,"project_id"=>"red","server_id"=>s.server_id,"generation"=>s.storage_generation,"sequence"=>s.seq,"route_generation"=>s.route_generation,"project_epoch"=>s.project_epoch,"allocation_epoch"=>s.allocation_epoch,"closed_checkpoint"=>%{"sha256"=>cert}}
    parent=self()
    {loader,monitor}=spawn_monitor(fn->
      {:ok,t}=:dets.open_file(:recovery_handoff_test,[file: String.to_charlist(path),type: :set,auto_save: :infinity,repair: false]);:dets.sync(t)
      assert :dets.lookup(t,:state)==[{:state,s}]
      files=%{"checkpoint"=>ADHD.RecoveryFiles.fingerprint(path,uid),"snapshot"=>ADHD.RecoveryFiles.fingerprint(path<>".snapshot",uid)}
      p=%{state: s,tab: t,path: path,digest: ADHD.RecoveryFiles.sha(ADHD.Storage.bytes(s)),checkpoint_sha: cert,files: files,uid: uid}
      send(parent,{:preloaded,p})
      receive do :release->:dets.close(t) end
    end)
    assert_receive {:preloaded,p},5000
    {:ok,writer}=GenServer.start(ADHD.Store,{:preloaded,%{"project_id"=>"red"},"owned-token",stage,p})
    try do
      send(loader,:release);assert_receive {:DOWN,^monitor,:process,^loader,:normal},5000
      assert :dets.lookup(p.tab,:state)==[{:state,s}]
      :erlang.trace(writer,true,[:call,{:tracer,self()}])
      for spec<-[{ADHD.Storage,:open,:_},{ADHD.Storage,:read_snapshot,:_},{ADHD.Store,:upgrade,:_}],do: :erlang.trace_pattern(spec,true,[:local])
      assert :ok==GenServer.call(writer,{:activate_restore,"owned-token",stage})
      assert {:ok,proof}=GenServer.call(writer,:state_proof)
      assert proof["state_sha256"]==p.digest and proof["sequence"]==4
      refute_receive {:trace,^writer,:call,_},100
      File.write!(path<>".snapshot",File.read!(path<>".snapshot")<>"tamper")
      assert {:error,"RECOVERY_REQUIRED"}==GenServer.call(writer,{:activate_restore,"owned-token",stage})
      assert :dets.lookup(p.tab,:state)==[{:state,s}]
    after
      for spec<-[{ADHD.Storage,:open,:_},{ADHD.Storage,:read_snapshot,:_},{ADHD.Store,:upgrade,:_}],do: :erlang.trace_pattern(spec,false,[:local])
      if Process.alive?(writer),do: GenServer.stop(writer)
      if Process.alive?(loader),do: Process.exit(loader,:kill)
      File.rm_rf!(root)
    end
    assert :dets.info(:recovery_handoff_test)==:undefined
  end
  test "existing frozen writer swaps to a preopened generation without retaining its old table" do
    root=Path.join(Application.fetch_env!(:handoff_test,:work),"swap-"<>Integer.to_string(System.unique_integer([:positive])))
    File.mkdir!(root);File.chmod!(root,0o700);uid=File.stat!(root).uid
    build=fn name,path,s->
      {:ok,t}=:dets.open_file(name,[file: String.to_charlist(path),type: :set,auto_save: :infinity,repair: false])
      File.chmod!(path,0o600);ADHD.Storage.persist(t,path,s)
      cert=ADHD.RecoveryFiles.sha(File.read!(path))
      files=%{"checkpoint"=>ADHD.RecoveryFiles.fingerprint(path,uid),"snapshot"=>ADHD.RecoveryFiles.fingerprint(path<>".snapshot",uid)}
      stage=%{"target"=>path,"project_id"=>"red","server_id"=>s.server_id,"generation"=>s.storage_generation,"sequence"=>s.seq,"route_generation"=>s.route_generation,"project_epoch"=>s.project_epoch,"allocation_epoch"=>s.allocation_epoch,"closed_checkpoint"=>%{"sha256"=>cert}}
      p=%{state: s,tab: t,path: path,digest: ADHD.RecoveryFiles.sha(ADHD.Storage.bytes(s)),checkpoint_sha: cert,files: files,uid: uid}
      {stage,p}
    end
    {old,p0}=build.(:handoff_old,Path.join(root,"old.dets"),state())
    {:ok,writer}=GenServer.start(ADHD.Store,{:preloaded,%{"project_id"=>"red"},"decision-token",old,p0})
    :dets.close(p0.tab)
    next=%{state()|project_epoch: String.duplicate("d",32),allocation_epoch: String.duplicate("e",32),allocation_counter: 0,route_generation: 3,storage_generation: 8}
    {stage,p}=build.(:handoff_new,Path.join(root,"new.dets"),next)
    try do
      :erlang.trace(writer,true,[:call,{:tracer,self()}])
      for spec<-[{ADHD.Storage,:open,:_},{ADHD.Storage,:read_snapshot,:_},{ADHD.Store,:upgrade,:_}],do: :erlang.trace_pattern(spec,true,[:local])
      assert :ok==GenServer.call(writer,{:adopt_restore,"decision-token",stage,p})
      assert :dets.info(:handoff_old)==:undefined
      :dets.close(p.tab)
      assert :dets.lookup(:handoff_new,:state)==[{:state,next}]
      assert :ok==GenServer.call(writer,{:activate_restore,"decision-token",stage})
      assert {:ok,proof}=GenServer.call(writer,:state_proof)
      assert proof["project_epoch"]==next.project_epoch and proof["state_sha256"]==p.digest
      refute_receive {:trace,^writer,:call,_},100
    after
      for spec<-[{ADHD.Storage,:open,:_},{ADHD.Storage,:read_snapshot,:_},{ADHD.Store,:upgrade,:_}],do: :erlang.trace_pattern(spec,false,[:local])
      if Process.alive?(writer),do: GenServer.stop(writer)
      if :dets.info(:handoff_new)!=:undefined,do: :dets.close(:handoff_new)
      File.rm_rf!(root)
    end
  end

end
