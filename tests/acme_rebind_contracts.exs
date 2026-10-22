# Pure isolated native transaction capsule: no Config/TLS process, guardian,
# listener, client, DETS or external service. The guardian lock seam is explicit.
[source, support, output] = System.argv()
output=Path.expand(output)
Code.compile_file(Path.join(support,"domain.exs"))
directory = File.read!(Path.join(support,"directory.exs"))
{prefix,_} = :binary.match(directory,"  def scope(")
Code.compile_string(binary_part(directory,0,prefix)<>"end\n")
files = File.read!(Path.join(support,"project_backup.exs")) |> String.split("\ndefmodule ADHD.RecoveryTerm",parts: 2) |> hd()
Code.compile_string(files)
defmodule ADHD.ACMEClient do
  def lock_available?(_),do: Process.get(:guard_available,true)
end
defmodule ADHD.Storage do
  def atomic_private(path,bytes) do
    :ok=File.write(path<>".new",bytes);:ok=File.chmod(path<>".new",0o600)
    :ok=File.rename(path<>".new",path)
  end
end
defmodule ADHD.ProjectRestore do
  def validate_metadata(_,_,_),do: :ok
end
defmodule ADHD.Projects do
  def ids(_),do: []
end
input=File.read!(source)
capsule=String.replace(input,"defp validate_decision(","def validate_decision(")
Code.compile_string(capsule,source)
base=Path.join(Path.dirname(output),"rebind-pure-"<>ADHD.Domain.opaque())
File.mkdir_p!(base);File.chmod!(base,0o700)
path=Path.join(base,"config.json");old="/old-owned/config.json"
uid=File.stat!(base).uid
limits=%{"max_records"=>1000,"max_backup_bytes"=>1048576,"deadline_ms"=>System.monotonic_time(:millisecond)+30000}
rows=:ets.new(:rows,[:set])
check=fn name,f->true=f.();:ets.insert(rows,{name,%{"case"=>name,"passed"=>true}}) end
reject=fn f->try do f.();false rescue _->true catch _,_->true end end
put=fn p,v->File.write!(p,JSON.encode!(v));File.chmod!(p,0o600) end
try do
  {absent,[]}=ADHD.ACMERebind.capture(path,old,uid,limits)
  check.("legacy-no-managed-state",fn-> absent==%{"initialized"=>false} end)
  root=Path.join(base,"acme")
  File.mkdir!(root);File.chmod!(root,0o700)
  check.("root-without-witness-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  for n<-~w(accounts attempts generations),do: (File.mkdir!(Path.join(root,n));File.chmod!(Path.join(root,n),0o700))
  owner=String.duplicate("A",32)
  w=%{"config_path"=>Base.encode16(:crypto.hash(:sha256,:erlang.term_to_binary(Path.expand(old))),case: :lower),"owner"=>owner,"phase"=>"ready"}
  wp=path<>".acme-owner.json";op=Path.join(root,"owner.json")
  check.("actual-domain-producer-path-digest",fn->w["config_path"]==ADHD.Domain.digest(old) and w["config_path"]!=ADHD.Directory.digest(old) end)
  producer=Code.string_to_quoted!(File.read!(Path.join(support,"tls.exs")))
  {_ast,bindings}=Macro.prewalk(producer,[],fn
    {:=,_,[{:binding,_,_},{{:.,_,[{:__aliases__,_,[:D]},:digest]},_,[{{:.,_,[{:__aliases__,_,[:Path]},:expand]},_,[{{:.,_,[{:s,_,_},:path]},_,[]}]}]}]}=node,acc->{node,[true|acc]}
    node,acc->{node,acc}
  end)
  check.("tls-initializer-uses-same-domain-expression",fn->bindings==[true] and String.contains?(File.read!(Path.join(support,"tls.exs")),"alias ADHD.Domain, as: D") end)
  put.(wp,Map.put(w,"config_path",ADHD.Directory.digest(old)));put.(op,Map.delete(w,"phase"));put.(Path.join(root,"state.json"),%{})
  check.("json-digest-impostor-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  put.(wp,w);put.(op,Map.delete(w,"phase"));put.(Path.join(root,"state.json"),%{"active"=>"unchanged"})
  key=Path.join(root,"accounts/key.pem");put.(key,"private-fixture-only")
  cert=Path.join(root,"generations/cert.pem");put.(cert,"certificate-fixture-only")
  {proof,replacements}=ADHD.ACMERebind.capture(path,old,uid,limits)
  retained=Map.new([key,cert,Path.join(root,"state.json")],&{&1,{File.read!(&1),File.stat!(&1)}})
  check.("exact-owner-two-targets",fn->Enum.map(replacements,&elem(&1,1))==[wp,op] end)
  check.("old-binding-and-opaque-owner-proved",fn->proof["old_config_path"]==ADHD.Domain.digest(old) and proof["owner"]==owner end)
  check.("predecision-valid",fn->ADHD.ACMERebind.verify(proof,path,uid,false)==:ok end)
  check.("wrong-old-config-binding-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,"/foreign/config.json",uid,limits) end) end)
  put.(Path.join(root,"client.lock"),"")
  Process.put(:guard_available,false)
  check.("live-guardian-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  Process.delete(:guard_available)
  File.rm!(Path.join(root,"client.lock"))
  put.(wp,Map.put(w,"owner",String.duplicate("B",32)))
  check.("foreign-owner-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  put.(wp,Map.put(w,"phase","initializing"))
  check.("incomplete-initialization-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  put.(wp,w)
  File.rename!(Path.join(root,"state.json"),Path.join(root,"state.keep"))
  check.("missing-initialized-state-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  File.rename!(Path.join(root,"state.keep"),Path.join(root,"state.json"))
  File.chmod!(key,0o644)
  check.("public-private-key-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  File.chmod!(key,0o600)
  File.ln_s!(key,Path.join(root,"accounts/alias"))
  check.("symlink-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  File.rm!(Path.join(root,"accounts/alias"))
  File.ln!(key,Path.join(root,"accounts/alias"))
  check.("hardlink-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  File.rm!(Path.join(root,"accounts/alias"))
  check.("record-budget-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,Map.put(limits,"max_records",1)) end) end)
  check.("byte-budget-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,Map.put(limits,"max_backup_bytes",1)) end) end)
  check.("deadline-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,Map.put(limits,"deadline_ms",System.monotonic_time(:millisecond)-1)) end) end)
  File.write!(cert,"changed")
  check.("changed-retained-content-refused",fn->reject.(fn->ADHD.ACMERebind.verify(proof,path,uid,false) end) end)
  {bytes,_}=retained[cert];File.write!(cert,bytes)
  put.(Path.join(root,"accounts/late-file"),"late")
  check.("postproof-extra-file-refused",fn->reject.(fn->ADHD.ACMERebind.verify(proof,path,uid,false) end) end)
  File.rm!(Path.join(root,"accounts/late-file"))
  # Exercise real shared transaction recovery with all five staged metadata
  # replacements, interrupt after every prefix, then finish the retained decision. Collaborator
  # journal validation/write seams are stubs; recovery/allowlist/read guards real.
  server=String.duplicate("a",32);config=%{"server_id"=>server};put.(path,config)
  result=%{"rebound"=>true,"server_id"=>server,"registry_revision"=>1,"projects"=>[]}
  request_hash=ADHD.Directory.digest("request")
  mid=ADHD.Domain.opaque();receipt_key=ADHD.Directory.digest(["offline-owner",mid])
  journal=%{"config_file"=>path,"rebind_receipts"=>%{receipt_key=>%{"digest"=>request_hash,"result"=>result}}}
  for prefix<-0..5 do
    put.(wp,w);put.(op,Map.delete(w,"phase"))
    stage=path<>".rebind-"<>ADHD.Domain.opaque();File.mkdir!(stage);File.chmod!(stage,0o700)
    first=for {name,target}<- [{"registry",path<>".stores"},{"marker",path<>".stores.marker"},{"journal",path<>".recovery"}] do
      oldvalue=%{"previous"=>name};put.(target,oldvalue)
      newvalue=if name=="journal",do: journal,else: %{"current"=>name}
      {name,target,JSON.encode!(oldvalue),newvalue}
    end
    rs=for {name,target,oldbytes,newvalue}<-first++replacements do
      stagepath=Path.join(stage,name<>".json");bytes=JSON.encode!(newvalue);File.write!(stagepath,bytes);File.chmod!(stagepath,0o600)
      %{"target"=>target,"stage"=>stagepath,"old_sha256"=>ADHD.RecoveryFiles.sha(oldbytes),"new_sha256"=>ADHD.RecoveryFiles.sha(bytes),"bytes"=>byte_size(bytes)}
    end
    d=%{"schema"=>1,"kind"=>"metadata_rebind","config_file"=>path,"server_id"=>server,"request_sha256"=>request_hash,"message_id"=>mid,"stage_dir"=>stage,"config_sha256"=>ADHD.RecoveryFiles.sha(JSON.encode!(config)),"config_journal_sha256"=>nil,"maximum_bytes"=>1048576,"stores"=>[],"replacements"=>rs,"result"=>result,"acme"=>proof}
    d=Map.put(d,"integrity_sha256",ADHD.Directory.digest(d))
    legacy=Map.drop(d,["acme","integrity_sha256"]) |> Map.put("replacements",Enum.take(rs,3))
    legacy=Map.put(legacy,"integrity_sha256",ADHD.Directory.digest(legacy))
    check.("legacy-three-target-decision-#{prefix}",fn->ADHD.StorageRebind.validate_decision(legacy,path)==:ok end)
    put.(path<>".transaction",d)
    for r<-Enum.take(rs,prefix),do: ADHD.Storage.atomic_private(r["target"],File.read!(r["stage"]))
    check.("recover-prefix-#{prefix}",fn-> ADHD.StorageRebind.recover(path,d)==:ok and not File.exists?(path<>".transaction") and not File.exists?(stage) end)
    check.("recovered-ready-binding-#{prefix}",fn->ADHD.ACMERebind.verify(proof,path,uid,true)==:ok end)
    forged=put_in(d["replacements"],List.update_at(rs,4,&Map.put(&1,"target",Path.join(root,"state.json"))));forged=Map.put(forged,"integrity_sha256",ADHD.Directory.digest(Map.delete(forged,"integrity_sha256")))
    check.("closed-target-allowlist-#{prefix}",fn->reject.(fn->ADHD.StorageRebind.validate_decision(forged,path) end) end)
  end
  check.("retained-key-cert-state-bytes-mode-inode-unchanged",fn->Enum.all?(retained,fn {p,{bytes,s}}->a=File.stat!(p);File.read!(p)==bytes and {a.inode,a.mode,a.uid}=={s.inode,s.mode,s.uid} end) end)
  put.(wp,w);put.(op,Map.delete(w,"phase"))
  File.rm!(wp)
  check.("missing-witness-with-state-refused",fn->reject.(fn->ADHD.ACMERebind.capture(path,old,uid,limits) end) end)
  check.("absent-proof-detects-appearing-root",fn->reject.(fn->ADHD.ACMERebind.verify(absent,path,uid,true) end) end)
  reports=:ets.tab2list(rows)|>Enum.map(&elem(&1,1))|>Enum.sort_by(& &1["case"])
  File.write!(output,JSON.encode!(%{"passed"=>true,"cases"=>reports,"source_sha256"=>ADHD.RecoveryFiles.sha(input),"shared_source_edited"=>false,"guardian_probe_stubbed"=>true,"journal_validation_stubbed"=>true,"application_started"=>false}))
after
  File.rm_rf!(base)
end
