# Native resource-admission fixture. Supply the generated resources.exs path.
defmodule ADHD.Domain do
  def fail(code \\ "INVALID_PARAMS"),do: throw({:domain,code})
  def keys(v,keys),do: check(is_map(v) and Enum.all?(Map.keys(v),&(&1 in keys)))
  def integer(v,a,b),do: check(is_integer(v) and v>=a and v<=b)
  def check(true),do: :ok
  def check(_),do: fail()
end
defmodule ADHD.Config do
  def root,do: :persistent_term.get(:resources_test_config,%{})
end
defmodule ADHD.Scope do
  def id,do: Process.get(:adhd_project)
  def put(id),do: Process.put(:adhd_project,id)
end
[resource_source] = System.argv()
Code.require_file(resource_source)
ExUnit.start()
defmodule ResourcesTests do
  use ExUnit.Case, async: false
  alias ADHD.Resources,as: R
  def root(extra \\ %{}) do
    %{"config_revision"=>1,"project_id"=>"red","projects"=>for(id<-~w(red blue green),do: %{"id"=>id,"status"=>"active"}),"resources"=>Map.merge(R.defaults(),extra)}
  end
  setup do
    if Process.whereis(R),do: GenServer.stop(R)
    :persistent_term.erase({R,:required})
    :persistent_term.put(:resources_test_config,root())
    :ok=R.start()
    on_exit(fn->if Process.whereis(R),do: GenServer.stop(R) end)
    :ok
  end
  def job(project,tag,kind \\ :model,timeout \\ 3000) do
    parent=self()
    spawn(fn->
      ADHD.Scope.put(project)
      value=try do
        R.run(kind,timeout,fn left->send(parent,{:start,tag,self(),left});receive do :finish->:finished after left->:expired end end)
      catch :throw,value->value end
      send(parent,{:done,tag,value})
    end)
  end
  def wait_for(fun,n \\ 200)
  def wait_for(fun,0),do: assert(fun.())
  def wait_for(fun,n),do: if(fun.(),do: true,else: (Process.sleep(5);wait_for(fun,n-1)))
  test "global and project limits with independent eventing" do
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>2,"project_model_concurrency"=>1}))
    a=job("red",:a);assert_receive {:start,:a,^a,_}
    b=job("red",:b);wait_for(fn->R.stats()["waiting"]==1 end)
    c=job("blue",:c);assert_receive {:start,:c,^c,_}
    assert R.stats()["lanes"]["model"]["active"]==2
    e=job("green",:e,:eventing);assert_receive {:start,:e,^e,_}
    send(a,:finish);assert_receive {:start,:b,^b,_}
    send(b,:finish);send(c,:finish);send(e,:finish)
    wait_for(fn->R.stats()["ingress_tickets"]==0 end)
  end
  test "round robin and project FIFO" do
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>1}))
    a=job("red",:a);assert_receive {:start,:a,^a,_}
    b=job("red",:b);wait_for(fn->R.stats()["waiting"]==1 end)
    c=job("red",:c);wait_for(fn->R.stats()["waiting"]==2 end)
    d=job("blue",:d);wait_for(fn->R.stats()["waiting"]==3 end)
    e=job("green",:e);wait_for(fn->R.stats()["waiting"]==4 end)
    send(a,:finish);assert_receive {:start,:b,^b,_};send(b,:finish)
    assert_receive {:start,:d,^d,_};send(d,:finish)
    assert_receive {:start,:e,^e,_};send(e,:finish)
    assert_receive {:start,:c,^c,_};send(c,:finish)
  end
  test "queue residence consumes timeout and never invokes timed out callback" do
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>1}))
    a=job("red",:a);assert_receive {:start,:a,^a,_}
    _b=job("blue",:b,:model,60)
    assert_receive {:done,:b,{:domain,"MODEL_BUSY"}},300
    refute_receive {:start,:b,_,_}
    assert R.stats()["waiting"]==0
    b=job("blue",:remaining,:model,1000);wait_for(fn->R.stats()["waiting"]==1 end)
    Process.sleep(70);send(a,:finish)
    assert_receive {:start,:remaining,^b,left};assert left<950;send(b,:finish)
  end
  test "bounded queue does not block eventing" do
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>1,"max_waiters"=>1}))
    a=job("red",:a);assert_receive {:start,:a,^a,_}
    b=job("blue",:b);wait_for(fn->R.stats()["waiting"]==1 end)
    _c=job("green",:c);assert_receive {:done,:c,{:domain,"MODEL_BUSY"}}
    e=job("green",:e,:eventing);assert_receive {:start,:e,^e,_}
    send(a,:finish);assert_receive {:start,:b,^b,_};send(b,:finish);send(e,:finish)
  end
  test "killed active and queued owners release tickets" do
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>1}))
    a=job("red",:a);assert_receive {:start,:a,^a,_}
    b=job("blue",:b);wait_for(fn->R.stats()["waiting"]==1 end)
    Process.exit(b,:kill);wait_for(fn->R.stats()["waiting"]==0 end)
    c=job("green",:c);wait_for(fn->R.stats()["waiting"]==1 end)
    Process.exit(a,:kill);assert_receive {:start,:c,^c,_};send(c,:finish)
    wait_for(fn->R.stats()["ingress_tickets"]==0 end)
  end
  test "revision fences and hot limit reductions preserve running requests" do
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>2}))
    a=job("red",:a);b=job("blue",:b);assert_receive {:start,:a,^a,_};assert_receive {:start,:b,^b,_}
    _c=job("green",:old);wait_for(fn->R.stats()["waiting"]==1 end)
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>1}) |> Map.put("config_revision",2));R.refresh()
    assert_receive {:done,:old,{:domain,"CONFIG_CHANGED"}}
    assert R.stats()["lanes"]["model"]["active"]==2
    c=job("green",:new);wait_for(fn->R.stats()["waiting"]==1 end)
    send(a,:finish);refute_receive {:start,:new,_,_},30
    send(b,:finish);assert_receive {:start,:new,^c,_};send(c,:finish)
  end
  test "archival fences queued calls and exceptions release slots" do
    :persistent_term.put(:resources_test_config,root(%{"model_concurrency"=>1}))
    a=job("red",:a);assert_receive {:start,:a,^a,_}
    _b=job("blue",:b);wait_for(fn->R.stats()["waiting"]==1 end)
    c=root(%{"model_concurrency"=>1});c=update_in(c,["projects"],&Enum.map(&1,fn p->if p["id"]=="blue",do: Map.put(p,"status","archived"),else: p end));:persistent_term.put(:resources_test_config,c);R.refresh()
    assert_receive {:done,:b,{:domain,"PROJECT_ARCHIVED"}}
    send(a,:finish);wait_for(fn->R.stats()["ingress_tickets"]==0 end)
    ADHD.Scope.put("red")
    assert_raise RuntimeError,fn->R.run(:model,100,fn _->raise "synthetic exception" end) end
    assert R.stats()["ingress_tickets"]==0
  end
  test "invalid config rejected and native unstarted fallback only before startup" do
    assert catch_throw(R.normalize(%{"resources"=>%{"max_waiters"=>-1}}))=={:domain,"INVALID_PARAMS"}
    assert catch_throw(R.normalize(%{"resources"=>%{"unknown"=>1}}))=={:domain,"INVALID_PARAMS"}
    GenServer.stop(R)
    assert catch_throw(R.run(:model,10,fn _->:wrong end))=={:domain,"MODEL_BUSY"}
  end
end
