# Targeted unit probe of exact artifact modules, not a public lifecycle claim.
[artifact,store,project,control,agent]=System.argv()
[modules,_]=String.split(File.read!(artifact),"\nunless Code.ensure_loaded?(ADHD.CLI)",parts: 2)
Code.compile_string(modules,artifact)
{:module,:dets}=Code.ensure_loaded(:dets)
tracer=spawn(fn->
  loop=fn loop,count->receive do
    {:trace,_,:call,{:dets,:open_file,_}}->loop.(loop,count+1)
    {:count,pid,ref}->send(pid,{ref,count});loop.(loop,0)
  end end
  loop.(loop,0)
end)
:erlang.trace_pattern({:dets,:open_file,2},true,[:local])
:erlang.trace(self(),true,[:call,{:tracer,tracer}])
count=fn->
  ref=:erlang.trace_delivered(self())
  receive do {:trace_delivered,_,^ref}->:ok after 5000->raise "trace delivery timeout" end
  token=make_ref();send(tracer,{:count,self(),token})
  receive do {^token,n}->n after 5000->raise "trace collection timeout" end
end
{:ok,table}=:dets.open_file(:identity_trace_control,[file: String.to_charlist(control)])
:ok=:dets.close(table)
positive=count.()
true=positive>0
result=try do
  %{"value"=>ADHD.Projects.retained_agent?(%{"project_id"=>project,"store_path"=>store},agent)}
rescue e->%{"error"=>inspect(e.__struct__)}
catch {:domain,code}->%{"error"=>code}
end
opens=count.()
:erlang.trace(self(),false,[:call])
Process.exit(tracer,:kill)
IO.puts(JSON.encode!(%{"positive_control_dets_calls"=>positive,"guard_dets_calls"=>opens,"result"=>result}))
