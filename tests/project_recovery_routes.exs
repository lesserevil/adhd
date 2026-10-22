[source, work] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for name <- ~w(domain directory project_backup storage_registry projects config store storage), do: Code.require_file(Path.join(source,name<>".exs"))
File.mkdir_p!(work)
File.chmod!(work,0o700)
Application.put_env(:routes_test,:work,Path.expand(work))
ExUnit.start()
defmodule RecoveryRoutesTest do
  use ExUnit.Case
  alias ADHD.StorageRegistry,as: R
  defp fixture do
    root=Path.join(Application.fetch_env!(:routes_test,:work),Integer.to_string(System.unique_integer([:positive])))
    File.mkdir!(root);File.chmod!(root,0o700)
    path=Path.join(root,"hub.json");server=String.duplicate("a",32)
    c=%{"server_id"=>server,"project_id"=>"red","projects"=>[%{"id"=>"red"},%{"id"=>"unknown"}],"store_path"=>Path.join(root,"store.dets")}
    ADHD.Storage.atomic_private(path,JSON.encode!(c))
    base=%{"server_id"=>server,"project_id"=>"unknown","aliases"=>[],"initialized"=>false,"generation"=>0,"project_epoch"=>nil,"allocation_epoch"=>nil,"topic_generation"=>nil,"storage_anchor"=>Path.join(root,"unknown.dets"),"state_sha256"=>nil,"sequence"=>0,"storage_generation"=>0,"availability"=>"uninitialized"}
    red=Map.merge(base,%{"project_id"=>"red","aliases"=>["old-red"],"initialized"=>true,"generation"=>1,"project_epoch"=>String.duplicate("b",32),"allocation_epoch"=>String.duplicate("c",32),"storage_anchor"=>Path.join(root,"red.dets"),"state_sha256"=>String.duplicate("0",64),"availability"=>"ready"})
    r=R.seal(%{"schema"=>1,"config_file"=>path,"server_id"=>server,"projects"=>%{"red"=>red,"unknown"=>base},"reserved_epochs"=>[red["project_epoch"],red["allocation_epoch"]]})
    R.persist(path,r)
    ADHD.Storage.atomic_private(R.paths(path).marker,JSON.encode!(%{"schema"=>1,"config_file"=>path,"server_id"=>server}))
    {root,path,c,red,base}
  end
  test "unsafe selected files halt only their registered targets and aliases never follow symlinks" do
    {root,path,c,red,unknown}=fixture()
    try do
      protected=Path.join(root,"foreign");File.write!(protected,"untouched")
      File.ln_s!(protected,red["storage_anchor"]<>".snapshot")
      assert :ok==R.load(path,c)
      assert R.entry("red")["availability"]=="recovery_required"
      assert R.entry("unknown")["availability"]=="uninitialized"
      assert ADHD.Store.project_aliases(c,"red")==["red","old-red"]
      File.ln_s!(protected,unknown["storage_anchor"])
      assert :ok==R.load(path,c)
      assert R.entry("unknown")["availability"]=="recovery_required"
      assert ADHD.Store.project_aliases(c,"unknown")==["unknown"]
      assert File.read!(protected)=="untouched"
    after
      :persistent_term.erase({R,:current});File.rm_rf!(root)
    end
  end
  test "uninitialized physical anchor rebases only with exact proof both old files are absent" do
    {root,_path,c,_red,unknown}=fixture()
    try do
      # This unit concerns an uninitialized route only; preserve a complete
      # validated registry with no history or reserved namespace for that target.
      x=R.current();r=R.seal(%{x.registry|"projects"=>%{"unknown"=>unknown},"reserved_epochs"=>[]})
      old=Map.merge(c,%{"project_id"=>"unknown","projects"=>[%{"id"=>"unknown"}]})
      :ok=R.publish(x.path,r)
      next=Map.put(old,"store_path",Path.join(root,"new/store.dets"))
      moved=R.for_config(next,old)["projects"]["unknown"]
      assert moved["storage_anchor"]==Path.expand(next["store_path"])
      assert Map.drop(moved,["storage_anchor"])==Map.drop(unknown,["storage_anchor"])
      File.write!(unknown["storage_anchor"],"unexpected retained bytes")
      assert catch_throw(R.for_config(next,old))=={:domain,"CONFIG_APPLY_FAILED"}
      assert File.read!(unknown["storage_anchor"])=="unexpected retained bytes"
      File.rm!(unknown["storage_anchor"])
      File.mkdir_p!(Path.dirname(moved["storage_anchor"]))
      File.write!(moved["storage_anchor"]<>".snapshot","foreign destination bytes")
      assert catch_throw(R.for_config(next,old))=={:domain,"CONFIG_APPLY_FAILED"}
      assert File.read!(moved["storage_anchor"]<>".snapshot")=="foreign destination bytes"
    after
      :persistent_term.erase({R,:current});File.rm_rf!(root)
    end
  end
end
