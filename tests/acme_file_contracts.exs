# Module-only real filesystem capsule; no listener, issuer, guardian or application.
[domain, source, ca, root, output] = System.argv()
root = Path.expand(root)
Code.compile_file(domain)
text = File.read!(source)
# Observe actual fsync calls without replacing their execution.
text = String.replace(text, ":ok = :file.sync(file)", "send(self(), {:synced, :file.read_file_info(file)}); :ok = :file.sync(file)")
# Deterministic substitutions occur after open and before the original checks.
text = String.replace(text, "D.check(identity(handle_stat(file)) == identity(before))", "if hook = Process.get(:read_hook), do: hook.(); D.check(identity(handle_stat(file)) == identity(before))", global: false)
text = String.replace(text, "D.check(parents_snapshot(path) == parents and target_identity(path) == before)", "if hook = Process.get(:write_hook), do: hook.(); D.check(parents_snapshot(path) == parents and target_identity(path) == before)")
Code.compile_string(text, source)
File.mkdir!(root)
File.chmod!(root, 0o700)
:persistent_term.put({ADHD.ACMEFiles, :uid}, File.stat!(root).uid)
alias ADHD.ACMEFiles, as: F
rows = :ets.new(:checks, [:ordered_set])
check = fn name, f -> true = f.(); :ets.insert(rows, {name, %{"case" => name, "passed" => true}}) end
reject = fn f -> try do f.(); false rescue _ -> true catch _, _ -> true end end
put = fn name, bytes, mode -> path = Path.join(root,name); File.write!(path,bytes); File.chmod!(path,mode); path end
check.("private-write-read", fn -> p=Path.join(root,"state"); :ok=F.write(p,"one"); F.read(p)=="one" and Bitwise.band(File.stat!(p).mode,0o777)==0o600 end)
check.("private-atomic-replace", fn -> p=Path.join(root,"state"); old=File.stat!(p); :ok=F.write(p,"two"); F.read(p)=="two" and File.stat!(p).inode != old.inode end)
check.("empty-private-file", fn -> p=put.("empty","",0o600); F.read(p)=="" end)
check.("private-mode-rejected", fn -> p=put.("public","secret",0o644); reject.(fn->F.read(p) end) and File.read!(p)=="secret" end)
check.("private-size-bounded", fn -> p=put.("large",:binary.copy("a",2097153),0o600); reject.(fn->F.read(p) end) end)
check.("write-size-rejected-preserves-target", fn -> p=Path.join(root,"state"); before=File.stat!(p); reject.(fn->F.write(p,:binary.copy("a",2097153)) end) and File.read!(p)=="two" and File.stat!(p)==before end)
check.("symlink-read-and-write-rejected", fn -> p=Path.join(root,"link"); File.ln_s!("state",p); reject.(fn->F.read(p) end) and reject.(fn->F.write(p,"bad") end) and File.read!(Path.join(root,"state"))=="two" end)
check.("hardlink-read-and-write-rejected", fn -> p=Path.join(root,"hard"); target=put.("hard-target","safe",0o600); File.ln!(target,p); reject.(fn->F.read(p) end) and reject.(fn->F.write(p,"bad") end) and File.read!(target)=="safe" end)
check.("redirected-parent-rejected", fn -> p=Path.join(root,"redirect"); File.ln_s!(root,p); reject.(fn->F.read(Path.join(p,"state")) end) and reject.(fn->F.write(Path.join(p,"new"),"bad") end) end)
check.("public-ca-valid", fn -> F.public_ca(ca)==File.read!(ca) end)
for {name,bytes} <- [{"prefix","junk\n"<>File.read!(ca)},{"suffix",File.read!(ca)<>"junk\n"},{"empty",""},{"oversize",:binary.copy("a",1048577)}] do
  check.("public-ca-"<>name<>"-rejected", fn -> p=put.("ca-"<>name,bytes,0o644); reject.(fn->F.public_ca(p) end) and File.read!(p)==bytes end)
end
check.("public-ca-link-rejected", fn -> p=Path.join(root,"ca-link"); File.ln_s!(ca,p); reject.(fn->F.public_ca(p) end) end)
# Clear previous sync observations; retain fresh directory + parent actual fd stats.
flush = fn f -> receive do {:synced,_}->f.(f) after 0->:ok end end
flush.(flush)
check.("new-directory-syncs-directory-and-parent", fn -> p=Path.join(root,"generation"); F.directory(p); expected=[File.stat!(p).inode,File.stat!(root).inode]; got=for _<-1..2 do receive do {:synced,{:ok,s}}->File.Stat.from_record(s).inode after 0->nil end end; got==expected end)
check.("existing-private-directory",fn-> F.directory(Path.join(root,"generation"))==Path.join(root,"generation") end)
check.("public-directory-refused",fn->p=Path.join(root,"open-dir");File.mkdir!(p);File.chmod!(p,0o755);reject.(fn->F.directory(p) end) and Bitwise.band(File.stat!(p).mode,0o777)==0o755 end)
flush.(flush)
check.("harden-file-before-directory-sync",fn->p=Path.join(root,"client");File.mkdir!(p);k=Path.join(p,"key");File.write!(k,"client-key");File.chmod!(k,0o644);F.harden_tree(p); expected=[File.stat!(k).inode,File.stat!(p).inode]; got=for _<-1..2 do receive do {:synced,{:ok,s}}->File.Stat.from_record(s).inode after 0->nil end end;got==expected and F.read(k)=="client-key" and Bitwise.band(File.stat!(p).mode,0o777)==0o700 end)
check.("harden-refuses-symlink",fn->p=Path.join(root,"bad-tree");File.mkdir!(p);File.ln_s!(Path.join(root,"state"),Path.join(p,"key"));reject.(fn->F.harden_tree(p) end) end)
check.("no-write-temporary-leftovers",fn->Enum.all?(File.ls!(root),fn n->not String.starts_with?(n,"state.") end) end)
check.("read-open-path-drift-rejected",fn->
 p=put.("read-drift","original",0o600); backup=p<>"-original"
 Process.put(:read_hook,fn->Process.delete(:read_hook);File.rename!(p,backup);put.("read-drift","changed!",0o600) end)
 reject.(fn->F.read(p) end) and File.read!(backup)=="original" and File.read!(p)=="changed!"
end)
check.("write-predecision-target-drift-rejected",fn->
 p=put.("write-drift","original",0o600)
 Process.put(:write_hook,fn->Process.delete(:write_hook);File.rm!(p);put.("write-drift","other-owner-state",0o600) end)
 failed=reject.(fn->F.write(p,"replacement") end)
 failed and File.read!(p)=="other-owner-state" and Enum.all?(File.ls!(root),fn n->not String.starts_with?(n,"write-drift.") end)
end)
result=%{"passed"=>true,"checks"=>:ets.tab2list(rows)|>Enum.map(&elem(&1,1)),"scope"=>"module-only real filesystem and actual fsync; no power-cut or malicious same-UID atomic-nofollow proof"}
File.write!(output,JSON.encode!(result))
IO.puts("file checks #{length(result["checks"])} PASS")
