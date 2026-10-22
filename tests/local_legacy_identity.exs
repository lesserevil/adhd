[artifact,checkpoint,configuration,work,report]=System.argv()
[prefix|_]=String.split(File.read!(artifact),"\nunless Code.ensure_loaded?(ADHD.CLI) do",parts: 2)
Code.compile_string(prefix,artifact)
original=File.read!(checkpoint)
{:ok,raw}=ADHD.RecoveryCheckpoint.preflight(original,%{})
true=(raw.schema==2 and not Map.has_key?(raw,:server_id))
config=ADHD.JSON.decode!(File.read!(configuration));project=config["project_id"]
File.mkdir!(work);File.chmod!(work,0o700)
vectors=[{"actual-schema2-checkpoint",raw,config,true},
  {"schema3-missing-identity",Map.put(raw,:schema,3),config,false},
  {"malformed-stored-identity",Map.put(raw,:server_id,false),config,false},
  {"foreign-stored-identity",Map.put(raw,:server_id,String.duplicate("a",32)),Map.put(config,"server_id",String.duplicate("b",32)),false},
  {"foreign-project",Map.put(raw,:project,"foreign"),config,false}]
rows=Enum.map(vectors,fn {name,state,current,expected}->
  path=Path.join(work,name<>".dets")
  source=if name=="actual-schema2-checkpoint" do
    File.write!(path,original);path
  else
    bytes=ADHD.Storage.bytes(state);snapshot=ADHD.Storage.snapshot_path(path)
    File.write!(snapshot,<<"ADHDSTATE",1,(:crypto.hash(:sha256,bytes))::binary,bytes::binary>>);snapshot
  end
  File.chmod!(source,0o664)
  before={File.read!(source),ADHD.RecoveryFiles.identity(File.stat!(source))}
  accepted=try do
    proof=ADHD.LocalLegacy.read(path,project,current["server_id"],ADHD.LocalLegacy.limits(current)) |> ADHD.LocalLegacy.validate(current,project)
    :ok=ADHD.LocalLegacy.verify(proof)
    true=(proof.validated.publications==state.publications)
    true=(is_binary(proof.validated.server_id) and byte_size(proof.validated.server_id)==32)
    true
  rescue _->false catch _,_->false end
  unchanged=before=={File.read!(source),ADHD.RecoveryFiles.identity(File.stat!(source))}
  %{"case"=>name,"passed"=>(accepted==expected and unchanged),"accepted"=>accepted,"input_unchanged"=>unchanged}
end)
result=%{"schema"=>"adhd/local-legacy-identity@1","passed"=>Enum.all?(rows,& &1["passed"]),"artifact_sha256"=>ADHD.RecoveryFiles.sha(File.read!(artifact)),"checkpoint_sha256"=>ADHD.RecoveryFiles.sha(original),"original_unchanged"=>(File.read!(checkpoint)==original),"cases"=>rows,"scope"=>"Actual supported schema2 checkpoint and derived negative headers; full public upgrade/cold restart qualified separately. No native source open or original mutation."}
File.write!(report,JSON.encode!(result));IO.puts(JSON.encode!(result))
if not result["passed"],do: System.halt(1)
