# Actual TLS API/callbacks; no application, CA, client, OS socket or listener.
[domain, certificate, source, output] = System.argv()
Code.compile_file(domain)
Code.compile_file(certificate)
input = File.read!(source)
Code.compile_string("""
defmodule ADHD.ControlPlanePorts do
  def close(port) do
    send(:persistent_term.get({__MODULE__, :owner}), {:closed, port})
    :ok
  end
end
""")
:persistent_term.put({ADHD.ControlPlanePorts, :owner}, self())
ast = Code.string_to_quoted!(input)
{ast, seams} = Macro.prewalk(ast, [], fn
  {:defp, meta, [{:prepare_listeners, hm, args}, [do: _]]}, acc ->
    body = quote do: %{https: :prepared_fixture_port}
    {{:defp, meta, [{:prepare_listeners, hm, args}, [do: body]]}, [:prepare_listeners | acc]}
  {:defp, meta, [{:activate_listeners, hm, args}, [do: _]]}, acc ->
    body = Code.string_to_quoted!("send(:persistent_term.get({ADHD.ControlPlanePorts, :owner}), :activated); %{s | config: c, listeners: Map.merge(s.listeners, prepared), fingerprint: fingerprint(c, s.trust)}")
    {{:defp, meta, [{:activate_listeners, hm, args}, [do: body]]}, [:activate_listeners | acc]}
  {{:., dm, [:gen_tcp, :close]}, cm, args}, acc ->
    {{{:., dm, [{:__aliases__, [], [:ADHD, :ControlPlanePorts]}, :close]}, cm, args}, [:close | acc]}
  node, acc -> {node, acc}
end)
{:defmodule, dm, [name, [do: {:__block__, bm, body}]]} = ast
expose = Code.string_to_quoted!("def control_plane_publish(s), do: publish_status(s)")
ast = {:defmodule, dm, [name, [do: {:__block__, bm, body ++ [expose]}]]}
true = Enum.count(seams, &(&1 == :prepare_listeners)) == 1
true = Enum.count(seams, &(&1 == :activate_listeners)) == 1
Code.compile_quoted(ast, source)
rows = :ets.new(:checks, [:ordered_set])
check = fn name, f -> true = f.(); :ets.insert(rows, {name, %{"case" => name, "passed" => true}}) end
rejected = fn f -> try do f.(); false rescue _ -> true catch _, _ -> true end end
now = ADHD.Domain.ms()
config = %{"config_revision" => 7, "tls" => ADHD.TLS.defaults(), "private_secret" => "PRIVATE_CONFIG_MARKER"}
config = put_in(config, ["tls", "enabled"], true)
certificate_state = %{metadata: %{"sha256" => String.duplicate("a",64), "serial" => "1", "not_before" => now-1000, "not_after" => now+60000}, domains: ["hub.example.org"], expires: now+60000, private: "PRIVATE_KEY_MARKER", chain: "PRIVATE_CHAIN_MARKER"}
state = %{config: config, certificate: certificate_state, data: %{"last_attempt_at"=>nil,"next_attempt_at"=>nil,"last_success_at"=>nil,"last_error"=>nil,"receipts"=>%{"PRIVATE_RECEIPT_MARKER"=>true}}, listeners: %{https: :old_fixture_port}, job: nil, trust_error: false, listener_error: false, recovering: false, fingerprint: nil, trust: nil, root: "PRIVATE_ROOT_MARKER"}
parent = self()
# Raw BEAM fixture process owns the real protected ETS table but never answers
# GenServer calls. A status implementation using GenServer.call would fail.
owner = spawn(fn ->
 Process.register(self(), ADHD.TLS)
 ADHD.TLS.control_plane_publish(state)
 send(parent, {:published, self()})
 loop = fn loop -> receive do
  {:publish, s} -> ADHD.TLS.control_plane_publish(s); send(parent, {:published,self()}); loop.(loop)
  :stop -> :ok
  other -> send(parent, {:unexpected_manager_request, other}); loop.(loop)
 end end
 loop.(loop)
end)
receive do {:published,^owner}->:ok after 1000->raise "missing publication" end
check.("busy-manager-status-never-calls-manager", fn ->
 {elapsed, status} = :timer.tc(fn->ADHD.TLS.status() end)
 status["https_state"] == "ready" and elapsed < 500000 and Process.info(owner,:message_queue_len)=={:message_queue_len,0}
end)
check.("protected-snapshot-redacts-private-state", fn ->
 table=ADHD.TLS.Status
 [{:state, view}]=:ets.lookup(table,:state)
 bytes=:erlang.term_to_binary(view)
 :ets.info(table,:protection)==:protected and not Enum.any?(["PRIVATE_CONFIG_MARKER","PRIVATE_KEY_MARKER","PRIVATE_CHAIN_MARKER","PRIVATE_RECEIPT_MARKER","PRIVATE_ROOT_MARKER"], &String.contains?(bytes,&1)) and rejected.(fn->:ets.insert(table,{:state,%{}}) end)
end)
statuses = [ADHD.TLS.status()]
future = %{certificate_state | metadata: Map.put(certificate_state.metadata,"not_before",ADHD.Domain.ms()+60000)}
send(owner,{:publish,%{state|certificate: future}})
receive do {:published,^owner}->:ok after 1000->raise "missing publication" end
check.("future-not-before-status-error",fn-> p=ADHD.TLS.status();p["https_state"]=="error" and p["active_domains"]==[] end)
statuses = statuses ++ [ADHD.TLS.status()]
expiry=ADHD.Domain.ms()+150
short=%{certificate_state|expires: expiry,metadata: Map.put(certificate_state.metadata,"not_after",expiry)}
send(owner,{:publish,%{state|certificate: short}})
receive do {:published,^owner}->:ok after 1000->raise "missing publication" end
Process.sleep(200)
check.("expiry-recomputed-without-manager-republication",fn->p=ADHD.TLS.status();p["https_state"]=="expired" and p["active_domains"]==[] end)
statuses=statuses++[ADHD.TLS.status()]
monitor=Process.monitor(owner);send(owner,:stop)
receive do {:DOWN,^monitor,:process,^owner,:normal}->:ok after 1000->raise "owner remained alive" end
check.("manager-death-removes-snapshot-fails-closed",fn->:ets.whereis(ADHD.TLS.Status)==:undefined and try do ADHD.TLS.status();false catch {:domain,"DEPENDENCY_UNAVAILABLE"}->true end end)
check.("missing-manager-renew-contained",fn->ADHD.TLS.renew(%{},%{})=={:error,"DEPENDENCY_UNAVAILABLE"} end)
check.("missing-manager-prepare-contained",fn->ADHD.TLS.prepare(config)=={:error,:unavailable} end)
check.("missing-manager-discard-contained",fn->ADHD.TLS.discard({:ok,%{listeners: %{}}})==:ok end)
# A callee dies after receiving renew; the actual API must preserve its caller.
crashing=spawn(fn->Process.register(self(),ADHD.TLS);send(parent,{:registered,self()});receive do {:"$gen_call",_,{:renew,_,_}}->exit(:fixture_crash) end end)
receive do {:registered,^crashing}->:ok after 1000->raise "missing callee" end
check.("renew-callee-exit-contained",fn->ADHD.TLS.renew(%{},%{})=={:error,"DEPENDENCY_UNAVAILABLE"} end)
# Actual ten-second API timeout followed by a deliberately late callback. Fake
# listener handles expose cancellation without any network binding.
late=spawn(fn->
 Process.register(self(),ADHD.TLS);send(parent,{:registered,self()})
 receive do {:"$gen_call",from,{:prepare,ticket,c}} ->
  Process.sleep(10100)
  {:reply,reply,next}=ADHD.TLS.handle_call({:prepare,ticket,c},from,state)
  GenServer.reply(from,reply)
  receive do {:cancel_prepare,^ticket}->
   {:noreply,closed}=ADHD.TLS.handle_info({:cancel_prepare,ticket},next)
   send(parent,{:late_closed,Map.get(closed,:preparations),closed.listeners})
  after 1000->send(parent,:missing_cancel) end
 end
end)
late_monitor=Process.monitor(late)
receive do {:registered,^late}->:ok after 1000->raise "missing late manager" end
started=System.monotonic_time(:millisecond)
reply=ADHD.TLS.prepare(config)
elapsed=System.monotonic_time(:millisecond)-started
check.("original-prepare-ten-second-budget-contained",fn->reply=={:error,:unavailable} and elapsed>=9500 and elapsed<11500 end)
check.("late-prebound-port-cancelled-old-listener-preserved",fn->
 receive do {:closed,:prepared_fixture_port}->true after 1500->false end and
 receive do {:late_closed,prepared,listeners}->prepared==%{} and listeners==state.listeners after 1000->false end
end)
check.("owned-fake-processes-closed", fn ->
 receive do {:DOWN,^late_monitor,:process,^late,:normal}->:ok after 1000->raise "late fixture remained alive" end
 not Process.alive?(owner) and not Process.alive?(crashing) and not Process.alive?(late) and Process.whereis(ADHD.TLS)==nil
end)
# Direct callback ticket invariants; no process or listener activation.
ticket=make_ref()
{:reply,{:ok,p},prepared}=ADHD.TLS.handle_call({:prepare,ticket,config},nil,state)
{:noreply,cancelled}=ADHD.TLS.handle_info({:cancel_prepare,ticket},prepared)
check.("cancelled-ticket-cannot-activate",fn->rejected.(fn->ADHD.TLS.handle_call({:activate,{:ok,p},config},nil,cancelled) end) end)
check.("duplicate-cancellation-is-idempotent",fn->ADHD.TLS.handle_info({:cancel_prepare,ticket},cancelled)=={:noreply,cancelled} end)
check.("async-discard-ticket-no-manager-needed",fn->ADHD.TLS.discard({:ok,p})==:ok end)
ticket2=make_ref()
{:reply,{:ok,p2},prepared2}=ADHD.TLS.handle_call({:prepare,ticket2,config},nil,state)
{:reply,:ok,activated}=ADHD.TLS.handle_call({:activate,{:ok,p2},config},nil,prepared2)
check.("activation-consumes-ticket",fn->Map.get(activated,:preparations)==%{} and activated.listeners[:https]==:prepared_fixture_port end)
receive do :activated->:ok after 1000->raise "successful ticket did not activate" end
# Drain closure observation from the preceding direct cancellation.
receive do {:closed,:prepared_fixture_port}->:ok after 1000->raise "direct cancellation did not close" end
check.("cancel-after-activation-never-closes-active-port",fn->
 {:noreply,next}=ADHD.TLS.handle_info({:cancel_prepare,ticket2},activated)
 next==activated and receive do {:closed,:prepared_fixture_port}->false after 0->true end
end)
:ets.delete(ADHD.TLS.Status)
receive do :activated->raise "cancelled listener activated" after 0->:ok end
receive do {:unexpected_manager_request,_}->raise "status called manager" after 0->:ok end
result=%{"passed"=>true,"checks"=>:ets.tab2list(rows)|>Enum.map(&elem(&1,1)),"statuses"=>statuses,"prepare_elapsed_ms"=>elapsed,"tls_source_sha256"=>Base.encode16(:crypto.hash(:sha256,input),case: :lower),"io_seams"=>Enum.map(seams,&Atom.to_string/1),"scope"=>"module-only actual API/callback/ETS and fake listener handles; no application, CA, client or OS listener"}
File.write!(output,JSON.encode!(result))
IO.puts("control-plane checks #{length(result["checks"])} PASS")
