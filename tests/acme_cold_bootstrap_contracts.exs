# Callback-only capsule. Five existing I/O function clauses are explicitly
# substituted; trust-file parsing, init/status/admission and activation logic real.
[domain,certificate,source,config_source,good_ca,output]=System.argv()
output=Path.expand(output)
good_ca=Path.expand(good_ca)
Code.compile_file(domain)
Code.compile_file(certificate)
input=File.read!(source)
asts=Code.string_to_quoted!(input)
replacement = fn name ->
  case name do
    :recover -> quote do: Map.merge(s, Process.get(:recovered, %{}))
    :initialize -> quote do: s
    :prepare_listeners -> quote do
      if Process.get(:bind_error,false), do: ADHD.Domain.fail("CONFIG_APPLY_FAILED")
      %{}
    end
    :activate_listeners -> quote do
      %{s | config: c, fingerprint: fingerprint(c,s.trust), listeners: if(c["tls"]["enabled"],do: %{https: :fixture_listener},else: %{})}
    end
  end
end
{asts,seams}=Macro.prewalk(asts,[],fn
  {:defp,meta,[head,[do: _]]}=node,acc ->
    plain=case head do {:when,_,[plain|_]}->plain;plain->plain end
    case plain do
      {name,_,_} when name in [:recover,:initialize,:prepare_listeners,:activate_listeners] ->
        # Parse replacement in the original function's lexical variable context.
        body=replacement.(name)|>Macro.prewalk(fn {name,m,context} when is_atom(name) and is_atom(context)->{name,m,nil};v->v end)
        {{:defp,meta,[head,[do: body]]},[name|acc]}
      _->{node,acc}
    end
  node,acc->{node,acc}
end)
true=Enum.sort(seams)==Enum.sort([:recover,:initialize,:initialize,:prepare_listeners,:activate_listeners])
Code.compile_quoted(asts,source)
config_text=File.read!(config_source)
true=String.contains?(config_text,"if cmd[\"op\"] == \"config_validate\" do\n          ADHD.TLS.validate_inputs(proposed)")
rows=:ets.new(:rows,[:set])
check=fn name,f->true=f.();:ets.insert(rows,{name,%{"case"=>name,"passed"=>true}}) end
reject=fn f->try do f.();false rescue _->true catch _,_->true end end
now=ADHD.Domain.ms()
metadata=%{"sha256"=>String.duplicate("a",64),"serial"=>"1","not_before"=>now-3600000,"not_after"=>now+3600000}
cert=%{metadata: metadata,expires: now+3600000,domains: ["hub.example.org"]}
base=%{"config_revision"=>1,"tls"=>ADHD.TLS.defaults()}
base=put_in(base,["tls","enabled"],true)
base=put_in(base,["tls","acme","enabled"],true)
base=put_in(base,["tls","acme","accept_terms"],true)
base=put_in(base,["tls","acme","email"],"test@example.org")
base=put_in(base,["tls","acme","domains"],["hub.example.org"])
base=ADHD.TLS.normalize(base,Path.dirname(output))
missing=put_in(base,["tls","acme","ca_cert_file"],Path.join(Path.dirname(output),"missing-ca.pem"))
check.("syntax-normalization-does-not-read-missing-ca",fn->ADHD.TLS.normalize(missing,Path.dirname(output))==missing end)
check.("dry-validation-rejects-missing-ca",fn->reject.(fn->ADHD.TLS.validate_inputs(missing) end) end)
good=put_in(base,["tls","acme","ca_cert_file"],good_ca)
check.("dry-validation-valid-ca",fn->ADHD.TLS.validate_inputs(good)==:ok end)
check.("syntax-invalid-host-still-rejected",fn->reject.(fn->ADHD.TLS.normalize(put_in(base,["tls","host"],"invalid-host"),Path.dirname(output)) end) end)
corrupt_path=Path.join(Path.dirname(output),"corrupt-ca.pem");File.write!(corrupt_path,"not a certificate")
corrupt=put_in(base,["tls","acme","ca_cert_file"],corrupt_path)
check.("dry-validation-rejects-corrupt-ca",fn->reject.(fn->ADHD.TLS.validate_inputs(corrupt) end) end)
project=fn s->{:reply,public,_}=ADHD.TLS.handle_call(:status,nil,s);public end
{:ok,empty}=ADHD.TLS.init({Path.join(Path.dirname(output),"config.json"),base})
check.("cold-valid-empty-waiting",fn->p=project.(empty);p["https_state"]=="waiting" and p["acme_state"]=="idle" and p["last_error"]==nil end)
Process.put(:recovered,%{certificate: cert})
{:ok,ready}=ADHD.TLS.init({"/unused/config.json",base})
check.("cold-retained-valid-ready",fn->p=project.(ready);p["https_state"]=="ready" and p["active_domains"]==cert.domains end)
{:ok,badtrust}=ADHD.TLS.init({"/unused/config.json",missing})
check.("missing-ca-retained-cert-stays-ready-error-issuance",fn->p=project.(badtrust);p["https_state"]=="ready" and p["acme_state"]=="error" and p["last_error"]==ADHD.TLS.error("ACME_STORAGE") and badtrust.trust_error end)
{:ok,badcertca}=ADHD.TLS.init({"/unused/config.json",corrupt})
check.("corrupt-ca-private-controller-survives",fn->badcertca.trust_error and project.(badcertca)["https_state"]=="ready" end)
check.("trust-error-force-blocked",fn->{:noreply,s}=ADHD.TLS.handle_info(:force,badtrust);s==badtrust end)
user=%{"role"=>"Admin","id"=>"admin"}
cmd=%{"message_id"=>"fresh","expected_revision"=>1,"confirm"=>true,"op"=>"tls_renew"}
check.("trust-error-new-renew-rejected",fn->match?({:reply,{:error,"CONFIG_APPLY_FAILED"},_},ADHD.TLS.handle_call({:renew,cmd,user},nil,badtrust)) end)
receipt=%{"digest"=>ADHD.Domain.digest(cmd),"result"=>%{"accepted"=>true,"config_revision"=>1}}
replayed=put_in(badtrust.data["receipts"],%{ADHD.Domain.digest([user["id"],cmd["message_id"]])=>receipt})
check.("bootstrap-error-exact-replay-preserved",fn->match?({:reply,{:ok,%{"accepted"=>true}},_},ADHD.TLS.handle_call({:renew,cmd,user},nil,replayed)) end)
check.("bootstrap-replay-still-auth-first",fn->match?({:reply,{:error,"FORBIDDEN"},_},ADHD.TLS.handle_call({:renew,cmd,Map.put(user,"role","Reader")},nil,replayed)) end)
check.("hot-prepare-trust-remains-strict",fn->match?({:reply,{:error,:unavailable},_},ADHD.TLS.handle_call({:prepare,missing},nil,ready)) end)
Process.put(:bind_error,true)
{:ok,badbind}=ADHD.TLS.init({"/unused/config.json",base})
check.("cold-bind-failure-controller-survives",fn->p=project.(badbind);badbind.listener_error and p["https_state"]=="error" and p["acme_state"]=="error" and p["active_domains"]==[] end)
check.("listener-error-force-blocked",fn->{:noreply,s}=ADHD.TLS.handle_info(:force,badbind);s==badbind end)
check.("listener-error-renew-rejected",fn->match?({:reply,{:error,"CONFIG_APPLY_FAILED"},_},ADHD.TLS.handle_call({:renew,cmd,user},nil,badbind)) end)
check.("hot-bind-failure-preserves-original-state",fn->{:reply,{:error,:unavailable},s}=ADHD.TLS.handle_call({:prepare,base},nil,ready);s==ready end)
Process.put(:bind_error,false)
for {name,state,cfg}<- [{"trust",badtrust,good},{"listener",badbind,base}] do
  {:reply,{:ok,p},_}=ADHD.TLS.handle_call({:prepare,cfg},nil,state)
  {:reply,:ok,repaired}=ADHD.TLS.handle_call({:activate,{:ok,p},cfg},nil,state)
  check.("hot-#{name}-repair-clears-only-bootstrap-flags",fn->not repaired.trust_error and not repaired.listener_error and project.(repaired)["https_state"]=="ready" and project.(repaired)["last_error"]==nil end)
