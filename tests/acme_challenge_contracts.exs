# Module-only challenge reader qualification. No GenServer/listener/client starts.
[tls_path, certificate_path, output] = System.argv()
defmodule ADHD.Config do
  def root, do: :persistent_term.get({__MODULE__, :config}, %{})
end
inputs = Map.new([tls_path, certificate_path], &{&1, File.read!(&1)})
Code.compile_string(inputs[certificate_path], certificate_path)
Code.compile_string(inputs[tls_path], tls_path)
root = Path.join(Path.dirname(output), "challenge-pure-" <> Base.encode16(:crypto.strong_rand_bytes(8), case: :lower))
File.mkdir_p!(Path.join(root, ".well-known/acme-challenge"))
File.chmod!(root, 0o700)
File.chmod!(Path.join(root, ".well-known"), 0o755)
File.chmod!(Path.join([root, ".well-known", "acme-challenge"]), 0o755)
uid = File.stat!(root).uid
:persistent_term.put({ADHD.ACMEFiles, :uid}, uid)
token = String.duplicate("A", 22)
value = token <> "." <> String.duplicate("B", 43)
path = Path.join([root, ".well-known", "acme-challenge", token])
File.write!(path, value)
File.chmod!(path, 0o644)
policy = %{"enabled" => true, "challenge_port" => 8080, "acme" => %{"enabled" => true, "domains" => ["hub.example.org"]}}
:persistent_term.put({ADHD.Config, :config}, %{"tls" => policy})
pending = %{webroot: root, generation: "pure", config: policy}
:persistent_term.put({ADHD.TLS, :challenge}, pending)
request = %{method: "GET", path: "/.well-known/acme-challenge/" <> token, target: "/.well-known/acme-challenge/" <> token, query: nil, body: "", headers: %{"host" => "hub.example.org"}}
rows = :ets.new(:challenge_results, [:set, :private])
check = fn name, req, expected ->
  actual = ADHD.TLS.challenge(req)
  {code, headers, body} = actual
  true = List.keyfind(headers, "content-type", 0) == {"content-type", "text/plain"}
  true = code == expected
  if expected != 200, do: true = body == {:raw, ""}
  if expected == 200, do: true = body == {:raw, value}
  :ets.insert(rows, {name, %{"case" => name, "passed" => true}})
end
try do
  check.("valid-owned-proof", request, 200)
  for host <- ["HUB.EXAMPLE.ORG", "hub.example.org:80", "hub.example.org:8080"] do
    check.("valid-host-" <> host, put_in(request.headers["host"], host), 200)
  end
  for host <- ["foreign.example.org", "hub.example.org:8443", "hub.example.org:0", "hub.example.org:65536", "hub.example.org.", "user@hub.example.org", "hub.example.org:80:80", "hub.example.org\r\nX: y", ""] do
    check.("reject-host-" <> Base.encode16(host), put_in(request.headers["host"], host), 404)
  end
  check.("missing-host", %{request | headers: %{}}, 404)
  check.("method-not-GET", %{request | method: "POST"}, 405)
  check.("GET-body-refused", %{request | body: "x"}, 404)
  check.("query-refused", %{request | query: "x", target: request.target <> "?x"}, 404)
  check.("encoded-traversal-refused", %{request | target: "/.well-known/acme-challenge/%2e%2e"}, 404)
  check.("unrelated-path-refused", %{request | path: "/admin/api", target: "/admin/api"}, 404)
  check.("unknown-token", %{request | path: request.path <> "z", target: request.target <> "z"}, 404)
  :persistent_term.put({ADHD.Config, :config}, %{"tls" => put_in(policy["acme"]["domains"], ["other.example.org"])})
  check.("policy-changed-fence", request, 404)
  :persistent_term.put({ADHD.Config, :config}, %{"tls" => policy})
  :persistent_term.put({ADHD.TLS, :challenge}, nil)
  check.("retired-attempt-fence", request, 404)
  :persistent_term.put({ADHD.TLS, :challenge}, pending)
  File.write!(path, String.duplicate("C", 22) <> "." <> String.duplicate("B", 43))
  check.("mismatched-token-content", request, 404)
  File.write!(path, value <> "private-extra")
  check.("extra-proof-suffix", request, 404)
  File.write!(path, String.duplicate("x", 1025))
  check.("oversize-proof", request, 404)
  File.write!(path, value); File.chmod!(path, 0o666)
  check.("writable-by-others-refused", request, 404)
  File.chmod!(path, 0o644)
  linked = path <> ".link"; File.ln!(path, linked)
  check.("hardlink-refused", request, 404)
  File.rm!(linked)
  File.rename!(path, linked); File.ln_s!(linked, path)
  check.("symlink-refused", request, 404)
  File.rm!(path); File.rename!(linked, path)
  check.("original-restored", request, 200)
  result = %{"passed" => true, "scope" => "Actual challenge functions/module-only with Config persistent-state seam; no HTTP server, TLS handshake, CA or child-client execution.", "cases" => :ets.tab2list(rows) |> Enum.sort() |> Enum.map(&elem(&1, 1)), "input_sha256" => Map.new(inputs, fn {path, bytes} -> {path, :crypto.hash(:sha256, bytes) |> Base.encode16(case: :lower)} end), "live_source_unchanged_at_end" => Enum.all?(inputs, fn {path, bytes} -> File.read!(path) == bytes end), "services_started" => 0}
  File.write!(output, JSON.encode!(result))
  IO.puts(JSON.encode!(%{"passed" => true, "cases" => length(result["cases"])}))
after
  File.rm_rf!(root)
end
