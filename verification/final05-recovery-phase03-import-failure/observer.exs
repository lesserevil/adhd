# Diagnostic only. Load before the exact immutable compiled boot using elixir -r.
# Trace payload arguments/results are never serialized or written.
defmodule ADHDTestRecoveryPhaseObserver do
  @functions [
    {ADHD.ProjectRestore, :prepare_apply, 5},
    {ADHD.RecoveryFiles, :mkdir_private, 2},
    {ADHD.Storage, :write_closed, 2},
    {ADHD.Storage, :persist, 3},
    {ADHD.Storage, :read_snapshot, 1},
    {ADHD.RecoveryFiles, :read, 3},
    {ADHD.RecoveryCheckpoint, :preflight, 2},
    {ADHD.RecoveryFiles, :fingerprint, 2},
    {ADHD.Eventing, :preflight_restore, 2},
    {ADHD.Eventing, :provision, 2},
    {ADHD.Eventing, :provision, 3},
    {ADHD.Eventing, :request, 4},
    {ADHD.Eventing, :request, 5},
    {ADHD.Eventing, :request, 6},
    {ADHD.Eventing, :request_now, 7},
    {ADHD.Eventing, :response, 4},
    {ADHD.Eventing, :success, 1}
  ]
  def start do
    path = System.fetch_env!("ADHD_TEST_PHASE_LOG")
    nonce = System.fetch_env!("ADHD_TEST_PHASE_NONCE")
    true = Regex.match?(~r/\A[a-f0-9]{32}\z/, nonce)
    parent = self()
    ref = make_ref()
    spawn(fn ->
      {:ok, fd} = :file.open(String.to_charlist(path), [:write, :exclusive, :raw, :binary])
      :ok = File.chmod(path, 0o600)
      send(parent, {ref, :opened})
      try do
        emit(fd, ["header", nonce, "source-unchanged-compiled-diagnostic"])
        await_modules(1500)
        spec = [{:_, [], [{:return_trace}, {:exception_trace}]}]
        Enum.each(@functions, fn mfa ->
          count = :erlang.trace_pattern(mfa, spec, [:local])
          true = is_integer(count) and count > 0
        end)
        :erlang.trace(:all, true, [:call, :arity, {:tracer, self()}])
        :erlang.trace(:new, true, [:call, :arity, {:tracer, self()}])
        emit(fd, ["ready", nonce, Integer.to_string(length(@functions)) <> "-mfa-patterns"])
        collect(fd, 0, System.monotonic_time(:millisecond) + 1800000)
      catch
        _, _ -> emit(fd, ["observer-failed", nonce, "redacted"])
      after
        Enum.each(@functions, fn mfa -> :erlang.trace_pattern(mfa, false, [:local]) end)
        :erlang.trace(:all, false, [:call])
        :erlang.trace(:new, false, [:call])
        :file.sync(fd)
        :file.close(fd)
      end
    end)
    receive do
      {^ref, :opened} -> :ok
    after
      1000 -> raise "Diagnostic output could not be opened"
    end
  end
  defp await_modules(0), do: throw(:modules_not_ready)
  defp await_modules(n) do
    if Enum.all?(@functions, fn {m, _, _} -> :code.is_loaded(m) != false end) do
      :ok
    else
      Process.sleep(20)
      await_modules(n - 1)
    end
  end
  defp emit(fd, fields) do
    line = Enum.join([Integer.to_string(System.monotonic_time(:microsecond)) | fields], "|") <> "\n"
    true = byte_size(line) <= 240
    :ok = :file.write(fd, line)
  end
  defp collect(fd, count, deadline) when count < 256 do
    remaining = max(0, deadline - System.monotonic_time(:millisecond))
    receive do
      {:trace, pid, :call, {m, f, a} = mfa} when is_integer(a) ->
        if mfa in @functions and File.exists?(System.fetch_env!("ADHD_TEST_PHASE_ARM")) do
          emit(fd, ["call", inspect(pid), inspect(m), Atom.to_string(f), Integer.to_string(a)])
          collect(fd, count + 1, deadline)
        else
          collect(fd, count, deadline)
        end
      {:trace, pid, :return_from, {m, f, a} = mfa, result} ->
        if mfa in @functions and File.exists?(System.fetch_env!("ADHD_TEST_PHASE_ARM")) do
          emit(fd, ["return", inspect(pid), inspect(m), Atom.to_string(f), Integer.to_string(a), safe_status(m, f, result)])
          collect(fd, count + 1, deadline)
        else
          collect(fd, count, deadline)
        end
      {:trace, pid, :exception_from, {m, f, a} = mfa, {class, reason}} ->
        if mfa in @functions and File.exists?(System.fetch_env!("ADHD_TEST_PHASE_ARM")) do
          emit(fd, ["exception", inspect(pid), inspect(m), Atom.to_string(f), Integer.to_string(a), safe_class(class), safe_reason(reason)])
          collect(fd, count + 1, deadline)
        else
          collect(fd, count, deadline)
        end
      _ -> collect(fd, count, deadline)
    after
      remaining -> emit(fd, ["expired", "diagnostic-incomplete"])
    end
  end
  defp collect(fd, _, _), do: emit(fd, ["limit", "diagnostic-incomplete"])
  defp safe_status(ADHD.Eventing, f, {status, _}) when f in [:request, :request_now, :response] and is_integer(status) and status in 100..599, do: Integer.to_string(status)
  defp safe_status(_, _, _), do: "redacted"
  defp safe_class(value) when value in [:error, :exit, :throw], do: Atom.to_string(value)
  defp safe_class(_), do: "redacted"
  defp safe_reason(value) when value in [:enoent, :eacces, :eperm, :eexist, :enospc, :badarg, :emfile, :enfile, :eio, :timeout], do: Atom.to_string(value)
  defp safe_reason({:badmatch, {:error, value}}) when value in [:enoent, :eacces, :eperm, :eexist, :enospc, :emfile, :enfile, :eio], do: "badmatch/" <> Atom.to_string(value)
  defp safe_reason(%File.Error{reason: value}) when value in [:enoent, :eacces, :eperm, :eexist, :enospc, :emfile, :enfile, :eio], do: "file/" <> Atom.to_string(value)
  defp safe_reason({:recovery, code, _}) when code in ["RESTORE_IO_ERROR", "RESTORE_INVALID_BACKUP", "RESTORE_CONFLICT", "RESTORE_UNAVAILABLE", "RESTORE_TIMEOUT"], do: code
  defp safe_reason({:eventing, code}) when code in ["BROKER_REQUEST_FAILED", "TOPIC_CREATE_FAILED", "TOPIC_UNAVAILABLE", "BROKER_UNAVAILABLE", "BROKER_TIMEOUT", "BROKER_RESPONSE_TOO_LARGE"], do: code
  defp safe_reason({:domain, code}) when code in ["EVENTING_UNAVAILABLE", "BACKPRESSURE", "INVALID_REQUEST"], do: code
  defp safe_reason(_), do: "redacted"
end
:ok = ADHDTestRecoveryPhaseObserver.start()
