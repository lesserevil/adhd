[baseline,out,manifest]=System.argv()
body=File.read!(baseline)
measure=fn label,ast->quote do: ADHD.Diagnostic.measure(unquote(label),fn->unquote(ast) end) end
rows=for name<-~w(Eventing Resources Store Storage) do
  [start,len]=Regex.run(Regex.compile!("(?m)^defmodule ADHD\\."<>name<>" do\\n"),body,return: :index) |> hd() |> Tuple.to_list()
  tail=binary_part(body,start+len,byte_size(body)-start-len)
  finish=case Regex.run(~r/(?m)^defmodule /,tail,return: :index) do nil->byte_size(body);[{index,_}]->start+len+index end
  raw=binary_part(body,start,finish-start)
  ast=Code.string_to_quoted!(raw)
  changed=Macro.postwalk(ast,fn
    {kind,meta,[head,[do: code]]}=node when kind in [:def,:defp]->
      plain=case head do {:when,_,[inner|_]}->inner;_->head end
      label=case {name,plain} do
        {"Eventing",{:request,_,_}}->"eventing_request"
        {"Eventing",{:request_now,_,_}}->"eventing_wire"
        {"Resources",{:run,_,_}}->"resource_total"
        {"Resources",{:track_http,_,_}}->"resource_track"
        {"Store",{:call,_,[_]}}->"store_roundtrip"
        {"Store",{:handle_call,_,[{:{},_,[:transaction,_,_,_]},_,_]}}->"store_transaction"
        {"Storage",{:persist,_,[_,_,_]}}->"storage_persist"
        _->nil
      end
      if label,do: {kind,meta,[head,[do: measure.(label,code)]]},else: node
    {{:.,_,[{:__aliases__,_,[:GenServer]},:call]},_,[{:__MODULE__,_,_},{:{},_,[:acquire|_]},_]}=node->measure.("resource_acquire",node)
    node->node
  end)
  replaced=Macro.to_string(changed)<>"\n"
  {start,finish,raw,replaced,name}
end
result=Enum.reduce(Enum.sort_by(rows,&elem(&1,0),:desc),body,fn {start,finish,_,replacement,_},acc->binary_part(acc,0,start)<>replacement<>binary_part(acc,finish,byte_size(acc)-finish) end)
prefix="""
defmodule ADHD.Diagnostic do
  def start,do: :persistent_term.put({__MODULE__,:counter},:atomics.new(1,[]))
  def measure(stage,fun) do
    started=System.monotonic_time(:microsecond)
    try do fun.() after
      elapsed=System.monotonic_time(:microsecond)-started
      counter=:atomics.add_get(:persistent_term.get({__MODULE__,:counter}),1,1)
      if counter<=50000,do: IO.puts(:stderr,JSON.encode!(%{"diagnostic"=>stage,"duration_us"=>elapsed,"at_us"=>System.monotonic_time(:microsecond),"counter"=>counter}))
    end
  end
end
ADHD.Diagnostic.start()
"""
result=prefix<>result
Code.string_to_quoted!(result)
File.write!(out,result)
sha=fn bytes->Base.encode16(:crypto.hash(:sha256,bytes),case: :lower) end
proof=%{"baseline_sha256"=>sha.(body),"overlay_sha256"=>sha.(result),"diagnostic_only"=>true,"shared_source_changed"=>false,"modules"=>Map.new(rows,fn {_,_,raw,new,name}->{name,%{"baseline_sha256"=>sha.(raw),"overlay_sha256"=>sha.(new)}} end)}
File.write!(manifest,JSON.encode!(proof))
