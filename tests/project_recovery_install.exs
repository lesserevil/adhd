[source, work] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for name <- ~w(domain directory project_backup storage_registry projects config allocator store storage), do: Code.require_file(Path.join(source, name <> ".exs"))
File.mkdir_p!(work)
File.chmod!(work, 0o700)
Application.put_env(:install_test, :work, Path.expand(work))
ExUnit.start()
defmodule RecoveryInstallTest do
  use ExUnit.Case
  defp fixture do
    root = Path.join(Application.fetch_env!(:install_test, :work), Integer.to_string(System.unique_integer([:positive])))
    stage_dir = Path.join(root, "stage")
    File.mkdir_p!(stage_dir)
    File.chmod!(root, 0o700)
    File.chmod!(stage_dir, 0o700)
    s = %{schema: 4, project: "red", aliases: ["red"], server_id: String.duplicate("a",32), seq: 3, storage_generation: 9, project_epoch: String.duplicate("b",32), allocation_epoch: String.duplicate("c",32), allocation_counter: 7, route_generation: 2}
    stage = Path.join(stage_dir,"state.dets")
    ADHD.Storage.write_closed(stage,s)
    e = %{"stage"=>stage,"stage_dir"=>stage_dir,"target"=>Path.join(root,"target.dets"),"project_id"=>s.project,"server_id"=>s.server_id,"generation"=>s.storage_generation,"sequence"=>s.seq,"digest"=>ADHD.RecoveryFiles.sha(ADHD.Storage.bytes(s)),"project_epoch"=>s.project_epoch,"allocation_epoch"=>s.allocation_epoch,"route_generation"=>s.route_generation}
    {root,s,e}
  end
  test "snapshot link then interruption completes only owned alias" do
    {root,s,e}=fixture()
    try do
      :ok=File.ln(e["stage"]<>".snapshot",e["target"]<>".snapshot")
      assert File.stat!(e["target"]<>".snapshot").links==2
      assert :ok==ADHD.Store.install_moves([e])
      assert ADHD.Storage.read_snapshot(e["target"])==s
      assert File.stat!(e["target"]<>".snapshot").links==1
      refute File.exists?(e["stage_dir"])
      assert :ok==ADHD.Store.install_moves([e])
    after File.rm_rf!(root) end
  end
  test "checkpoint link interruption completes without opening native input" do
    {root,s,e}=fixture()
    try do
      File.rename!(e["stage"]<>".snapshot",e["target"]<>".snapshot")
      :ok=File.ln(e["stage"],e["target"])
      assert File.stat!(e["target"]).links==2
      assert :ok==ADHD.Store.install_moves([e])
      assert ADHD.Storage.read_snapshot(e["target"])==s
      assert File.stat!(e["target"]).links==1
    after File.rm_rf!(root) end
  end
  test "third alias is rejected and preserves all names" do
    {root,_,e}=fixture()
    try do
      :ok=File.ln(e["stage"]<>".snapshot",e["target"]<>".snapshot")
      :ok=File.ln(e["stage"]<>".snapshot",Path.join(root,"foreign"))
      assert catch_throw(ADHD.Store.install_moves([e]))=={:domain,"INVALID_PARAMS"}
      assert File.stat!(e["target"]<>".snapshot").links==3
      assert File.exists?(e["stage"]<>".snapshot")
    after File.rm_rf!(root) end
  end
  test "unavailable target aliases come only from validated registry" do
    {root,s,e}=fixture()
    try do
      entry=%{"server_id"=>s.server_id,"project_id"=>s.project,"aliases"=>["old-red"],"initialized"=>true,"generation"=>s.route_generation,"project_epoch"=>s.project_epoch,"allocation_epoch"=>s.allocation_epoch,"topic_generation"=>s.project_epoch,"storage_anchor"=>e["target"],"state_sha256"=>e["digest"],"sequence"=>s.seq,"storage_generation"=>s.storage_generation,"availability"=>"recovery_required"}
      path=Path.join(root,"hub.json")
      registry=ADHD.StorageRegistry.seal(%{"schema"=>1,"config_file"=>path,"server_id"=>s.server_id,"projects"=>%{"red"=>entry},"reserved_epochs"=>[s.project_epoch,s.allocation_epoch]})
      :ok=ADHD.StorageRegistry.publish(path,registry)
      File.write!(e["target"]<>".snapshot","corrupt target must not be read for alias discovery")
      assert ADHD.Store.project_aliases(%{"project_id"=>"red"},"red")==["red","old-red"]
    after
      :persistent_term.erase({ADHD.StorageRegistry,:current})
      File.rm_rf!(root)
    end
  end

end
