[source] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for name <- ~w(domain directory project_backup storage storage_registry),
  do: Code.require_file(Path.join(source,name<>".exs"))
ExUnit.start()
defmodule RecoveryRegistryTest do
  use ExUnit.Case
  alias ADHD.StorageRegistry,as: R
  defp epoch(n),do: String.duplicate(n,32)
  defp entry do
    %{"server_id"=>epoch("a"),"project_id"=>"red","aliases"=>[],"initialized"=>true,"generation"=>3,"project_epoch"=>epoch("b"),"allocation_epoch"=>epoch("c"),"topic_generation"=>epoch("b"),"storage_anchor"=>"/private/red/state.dets","state_sha256"=>String.duplicate("0",64),"sequence"=>5,"storage_generation"=>8,"availability"=>"ready"}
  end
  defp registry do
    R.seal(%{"schema"=>1,"config_file"=>"/private/hub.json","server_id"=>epoch("a"),"projects"=>%{"red"=>entry()},"reserved_epochs"=>[epoch("b"),epoch("c")]})
  end
  test "every selected namespace is reserved and active project namespaces cannot collide" do
    assert :ok==R.validate(registry(),"/private/hub.json",epoch("a"))
    for bad<-[put_in(registry(),["reserved_epochs"],[epoch("b")]),put_in(registry(),["projects","red","allocation_epoch"],epoch("b")),put_in(registry(),["projects","red","topic_generation"],epoch("d"))] do
      assert catch_throw(R.validate(R.seal(bad),"/private/hub.json",epoch("a")))=={:domain,"INVALID_PARAMS"}
    end
  end
  test "same allocation incarnation keeps its counter, new admitted incarnation starts zero" do
    s=%{schema: 4,allocation_epoch: epoch("c"),allocation_counter: 97}
    assert R.headers(s,entry()).allocation_counter==97
    changed=Map.put(entry(),"allocation_epoch",epoch("d"))
    assert R.headers(s,changed).allocation_counter==0
    assert R.headers(%{schema: 3},entry()).allocation_counter==0
  end
  test "selected header rejects older watermarks and same-watermark different bytes" do
    s=%{schema: 4,server_id: epoch("a"),project: "red",route_generation: 3,project_epoch: epoch("b"),allocation_epoch: epoch("c"),allocation_counter: 9,seq: 5,storage_generation: 8}
    e=Map.put(entry(),"state_sha256",ADHD.RecoveryFiles.sha(ADHD.Storage.bytes(s)))
    assert :ok==R.check_header(s,e)
    for bad<-[%{s|seq: 4},%{s|storage_generation: 7},%{s|allocation_counter: 8},%{s|project_epoch: epoch("d")}] do
      assert catch_throw(R.check_header(bad,e))=={:domain,"INVALID_PARAMS"}
    end
    assert :ok==R.check_header(%{s|storage_generation: 9,allocation_counter: 10},e)
  end
end
