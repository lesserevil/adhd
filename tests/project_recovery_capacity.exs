# Native capacity boundary using actual private empty DETS files. These are not
# project stores or an Admin admission substitute; no HTTP/model/broker runs.
[artifact,work]=System.argv()
Code.compiler_options(no_warn_undefined: :all)
[modules,_main]=String.split(File.read!(artifact),"\ntry do\n  result =",parts: 2)
Code.eval_string(modules,[],file: artifact)
File.mkdir_p!(work);File.chmod!(work,0o700)
ExUnit.start()
Application.put_env(:capacity_test,:work,Path.expand(work))
defmodule RecoveryCapacityTest do
  use ExUnit.Case
  test "256 existing table slots retain one handoff slot and no more" do
    root=Path.join(Application.fetch_env!(:capacity_test,:work),Integer.to_string(System.unique_integer([:positive])))
    File.mkdir!(root);File.chmod!(root,0o700)
    c=ADHD.Config.validate(%{"project_id"=>"red","projects"=>[%{"id"=>"red","name"=>"Red"}],"server_id"=>String.duplicate("a",32),"store_path"=>Path.join(root,"target.dets"),"agents"=>%{},"admin_token"=>String.duplicate("b",32),"matcher"=>nil,"eventing"=>%{"enabled"=>false}},root)
    :persistent_term.put({ADHD.Config,:config},c)
    names=for i<-0..255 do
      name=String.to_atom("adhd_project_store_"<>Integer.to_string(i))
      {:ok,^name}=:dets.open_file(name,[file: String.to_charlist(Path.join(root,"occupied-"<>Integer.to_string(i))),type: :set,auto_save: :infinity])
      name
    end
    extra=String.to_atom("adhd_project_store_256")
    try do
      assert {:ok,^extra,state}=ADHD.Storage.open(c["store_path"],"red")
      assert state.project=="red"
      beyond=Path.join(root,"beyond.dets")
      assert catch_throw(ADHD.Storage.open(beyond,"red"))=={:domain,"RESOURCE_EXHAUSTED"}
      refute File.exists?(beyond)
      :dets.close(hd(names))
      assert {:ok,reused,_}=ADHD.Storage.open(beyond,"red")
      assert reused==hd(names)
    after
      for name<-[extra|names],:dets.info(name)!=:undefined,do: :dets.close(name)
      :persistent_term.erase({ADHD.Config,:config})
      File.rm_rf!(root)
    end
  end
end