end
# Exhaustive nullable status cross-product: real projection/date/live functions,
# no network or actual certificate-handshake claim. Every row is schema-checked
# independently after this process by the Python wrapper.
projections=for enabled<-[false,true],issuance<-[false,true],kind<-[:none,:valid,:expired],job<-[nil,%{}],error<-[nil,ADHD.TLS.error("ACME_NETWORK"),ADHD.TLS.error("ACME_STORAGE")],dates<-[nil,0,now,253402300799000],trust_error<-[false,true],listener_error<-[false,true] do
  c=ready.config |> put_in(["tls","enabled"],enabled) |> put_in(["tls","acme","enabled"],issuance and enabled)
  certificate=case kind do :none->nil;:valid->cert;:expired->%{cert | expires: now-1,metadata: Map.put(cert.metadata,"not_after",now-1)} end
  # An ordering row has a durable attempt timestamp; a backoff row has a
  # durable retry date. Keep all other nullable combinations unchanged.
  attempt=if job != nil and dates==nil,do: now,else: dates
  next_due=if dates==nil and is_map(error) and error["retryable"],do: now+300000,else: dates
  state=%{ready | config: c,certificate: certificate,job: job,trust_error: trust_error,listener_error: listener_error,data: Map.merge(ready.data,%{"last_error"=>error,"last_attempt_at"=>attempt,"last_success_at"=>dates,"next_attempt_at"=>next_due})}
  p=project.(state)
  expected_https=cond do not enabled->"disabled";listener_error->"error";is_map(error) and error["code"]=="ACME_STORAGE" and kind==:none->"error";kind==:none->"waiting";kind==:expired->"expired";true->"ready" end
  expected_acme=cond do not(enabled and issuance)->"disabled";trust_error or listener_error->"error";job != nil->"ordering";is_map(error) and not error["retryable"]->"error";error != nil->"backoff";true->"idle" end
  true=p["https_state"]==expected_https and p["acme_state"]==expected_acme
  true=(p["active_domains"]!=[])==(expected_https=="ready")
  true=(p["next_attempt_at"]==nil)==(not(enabled and issuance) or job != nil or next_due==nil or trust_error or listener_error)
  p
end
check.("https-listener-map-absence-never-ready",fn->project.(%{ready|listeners: %{}})["https_state"]=="error" end)
reports=:ets.tab2list(rows)|>Enum.map(&elem(&1,1))|>Enum.sort_by(& &1["case"])
File.write!(output,JSON.encode!(%{"passed"=>true,"cases"=>reports,"status_projections"=>projections,"projection_count"=>length(projections),"tls_source_sha256"=>Base.encode16(:crypto.hash(:sha256,input),case: :lower),"application_started"=>false,"network_operations"=>0,"test_io_seams"=>Enum.map(seams,&Atom.to_string/1)}))
