# Real account file/hash checks in cold recover; explicit init/lock seams only.
[domain, certificate, source, work, output] = System.argv()
Code.compile_file(domain)
Code.compile_file(certificate)
Code.compile_string("""
defmodule ADHD.ACMEClient do
  def lock_available?(_) do
    send(self(), :guardian_probe)
    Process.get(:guardian_closed, true)
  end
end
""")
input=File.read!(source)
ast=Code.string_to_quoted!(input)
{ast,seams}=Macro.postwalk(ast,[],fn
  {:defp,meta,[head,[do: _]]}=node,acc ->
    plain=case head do {:when,_,[p|_]}->p;p->p end
    case plain do
      {:initialize,_,_} -> {{:defp,meta,[head,[do: {:s,[],nil}]]},[:initialize|acc]}
      _ -> {node,acc}
    end
  {{:.,_,[{:__aliases__,_,[:F]},name]},_,[path]}=node,acc when name in [:read,:harden_tree] ->
    observation={:{},[],[:account_io,name,path]}
    {{:__block__,[],[{:send,[],[{:self,[],[]},observation]},node]},[name|acc]}
  node,acc -> {node,acc}
end)
true=Enum.count(seams,&(&1==:initialize))==2
{:defmodule,dm,[name,[do: {:__block__,bm,body}]]}=ast
expose=Code.string_to_quoted!("def account_recover(s), do: recover(s)\ndef account_recover_closed(s), do: recover_closed(s)\ndef account_admit(s), do: admission_state(s)\ndef account_ensure(s), do: ensure_account(s)")
{:__block__,_,wrappers}=expose
Code.compile_quoted({:defmodule,dm,[name,[do: {:__block__,bm,body++wrappers}]]},source)
work=Path.expand(work);File.mkdir!(work);File.chmod!(work,0o700)
:persistent_term.put({ADHD.ACMEFiles,:uid},File.stat!(work).uid)
alias ADHD.ACMEFiles, as: F
c=%{"config_revision"=>1,"tls"=>ADHD.TLS.defaults()}
c=c|>put_in(["tls","enabled"],true)|>put_in(["tls","acme","enabled"],true)|>put_in(["tls","acme","email"],"fixture@example.invalid")|>put_in(["tls","acme","domains"],["hub.example.org"])|>put_in(["tls","acme","accept_terms"],true)
c=ADHD.TLS.normalize(c,work)
owner=String.duplicate("o",32)
id=ADHD.Domain.digest([c["tls"]["acme"]["directory_url"],c["tls"]["acme"]["email"],nil])
# Matches maintained Lego storage_accounts.go: accounts/<issuer>/<id>/<id>.key.
relative="accounts/acme-staging-v02.api.letsencrypt.org/fixture@example.invalid/fixture@example.invalid.key"
bytes="synthetic-account-key-bytes"
digest=Base.encode16(:crypto.hash(:sha256,bytes),case: :lower)
flush=fn flush,acc->receive do message->flush.(flush,[message|acc]) after 0->Enum.reverse(acc) end end
build=fn label,mode->
 root=Path.join(work,label);F.directory(root);F.directory(Path.join(root,"accounts"));account=F.directory(Path.join([root,"accounts",id]))
 key=Path.join(account,relative);File.mkdir_p!(Path.dirname(key))
 File.write!(key,if(mode==:changed_key,do: "changed",else: bytes));File.chmod!(key,0o600)
 case mode do
  :missing_owner->:ok
  :changed_owner->F.write(Path.join(account,"owner.json"),JSON.encode!(%{"owner"=>"foreign","identity"=>id}))
  :malformed_owner->F.write(Path.join(account,"owner.json"),"invalid-json")
  _->F.write(Path.join(account,"owner.json"),JSON.encode!(%{"owner"=>owner,"identity"=>id}))
 end
 metadata=%{"id"=>"fixture@example.invalid","email"=>"fixture@example.invalid","keyType"=>"EC256","server"=>c["tls"]["acme"]["directory_url"],"registration"=>nil}
 metadata_path=Path.join(Path.dirname(key),"account.json")
 case mode do
  :missing_client -> :ok
  :nonobject_client -> F.write(metadata_path,"[]")
  :malformed_client -> F.write(metadata_path,"{invalid")
  :empty_client -> F.write(metadata_path,"{}")
  :invalid_registration -> F.write(metadata_path,JSON.encode!(Map.put(metadata,"registration","invalid")))
  :registered_client -> F.write(metadata_path,JSON.encode!(Map.put(metadata,"registration",%{"status"=>"valid","accountURL"=>"https://fixture.invalid/acme/acct/1","orders"=>"https://fixture.invalid/acme/orders"})))
  _ -> F.write(metadata_path,JSON.encode!(metadata))
 end
 if mode==:missing_key,do: File.rm!(key)
 cert=%{fixture_metadata_placeholder: true}
 s=%{path: Path.join(root,"config.json"),root: root,owner: owner,config: c,certificate: cert,
  trust: nil,job: nil,data: %{"last_attempt_at"=>nil,"next_attempt_at"=>ADHD.Domain.ms()+600000,"last_success_at"=>nil,"last_error"=>nil,"receipts"=>%{},"active"=>nil,"ordering"=>false,"accounts"=>%{id=>%{"keys"=>%{relative=>digest}}}},recovering: false}
 {s,account}
