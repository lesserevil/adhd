[source] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for file <- ~w(domain projects directory project_backup storage_registry config resources workers) do
  Code.require_file(Path.join(source, file <> ".exs"))
end
Application.ensure_all_started(:inets)
Application.ensure_all_started(:ssl)
ExUnit.start()

defmodule ProjectHTTPEpochTest do
  use ExUnit.Case, async: false
  alias ADHD.{Scope, StorageRegistry, Resources, Net}

  defp epoch(letter), do: String.duplicate(letter, 32)
  defp publish(red) do
    entries = for {id, captured, allocation} <- [{"red", red, epoch("c")}, {"blue", epoch("b"), epoch("d")}], into: %{} do
      {id, %{"server_id" => epoch("f"), "project_id" => id, "aliases" => [],
        "initialized" => true, "generation" => 1, "project_epoch" => captured,
        "allocation_epoch" => allocation, "topic_generation" => nil,
        "storage_anchor" => "/isolated-http/" <> id <> ".dets",
        "state_sha256" => String.duplicate("0", 64), "sequence" => 0,
        "storage_generation" => 0, "availability" => "ready"}}
    end
    registry = %{"schema" => 1, "config_file" => "/isolated-http/config.json",
      "server_id" => epoch("f"), "projects" => entries,
      "reserved_epochs" => Enum.uniq([epoch("a"), epoch("b"), epoch("c"), epoch("d"), red])}
      |> StorageRegistry.seal()
    StorageRegistry.publish("/isolated-http/config.json", registry)
  end

  setup do
    :persistent_term.put({ADHD.Config, :config}, %{"config_revision" => 1,
      "projects" => [%{"id" => "red", "status" => "active"}, %{"id" => "blue", "status" => "active"}],
      "resources" => %{"network_concurrency" => 2, "project_network_concurrency" => 1}})
    publish(epoch("a"))
    :ok = Resources.start()
    on_exit(fn ->
      if pid = Process.whereis(Resources), do: GenServer.stop(pid)
      for key <- [{ADHD.Config, :config}, {StorageRegistry, :current}, {Resources, :required}], do: :persistent_term.erase(key)
    end)
    :ok
  end

  # A real loopback TCP peer holds its HTTP response until explicitly released.
  # No model, Kafka, active hub configuration or fabricated httpc messages.
  defp peer(parent, name) do
    {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, reuseaddr: true, ip: {127, 0, 0, 1}])
    {:ok, {_, port}} = :inet.sockname(listener)
    pid = spawn_link(fn ->
      {:ok, socket} = :gen_tcp.accept(listener, 3000)
      :gen_tcp.close(listener)
      {:ok, request} = :gen_tcp.recv(socket, 0, 3000)
      send(parent, {:request, name, request})
      receive do
        :reply ->
          body = "{\"peer\":\"#{name}\"}"
          result = :gen_tcp.send(socket, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: #{byte_size(body)}\r\nConnection: close\r\n\r\n" <> body)
          send(parent, {:sent, name, result})
      after 4000 -> send(parent, {:peer_timeout, name})
      end
      :gen_tcp.close(socket)
    end)
    {pid, "http://127.0.0.1:#{port}/held"}
  end

  defp request(parent, name, url, project, captured) do
    spawn_link(fn ->
      Scope.put(project)
      Scope.put_epoch(captured)
      result = try do
        {:ok, Net.request(:get, url, nil, [], 1500)}
      catch {:domain, code} -> {:rejected, code} end
      send(parent, {:result, name, result})
    end)
  end

  test "a restored project's actual held HTTP reply cannot succeed while another project's reply completes" do
    {red_peer, red_url} = peer(self(), "red")
    {blue_peer, blue_url} = peer(self(), "blue")
    request(self(), :red, red_url, "red", epoch("a"))
    request(self(), :blue, blue_url, "blue", epoch("b"))
    assert_receive {:request, "red", red_request}, 2000
    assert_receive {:request, "blue", blue_request}, 2000
    assert red_request =~ "GET /held HTTP/1.1"
    assert blue_request =~ "GET /held HTTP/1.1"
    publish(epoch("e"))
    :ok = Resources.refresh()
    lane = Resources.stats()["lanes"]["network"]
    assert lane["active"] == 1
    assert lane["projects"]["blue"]["active"] == 1
    send(red_peer, :reply)
    send(blue_peer, :reply)
    assert_receive {:sent, "red", _}, 1000
    assert_receive {:sent, "blue", :ok}, 1000
    assert_receive {:result, :blue, {:ok, {200, %{"peer" => "blue"}}}}, 2000
    assert_receive {:result, :red, {:rejected, _}}, 2000
    refute_receive {:result, :red, {:ok, _}}, 20
    assert Resources.stats()["lanes"]["network"]["active"] == 0
  end

  test "a stale project is rejected before any actual HTTP connection" do
    {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, ip: {127, 0, 0, 1}])
    try do
      {:ok, {_, port}} = :inet.sockname(listener)
      publish(epoch("e"))
      Scope.put("red")
      Scope.put_epoch(epoch("a"))
      assert catch_throw(Net.request(:get, "http://127.0.0.1:#{port}/never", nil, [], 500)) == {:domain, "RECOVERY_REQUIRED"}
      assert {:error, :timeout} = :gen_tcp.accept(listener, 30)
    after
      :gen_tcp.close(listener)
    end
  end
end
