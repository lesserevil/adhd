# Read one owned stopped-runtime metadata set. Mutations below stay in memory;
# no accepted source bytes, Store or writable DETS are opened.
[source,config] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for name<-~w(domain directory project_backup storage_registry project_restore),
  do: Code.require_file(Path.join(source,name<>".exs"))
ExUnit.start()
Application.put_env(:recovery_journal_test,:input,{Path.expand(config),ADHD.JSON.decode!(File.read!(config)),ADHD.JSON.decode!(File.read!(config<>".recovery"))})
defmodule RecoveryJournalTest do
  use ExUnit.Case
  alias ADHD.ProjectRestore,as: R
  defp input,do: Application.fetch_env!(:recovery_journal_test,:input)
  defp seal(j),do: Map.put(j,"integrity_sha256",ADHD.Directory.digest(Map.delete(j,"integrity_sha256")))
  test "actual stopped owner journal preserves all accepted receipts and plans" do
    {path,c,j}=input()
    assert map_size(j["operations"])>0
    assert :ok==R.validate_metadata(j,path,c)
  end
  test "valid checksum cannot authorize broken receipt or missing job graph" do
    {path,c,j}=input();{key,receipt}=Enum.at(j["receipts"],0);id=receipt["receipt"]["operation_id"]
    for broken<-[put_in(j,["receipts",key,"digest"],String.duplicate("0",64)),update_in(j,["jobs"],&Map.delete(&1,id)),put_in(j,["operations",id,"project_id"],"foreign-project")] do
      assert catch_throw(R.validate_metadata(seal(broken),path,c))=={:domain,"INVALID_PARAMS"}
    end
  end
  test "plan namespaces and digest remain linked to durable reservation history" do
    {path,c,j}=input();{id,op}=Enum.find(j["operations"],fn {_,o}->is_map(o["plan"]) end)
    epoch=op["plan"]["selected"]["allocation_epoch"]
    missing=update_in(j,["reserved_epochs"],&List.delete(&1,epoch))
    assert catch_throw(R.validate_metadata(seal(missing),path,c))=={:domain,"INVALID_PARAMS"}
    changed=put_in(j,["operations",id,"plan","selected","topic"],"unreviewed-topic")
    assert catch_throw(R.validate_metadata(seal(changed),path,c))=={:domain,"INVALID_PARAMS"}
  end
end
