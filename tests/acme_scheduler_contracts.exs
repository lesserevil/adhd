# Evaluate the actual scheduler admission predicate before any I/O/job creation.
# This verifies the no-error automatic path without starting an ACME worker.
[source,output]=System.argv()
input=File.read!(source)
ast=Code.string_to_quoted!(input)
{_,defs}=Macro.prewalk(ast,[],fn
  {:defp,_,[{name,_,args},body]}=node,acc when name in [:maybe_start,:enabled?] -> {node,[{name,args,body}|acc]}
  node,acc->{node,acc}
end)
[{_,_,enabled_body}]=Enum.filter(defs,fn {n,_,_}->n==:enabled? end)
{_,assignments}=Macro.prewalk(ast,[],fn
  {:=,_,[{:failed,_,_},_]}=node,acc->{node,[node|acc]}
  node,acc->{node,acc}
end)
[failed]=assignments
{_,conditions}=Macro.prewalk(ast,[],fn
  {:if,_,[{:and,_,_}=condition,_]}=node,acc ->
    if String.contains?(Macro.to_string(condition),"is_nil(s.job)") and String.contains?(Macro.to_string(condition),"needs"),do: {node,[condition|acc]},else: {node,acc}
  node,acc->{node,acc}
end)
[condition]=conditions
module=quote do
  defmodule SchedulerAdmissionCapsule do
    defp enabled?(c),do: unquote(Keyword.fetch!(enabled_body,:do))
    def admitted?(s,force,due,needs) do
      unquote(failed)
      if unquote(condition),do: true,else: false
    end
  end
end
module=Macro.prewalk(module,fn {name,m,context} when is_atom(name) and is_atom(context)->{name,m,nil};v->v end)
Code.compile_quoted(module)
base=%{config: %{"tls"=>%{"enabled"=>true,"acme"=>%{"enabled"=>true}}},job: nil,data: %{"last_error"=>nil}}
rows=for {name,state,force,due,needs,want}<- [
  {"automatic-no-error",base,false,true,true,true},
  {"automatic-retryable-error",put_in(base.data["last_error"],%{"retryable"=>true}),false,true,true,true},
  {"automatic-hard-error-blocked",put_in(base.data["last_error"],%{"retryable"=>false}),false,true,true,false},
  {"manual-hard-error-allowed",put_in(base.data["last_error"],%{"retryable"=>false}),true,true,true,true},
  {"manual-does-not-bypass-issuer-floor",base,true,false,true,false},
  {"automatic-future-renewal-not-due",base,false,false,true,false},
  {"running-job-blocks-concurrent-order",%{base|job: %{}},true,true,true,false},
  {"no-renewal-needed",base,false,true,false,false},
  {"disabled-issuance",put_in(base.config["tls"]["acme"]["enabled"],false),true,true,true,false},
  {"disabled-native-tls",put_in(base.config["tls"]["enabled"],false),true,true,true,false}
] do
  actual=SchedulerAdmissionCapsule.admitted?(state,force,due,needs)
  true=actual==want
  %{"case"=>name,"passed"=>true,"admitted"=>actual}
end
File.write!(output,JSON.encode!(%{"passed"=>true,"cases"=>rows,"source_sha256"=>Base.encode16(:crypto.hash(:sha256,input),case: :lower),"application_started"=>false,"workers_started"=>0,"scope"=>"actual failed assignment/enabled helper/admission AST only; no scheduler I/O or lifecycle qualification"}))
