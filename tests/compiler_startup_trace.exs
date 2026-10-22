# Diagnostic only: public Elixir compiler tracing, no ADHD functions or patches.
# Loaded with `elixir -r THIS_FILE /app/hub.exs ORIGINAL_SERVE_ARGUMENT`.
# https://elixir.hexdocs.pm/1.20.4/Code.html#module-compilation-tracers
# Callback work is bounded; writes happen in an independent owned logger.
defmodule ADHDTest.PublicCompilerTrace do
  @maximum_events 4096
  @maximum_bytes 1_048_576

  def install(path) do
    true = Path.type(path) == :absolute
    start = System.monotonic_time(:microsecond)
    wall = System.system_time(:microsecond)
    parent = self()
    logger = spawn_link(fn ->
      {:ok, io} = :file.open(String.to_charlist(path), [:write, :exclusive, :binary, :raw])
      :ok = File.chmod(path, 0o600)
      :ok = :file.write(io, "installed\t#{start}\t#{wall}\t#{System.pid()}\n")
      send(parent, {:compiler_trace_logger_ready, self()})
      loop(io, start, 0)
    end)
    receive do
      {:compiler_trace_logger_ready, ^logger} -> :ok
    after
      1_000 -> raise "Private compiler trace logger unavailable"
    end
    counter = :atomics.new(1, [])
    :persistent_term.put(__MODULE__, {logger, counter, start})
    Code.put_compiler_option(:tracers, [__MODULE__ | Code.get_compiler_option(:tracers)])
    :ok
  end

  def trace(event, env) when event in [:start, :stop, :defmodule], do: record(event, env)
  def trace({:on_module, _bytecode, _metadata}, env), do: record(:on_module, env)
  def trace(_event, _env), do: :ok

  defp record(event, env) do
    {logger, counter, start} = :persistent_term.get(__MODULE__)
    count = :atomics.add_get(counter, 1, 1)
    if count <= @maximum_events do
      send(logger, {:event, count, System.monotonic_time(:microsecond) - start,
                    event, env.module, env.file, env.line})
    else
      if count == @maximum_events + 1, do: send(logger, :event_limit)
    end
    :ok
  end

  defp loop(io, start, bytes) do
    receive do
      {:event, count, elapsed, event, module, file, line} ->
        # No source text, bytecode, arguments, state or credentials are recorded.
        mod = bounded(inspect(module), 256)
        filename = bounded(Path.basename(file), 128)
        row = "#{count}\t#{elapsed}\t#{event}\t#{mod}\t#{filename}\t#{line}\n"
        if bytes + byte_size(row) <= @maximum_bytes do
          :ok = :file.write(io, row)
          loop(io, start, bytes + byte_size(row))
        else
          :ok = :file.write(io, "byte_limit\n")
          discard(io)
        end
      :event_limit ->
        :ok = :file.write(io, "event_limit\n")
        discard(io)
    end
  end

  defp discard(io) do
    receive do
      _ -> discard(io)
    end
  end

  defp bounded(text, limit) do
    text |> String.replace(["\t", "\r", "\n"], " ") |> String.slice(0, limit)
  end
end

ADHDTest.PublicCompilerTrace.install(System.fetch_env!("ADHD_COMPILER_TRACE_FILE"))
