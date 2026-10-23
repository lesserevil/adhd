# Isolated module/callback capsule. No hub, guardian executable, socket or issuer.
# Usage: elixir tests/acme_admission_contracts.exs /absolute/candidate-source
# Original TLS function bodies are retained; only module references and explicit
# IO boundaries are redirected. This does not qualify real issuance or packaging.
[source] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
Code.require_file(Path.join(source, "domain.exs"))
Code.require_file(Path.join(source, "tls_certificate.exs"))

defmodule ACMEAdmissionSpy do
  def event(value), do: Process.put(:events, (Process.get(:events) || []) ++ [value])
  def events, do: Process.get(:events, [])
  def reset, do: Process.put(:events, [])
  def lock_available?(_root) do
    value = Process.get(:lock_available, false)
    event({:lock, value})
    value
  end
  def run(_, _, _, _, _, _, _), do: raise("capsule must never launch a client")
  def read(path) do
    event({:read, path})
    ADHD.ACMEFiles.read(path)
  end
  def directory(path) do
    event({:directory, path})
    ADHD.ACMEFiles.directory(path)
  end
  def harden_tree(path) do
    event({:harden, path})
    ADHD.ACMEFiles.harden_tree(path)
  end
  def write(path, bytes), do: ADHD.ACMEFiles.write(path, bytes)
  def init_owner(path), do: ADHD.ACMEFiles.init_owner(path)
  # Certificate cryptography has its own independent live oracle. Here the
  # sentinel isolates account-integrity ordering from certificate parsing.
  def load(_, _, _, _), do: Process.get(:retained_certificate)
  def load(_, _, _), do: raise("unexpected publication in callback capsule")
  def live?(_), do: true
end

# Add wrappers only to call existing private functions; never replace bodies.
ast = Code.string_to_quoted!(File.read!(Path.join(source, "tls.exs")))
ast = Macro.prewalk(ast, fn
  {:__aliases__, meta, [:ADHD, :TLS]} -> {:__aliases__, meta, [:ACMEAdmissionTLS]}
  {:__aliases__, meta, [:ADHD, name]} when name in [:ACMEFiles, :ACMEClient, :TLSCertificate] ->
    {:__aliases__, meta, [:ACMEAdmissionSpy]}
  node -> node
end)
wrappers = quote do
  def capsule_initialize(s), do: initialize(s)
  def capsule_account(s), do: ensure_account(s)
  def capsule_save(s), do: save(s)
  def capsule_recover(s), do: recover(s)
  def capsule_closed(s), do: recover_closed(s)
  def capsule_finish(s, result), do: finish(s, result)
  def capsule_maybe(s), do: maybe_start(s, false)
end
{:defmodule, meta, [name, [do: body]]} = ast
{:__block__, _, statements} = body
{:__block__, _, additions} = wrappers
Code.compile_quoted({:defmodule, meta, [name, [do: {:__block__, [], statements ++ additions}]]})
ExUnit.start()

