defmodule ACMEPassiveObserver do
  @maximum 8_388_608
  @lifetime 600_000
  # Only integer arities survive; argument-list stack frames are discarded.
  def mfa({module, function, arity}) when is_atom(module) and is_atom(function) and is_integer(arity),
    do: [Atom.to_string(module), Atom.to_string(function), arity]
  def mfa({module, function, arity, _location}), do: mfa({module, function, arity})
  def mfa(_), do: nil
  def sanitize(info) do
    info = Map.new(info)
    %{"function" => mfa(info[:current_function]),
      "stack" => Enum.map(Enum.take(info[:current_stacktrace] || [], 32), &mfa/1) |> Enum.reject(&is_nil/1),
      "status" => if(is_atom(info[:status]), do: Atom.to_string(info[:status]), else: nil),
      "queue" => integer(info[:message_queue_len]), "reductions" => integer(info[:reductions])}
  end
  defp integer(n) when is_integer(n) and n >= 0, do: n
  defp integer(_), do: nil
  def start(path) do
    parent = self()
    pid = spawn(fn ->
      {:ok, file} = :file.open(String.to_charlist(path), [:write, :exclusive, :binary, :raw])
      File.chmod!(path, 0o600)
      try do
        header = JSON.encode!(%{"schema" => "adhd/acme-passive-stack@1", "interval_ms" => 100,
          "lifetime_ms" => @lifetime, "maximum_bytes" => @maximum}) <> "\n"
        :ok = :file.write(file, header)
        send(parent, {:observer_ready, self()})
        loop(file, System.monotonic_time(:millisecond) + @lifetime, byte_size(header))
      after
        :file.close(file)
      end
    end)
    monitor = Process.monitor(pid)
    receive do
      {:observer_ready, ^pid} -> Process.demonitor(monitor, [:flush]); :ok
      {:DOWN, ^monitor, :process, ^pid, _} -> raise "passive observer setup failed"
    after 1000 -> raise "passive observer setup deadline" end
  end
  defp loop(file, deadline, used) do
    now = System.monotonic_time(:millisecond)
    rows = for module <- [ADHD.TLS, ADHD.Config] do
      case Process.whereis(module) do
        nil -> %{"module" => Atom.to_string(module), "present" => false}
        pid ->
          info = Process.info(pid, [:current_function, :current_stacktrace, :status, :message_queue_len, :reductions])
          Map.merge(%{"module" => Atom.to_string(module), "present" => info != nil,
            "pid" => :erlang.pid_to_list(pid) |> List.to_string()}, sanitize(info || []))
      end
    end
    bytes = JSON.encode!(%{"at_monotonic_ms" => now, "processes" => rows}) <> "\n"
    if now < deadline and used + byte_size(bytes) <= @maximum do
      :ok = :file.write(file, bytes)
      receive do :stop -> :ok after 100 -> loop(file, deadline, used + byte_size(bytes)) end
    end
  end
end
