# Operational probe: health deliberately does not require matcher availability.
try do
  config = File.read!("/config/hub.json") |> JSON.decode!()
  :inets.start()
  url = ~c"http://127.0.0.1:#{Map.get(config, "port", 8766)}/health"
  case :httpc.request(:get, {url, []}, [timeout: 3000], []) do
    {:ok, {{_, 200, _}, _, body}} ->
      if JSON.decode!(to_string(body)) != %{"status" => "ready"}, do: System.halt(1)
    _ -> System.halt(1)
  end
rescue
  _ -> System.halt(1)
end