defmodule ACMEAdmissionContracts do
  use ExUnit.Case, async: false
  alias ADHD.Domain, as: D
  alias ACMEAdmissionTLS, as: TLS
  alias ACMEAdmissionSpy, as: Spy

  setup do
    base = Path.join(System.tmp_dir!(), "adhd-acme-capsule-" <> D.opaque())
    File.mkdir!(base); File.chmod!(base, 0o700)
    config = %{"config_revision" => 7, "tls" => TLS.defaults()}
    config = put_in(config, ["tls", "enabled"], true)
    config = put_in(config, ["tls", "acme", "enabled"], true)
    config = put_in(config, ["tls", "acme", "domains"], ["one.acme.test"])
    state = %{path: Path.join(base, "config.json"), root: Path.join(base, "acme"),
      config: config, owner: nil, job: nil, fingerprint: "current", trust: nil,
      trust_error: false, listener_error: false, recovering: false, certificate: nil,
      active: nil, listeners: %{},
      data: %{"last_attempt_at" => nil, "next_attempt_at" => nil,
        "last_success_at" => nil, "last_error" => nil, "receipts" => %{}, "active" => nil}}
    state = TLS.capsule_initialize(state)
    Process.put(:lock_available, false); Spy.reset()
    on_exit(fn -> File.rm_rf!(base) end)
    %{s: state, base: base}
  end

  defp command(mid, revision \\ 7), do: %{"op" => "tls_renew", "message_id" => mid,
    "expected_revision" => revision, "confirm" => true}
  defp admin, do: %{"id" => "admin", "role" => "Admin"}
  defp renew(s, command, user \\ admin()), do: TLS.handle_call({:renew, command, user}, {self(), make_ref()}, s)
  defp persisted(s), do: ADHD.JSON.decode!(File.read!(Path.join(s.root, "state.json")))
  defp flush_force do
    receive do :force -> flush_force() after 0 -> :ok end
  end

  test "different MIDs join active identical policy without scheduling a second attempt", %{s: s} do
    due = D.ms() + 50_000
    s = %{s | job: %{fingerprint: s.fingerprint}, data: Map.put(s.data, "next_attempt_at", due)}
    {:reply, {:ok, first}, one} = renew(s, command("first"))
    {:reply, {:ok, ^first}, two} = renew(one, command("second"))
    assert map_size(two.data["receipts"]) == 2
    assert persisted(two)["receipts"] == two.data["receipts"]
    assert two.data["force_pending"] != true
    assert two.data["next_attempt_at"] == due
    {:reply, {:ok, ^first}, replay} = renew(two, command("first"))
    assert replay == two
    {:reply, {:error, "FORBIDDEN"}, denied} = renew(two, command("first"), %{"id" => "admin", "role" => "Viewer"})
    assert denied == two
    finished = TLS.capsule_finish(%{two | job: nil}, {:error, "ACME_CERTIFICATE", nil})
    assert finished.data["last_error"]["retryable"] == false
    assert TLS.capsule_maybe(finished).job == nil
    refute Enum.any?(Spy.events(), &match?({:lock, _}, &1))
    refute_received :force
  end

  test "new policy intent survives a retiring different-fingerprint job and issuer floor", %{s: s} do
    floor = D.ms() + 120_000
    s = %{s | job: %{fingerprint: "retiring"}, data: Map.put(s.data, "issuer_retry_at", floor)}
    {:reply, {:ok, _}, queued} = renew(s, command("new-policy"))
    assert queued.data["force_pending"] == true
    assert queued.data["next_attempt_at"] >= floor
    assert persisted(queued)["force_pending"] == true
    assert TLS.capsule_maybe(queued).job == s.job
    assert_received :force
    flush_force()
  end

  defp known_account(s) do
    s = TLS.capsule_account(s)
    [{id, _}] = Map.to_list(s.data["accounts"])
    root = Path.join([s.root, "accounts", id])
    key = "accounts/issuer/keys/account.key"
    File.mkdir_p!(Path.dirname(Path.join(root, key)))
    for dir <- [Path.join(root, "accounts"), Path.join(root, "accounts/issuer"), Path.join(root, "accounts/issuer/keys")], do: File.chmod!(dir, 0o700)
    ADHD.ACMEFiles.write(Path.join(root, key), "original witnessed key")
    digest = :crypto.hash(:sha256, "original witnessed key") |> Base.encode16(case: :lower)
    s = %{s | data: put_in(s.data, ["accounts", id, "keys"], %{key => digest})} |> TLS.capsule_save()
    {s, root, Path.join(root, key)}
  end

  defp retained(s) do
    id = String.duplicate("g", 32)
    root = Path.join([s.root, "generations", id]); ADHD.ACMEFiles.directory(root)
    cert = %{domains: ["one.acme.test"], metadata: %{"not_before" => D.ms() - 1000, "not_after" => D.ms() + 90_000}}
    for {name, bytes} <- [{"chain.pem", "capsule certificate sentinel"}, {"key.pem", "capsule key sentinel"},
      {"metadata.json", JSON.encode!(%{"domains" => cert.domains, "certificate" => cert.metadata})}], do: ADHD.ACMEFiles.write(Path.join(root, name), bytes)
    Process.put(:retained_certificate, cert)
    s = %{s | data: s.data |> Map.put("active", id) |> Map.put("ordering", true)} |> TLS.capsule_save()
    {s, cert}
  end

  defp account_events(root), do: Enum.filter(Spy.events(), fn
    {kind, path} when kind in [:read, :directory, :harden] -> path == root or String.starts_with?(path, root <> "/")
    _ -> false
  end)

  for damage <- [:missing, :changed, :intact], ordering <- [true, false] do
    test "cold account #{damage}, ordering=#{ordering}: guardian lock proof precedes integrity IO; retained cert survives", %{s: initial} do
      {s, account, key} = known_account(initial)
      {s, certificate} = retained(s)
      s = %{s | data: Map.put(s.data, "ordering", unquote(ordering))} |> TLS.capsule_save()
      case unquote(damage) do
        :missing -> File.rm!(key)
        :changed -> ADHD.ACMEFiles.write(key, "changed key")
        :intact -> :ok
      end
      Spy.reset()
      cold = TLS.capsule_recover(%{s | owner: nil, certificate: nil})
      assert cold.certificate == certificate
      assert cold.recovering == true
      assert account_events(account) == []
      busy = TLS.capsule_closed(cold)
      assert busy == cold
      assert account_events(account) == []
      assert {:lock, false} in Spy.events()
      Spy.reset(); Process.put(:lock_available, true)
      closed = TLS.capsule_closed(busy)
      assert hd(Spy.events()) == {:lock, true}
      assert account_events(account) != []
      assert closed.certificate == certificate
      if unquote(damage) == :intact do
        refute closed.data["last_error"]["code"] == "ACME_STORAGE"
      else
        assert closed.data["last_error"]["code"] == "ACME_STORAGE"
        assert closed.job == nil
      end
    end
  end
end