end
reject=fn f->try do f.();false rescue _->true catch _,_->true end end
rows=for {label,mode} <- [{"valid-owner-registration-null",:valid},{"valid-registered-metadata",:registered_client},{"missing-client-metadata",:missing_client},{"nonobject-client-metadata",:nonobject_client},{"malformed-client-metadata",:malformed_client},{"empty-client-metadata",:empty_client},{"invalid-registration-value",:invalid_registration},{"missing-owner",:missing_owner},{"changed-owner",:changed_owner},{"malformed-owner",:malformed_owner},{"missing-key",:missing_key},{"changed-key",:changed_key}] do
 {s,_}=build.(label,mode);flush.(flush,[]);Process.put(:guardian_closed,true)
 observed=ADHD.TLS.account_recover(s);messages=flush.(flush,[])
 error=observed.data["last_error"]
 expected=if mode in [:valid,:registered_client],do: nil,else: "ACME_STORAGE"
 actual=if is_map(error),do: error["code"],else: nil
 manual_rejected=reject.(fn->ADHD.TLS.account_admit(s) end)
 ensure_rejected=reject.(fn->ADHD.TLS.account_ensure(s) end)
 should_reject=expected != nil
 first=Enum.find_index(messages,&(&1==:guardian_probe))
 io=Enum.find_index(messages,&match?({:account_io,_,_},&1))
 %{"case"=>label,"passed"=>manual_rejected==should_reject and ensure_rejected==should_reject and actual==expected and observed.certificate==s.certificate and is_integer(first) and (is_nil(io) or first<io),"expected_error"=>expected,"actual_error"=>actual,"manual_admission_rejected"=>manual_rejected,"preworker_ensure_rejected"=>ensure_rejected,"certificate_placeholder_preserved"=>observed.certificate==s.certificate,"guard_before_account_io"=>is_integer(first) and (is_nil(io) or first<io)}
end
{s,_}=build.("busy-missing-owner",:missing_owner);flush.(flush,[]);Process.put(:guardian_closed,false)
busy=ADHD.TLS.account_recover(s);messages=flush.(flush,[])
row=%{"case"=>"busy-guardian-never-reads-or-hardens-account","passed"=>busy.recovering and busy.data["last_error"]["code"]=="ACME_RECOVERY" and not Enum.any?(messages,&match?({:account_io,_,_},&1)),"account_io_calls"=>Enum.count(messages,&match?({:account_io,_,_},&1))}
Process.put(:guardian_closed,true);closed=ADHD.TLS.account_recover_closed(busy)
row2=%{"case"=>"after-closure-missing-owner-blocks-recovery","passed"=>closed.data["last_error"]["code"]=="ACME_STORAGE" and closed.certificate==s.certificate,"actual_error"=>closed.data["last_error"]["code"],"expected_error"=>"ACME_STORAGE"}
rows=rows++[row,row2]
result=%{"passed"=>Enum.all?(rows,& &1["passed"]),"checks"=>rows,"tls_source_sha256"=>Base.encode16(:crypto.hash(:sha256,input),case: :lower),"scope"=>"Actual cold recover/remember callbacks and private file/hash/fsync; initialized-state and guardian probe seams; certificate metadata placeholder, no actual app or cert recovery", "io_seams"=>Enum.map(seams,&Atom.to_string/1)}
File.write!(output,JSON.encode!(result));IO.puts(JSON.encode!(%{"passed"=>result["passed"],"checks"=>length(rows),"failed"=>Enum.filter(rows,& ! &1["passed"])|>Enum.map(& &1["case"])}))
if not result["passed"],do: System.halt(1)
