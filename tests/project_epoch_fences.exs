[source] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for file <- ~w(domain projects directory project_backup storage_registry config resources store) do
  Code.require_file(Path.join(source, file <> ".exs"))
end
ExUnit.start()

defmodule ProjectEpochFencesTest do
  use ExUnit.Case, async: false
  alias ADHD.{Scope, StorageRegistry, Resources}

  defp epoch(letter), do: String.duplicate(letter, 32)
  defp registry(red) do
    entries = for {id, project, allocation} <- [{"red", red, epoch("c")}, {"blue", epoch("b"), epoch("d")}], into: %{} do
      {id, %{"server_id" => epoch("f"), "project_id" => id, "aliases" => [],
        "initialized" => true, "generation" => 1, "project_epoch" => project,
        "allocation_epoch" => allocation, "topic_generation" => nil,
        "storage_anchor" => "/isolated-fixture/" <> id <> ".dets",
        "state_sha256" => String.duplicate("0", 64), "sequence" => 0,
        "storage_generation" => 0, "availability" => "ready"}}
    end
    %{"schema" => 1, "config_file" => "/isolated-fixture/config.json",
      "server_id" => epoch("f"), "projects" => entries,
      "reserved_epochs" => Enum.uniq([epoch("a"), epoch("b"), epoch("c"), epoch("d"), red])}
    |> StorageRegistry.seal()
  end
  defp replace_red(red), do: StorageRegistry.publish("/isolated-fixture/config.json", registry(red))

  setup do
    # Isolated VM memory only: no running hub, broker or host configuration changes.
    :persistent_term.put({ADHD.Config, :config}, %{"config_revision" => 1,
      "project_id" => "red", "store_path" => "/isolated-fixture/red.dets",
      "projects" => [%{"id" => "red", "status" => "active"}, %{"id" => "blue", "status" => "active"}],
      "resources" => %{"network_concurrency" => 2, "project_network_concurrency" => 1}})
    replace_red(epoch("a"))
    Scope.begin_work()
    Scope.put("red")
    Scope.put_epoch(epoch("a"))
    on_exit(fn ->
      if pid = Process.whereis(Resources), do: GenServer.stop(pid)
      for key <- [{ADHD.Config, :config}, {StorageRegistry, :current}, {Resources, :required}], do: :persistent_term.erase(key)
    end)
    :ok
  end

  test "nested local work keeps origin fence and restores caller context" do
    Scope.with_project("blue", fn ->
      Scope.put_epoch(epoch("b"))
      assert Enum.sort(Scope.fences()) == [{"blue", epoch("b")}, {"red", epoch("a")}]
      assert Scope.current?()
      replace_red(epoch("e"))
      refute Scope.current?()
    end)
    assert Scope.id() == "red"
    assert Scope.epoch() == epoch("a")
    refute Scope.current?()
    Scope.begin_work()
    assert Scope.fences() == []
  end

  test "serialized target guard rejects stale origin before executing callback" do
    replace_red(epoch("e"))
    state = %{project_epoch: epoch("b")}
    callback = fn s -> send(self(), :callback_executed); {:read, s} end
    assert {:reply, {:error, "RECOVERY_REQUIRED"}, %{state: ^state}} =
      ADHD.Store.handle_call({:transaction, epoch("b"), [{"red", epoch("a")}], callback}, nil, %{state: state})
    refute_receive :callback_executed, 20
    assert {:reply, {:ok, :read, _}, _} =
      ADHD.Store.handle_call({:transaction, epoch("b"), [{"red", epoch("e")}], callback}, nil, %{state: state})
    assert_receive :callback_executed
  end

  defp worker(parent, name, project, captured) do
    Kernel.spawn(fn ->
      Scope.put(project)
      Scope.put_epoch(captured)
      result = try do
        Resources.run(:network, 5000, fn _ ->
          send(parent, {:entered, name, self()})
          receive do :release -> :completed after 4500 -> :test_timeout end
        end)
      catch {:domain, code} -> {:rejected, code} end
      send(parent, {:finished, name, result})
    end)
  end

  defp await_waiter(remaining \\ 100)
  defp await_waiter(0), do: flunk("resource waiter was not admitted")
  defp await_waiter(remaining) do
    if Resources.stats()["waiting"] == 1, do: :ok, else: (Process.sleep(10); await_waiter(remaining - 1))
  end

  test "epoch switch retires active and queued target tickets while unrelated work finishes" do
    :ok = Resources.start()
    blue = worker(self(), :blue, "blue", epoch("b"))
    assert_receive {:entered, :blue, ^blue}, 1000
    red = worker(self(), :red, "red", epoch("a"))
    assert_receive {:entered, :red, ^red}, 1000
    queued = worker(self(), :queued, "red", epoch("a"))
    await_waiter()
    replace_red(epoch("e"))
    :ok = Resources.refresh()
    assert_receive {:finished, :queued, {:rejected, "RECOVERY_REQUIRED"}}, 1000
    refute_receive {:entered, :queued, ^queued}, 20
    lanes = Resources.stats()["lanes"]["network"]
    assert lanes["active"] == 1
    assert lanes["projects"]["blue"]["active"] == 1
    assert lanes["queued"] == 0
    send(red, :release)
    assert_receive {:finished, :red, {:rejected, "RECOVERY_REQUIRED"}}, 1000
    send(blue, :release)
    assert_receive {:finished, :blue, :completed}, 1000
    assert Resources.stats()["lanes"]["network"]["active"] == 0
  end
end
