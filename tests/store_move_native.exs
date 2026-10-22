# Independent local-writer rejection and recovery invariants against a frozen
# diagnostic artifact. Public SDK persistence tests remain separate.
[artifact,root]=System.argv()
[modules,_]=String.split(File.read!(artifact),"\nunless Code.ensure_loaded?(ADHD.CLI)",parts: 2)
Code.compile_string(modules,artifact)
{:ok,_}=Application.ensure_all_started(:inets)
{:ok,_}=Application.ensure_all_started(:ssl)
if File.exists?(root),do: raise("Fixture directory must be fresh")
File.mkdir_p!(root)
old=ADHD.Config.validate(%{"server_id"=>String.duplicate("a",32),"project_id"=>"red","projects"=>[%{"id"=>"red","name"=>"Red"},%{"id"=>"blue","name"=>"Blue"}],"agents"=>%{},"admin_token"=>String.duplicate("k",36),"matcher"=>nil,"eventing"=>%{"enabled"=>false},"store_path"=>Path.join(root,"old.dets")},root)
:persistent_term.put({ADHD.Config,:config},old)
{:ok,_}=ADHD.Store.start_link(old)
ADHD.Projects.prepare(old,old)
ids=ADHD.Projects.ids(old)
state=fn id->ADHD.Scope.with_project(id,fn->ADHD.Store.snapshot() |> ADHD.Store.unwrap() end) end
before=Map.new(ids,&{&1,state.(&1)})
new=Map.put(old,"store_path",Path.join(root,"new.dets"))
check=fn value->if not value,do: raise("Relocation invariant failed") end
passed=[]
try do
  moves=ADHD.Store.prepare_moves(new,old)
  owner=self()
  for id<-ids do
    result=ADHD.Scope.with_project(id,fn->ADHD.Store.call(fn s->send(owner,:unexpected_accept);{:ok,s} end) end)
    check.(result=={:error,"CONFIG_APPLY_IN_PROGRESS"})
  end
  receive do :unexpected_accept->raise("Frozen writer executed a rejected transaction") after 10->:ok end
  ADHD.Store.abort_moves(moves)
  for id<-ids,do: check.(state.(id)==before[id])
  passed=["all-frozen-writers-reject-without-executing-callback-and-abort-resumes-identical-state"|passed]
  moves=ADHD.Store.prepare_moves(new,old)
  entries=ADHD.Store.move_decision(moves)
  :ok=ADHD.Store.install_moves(entries)
  :ok=ADHD.Store.activate_moves(moves)
  :persistent_term.put({ADHD.Config,:config},new)
  :ok=ADHD.Store.release_moves(moves)
  for id<-ids do
    after_move=state.(id)
    check.(Map.delete(after_move,:storage_generation)==Map.delete(before[id],:storage_generation))
    check.(after_move.storage_generation==before[id].storage_generation+1)
  end
  passed=["every-activated-writer-retains-complete-state-and-advances-only-storage-generation"|passed]
  for id<-ids do
    ADHD.Scope.with_project(id,fn->ADHD.Store.call(fn s->{:ok,%{s|seq: s.seq+1}} end) |> ADHD.Store.unwrap() end)
  end
  newer=Map.new(ids,&{&1,state.(&1)})
  :ok=ADHD.Store.install_moves(entries)
  for id<-ids,do: check.(state.(id)==newer[id])
  for e<-entries,do: check.(ADHD.Store.validate_move_target(e)==newer[e["project_id"]])
  passed=["idempotent-decision-recovery-preserves-newer-postactivation-writes"|passed]
  e=hd(entries)
  path=ADHD.Storage.snapshot_path(e["target"])
  saved=File.read!(path)
  File.write!(path,"damaged snapshot")
  refused=try do ADHD.Store.install_moves(entries);false rescue _->true catch _,_->true end
  check.(refused)
  check.(File.read!(path)=="damaged snapshot")
  File.write!(path,saved)
  :ok=ADHD.Store.install_moves(entries)
  passed=["damaged-installed-target-fails-closed-without-overwriting-from-older-stage"|passed]
  IO.puts(JSON.encode!(%{"suite"=>"adhd/store-move-local-invariants@1","passed"=>true,"checks"=>Enum.map(Enum.reverse(passed),&%{"name"=>&1,"passed"=>true})}))
after
  for id<-ids do
    pid=if id==old["project_id"],do: Process.whereis(ADHD.Store),else: :global.whereis_name({ADHD.Store,id})
    if is_pid(pid) and Process.alive?(pid),do: GenServer.stop(pid)
  end
end
