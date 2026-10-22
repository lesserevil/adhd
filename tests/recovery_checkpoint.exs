# Independent raw-checkpoint vectors. Rejected bytes never reach native DETS.
[baseline, parser, image_table, product_table, work, report | extra] = System.argv()
[modules | _] = String.split(File.read!(baseline), "unless Code.ensure_loaded?(ADHD.CLI)", parts: 2)
Code.compile_string(modules)
Code.compile_file(parser)

defmodule CheckpointVectors do
  import Bitwise
  def sha(b), do: Base.encode16(:crypto.hash(:sha256, b), case: :lower)
  def word(b, p), do: (<<v::32>> = binary_part(b, p, 4); v)
  def put(b, p, v), do: binary_part(b, 0, p) <> <<v::32>> <> binary_part(b, p + 4, byte_size(b) - p - 4)
  def bytes(b, p, value), do: binary_part(b, 0, p) <> value <> binary_part(b, p + byte_size(value), byte_size(b) - p - byte_size(value))
  def seal(b), do: bytes(b, 168, :crypto.hash(:md5, binary_part(b, 12, 156)))
  def slot(b) do
    for i <- 0..255, p = word(b, 312), s = word(b, p), word(b, s + i * 8) != 0, do: {i, s + i * 8, word(b, s + i * 8 + 4)}
  end
  def power(n, p \\ 4), do: if((1 <<< p) >= n, do: p, else: power(n, p + 1))
  # Independently construct a closed one-row v9 collection from the real native
  # table's directory prefix. A successful native lookup validates the builder.
  def object(seed, etf) do
    [{_slot, slot_position, p}] = slot(seed)
    size = byte_size(etf) + 12
    exponent = power(size)
    counters = for i <- 4..31, into: <<>>, do: <<(if i == exponent, do: 1, else: 0)::32>>
    prefix = binary_part(seed, 0, p) |> put(slot_position, size) |> put(0, p + size) |> bytes(56, counters)
    free = for i <- (exponent + 1)..31, into: <<>>, do: <<16::32, 0x03ABCDEF::32, i::32, (p + (1 <<< (i - 1)))::32>>
    b = prefix <> <<size::32, 0x12345678::32, (byte_size(etf) + 4)::32>> <> etf <> free <> <<12::32, 0x03ABCDEF::32, 12345::32>>
    seal(b <> <<(byte_size(b) + 4 - word(seed, 184))::32>>)
  end
  def trace_loop(calls) do
    receive do
      {:trace, _, :call, {:dets, :open_file, args}} -> trace_loop([length(args) | calls])
      {:get, caller} -> send(caller, {:calls, Enum.reverse(calls)}); trace_loop([])
    end
  end
  def collect(tracer) do
    ref = :erlang.trace_delivered(self())
    receive do {:trace_delivered, _, ^ref} -> :ok end
    send(tracer, {:get, self()})
    receive do {:calls, calls} -> calls end
  end
  def check(name, b, expected, work, tracer, overrides \\ %{}) do
    path = Path.join(work, name <> ".dets")
    File.write!(path, b)
    options = Map.merge(%{"max_backup_bytes" => 100_000_000, "scan_batch_records" => 16, "deadline_ms" => System.monotonic_time(:millisecond) + 30_000}, overrides)
    actual = try do
      case ADHD.RecoveryCheckpoint.preflight(b, options) do
        {:ok, safe} ->
          {:ok, table} = :dets.open_file(:checkpoint_vector, [file: String.to_charlist(path), type: :set, access: :read, repair: false])
          try do
            true = (:dets.info(table, :size) == 1)
            [{:state, ^safe}] = :dets.lookup(table, :state)
          after :dets.close(table) end
          :ok
        {:needs_repair, :not_closed} -> :needs_repair
      end
    catch {:recovery, code, reason} -> {code, reason} end
    calls = collect(tracer)
    if actual != expected, do: raise("#{name}: actual #{inspect(actual)} expected #{inspect(expected)}")
    true = (length(calls) == if(expected == :ok, do: 1, else: 0))
    IO.puts("PASS " <> name)
    %{"id" => name, "passed" => true, "result" => inspect(actual), "bytes" => byte_size(b), "sha256" => sha(b), "native_opener_calls" => length(calls)}
  end
  def append_free(b, block) do
    fl = word(b, 0)
    out = binary_part(b, 0, fl) <> block <> binary_part(b, fl, byte_size(b) - fl - 4)
    out <> <<(byte_size(out) + 4 - word(b, 184))::32>>
  end
  def sequence(work) do
    path = Path.join(work, "actual-rewrite-sequence.dets")
    Enum.with_index([64, 6000, 128, 20000, 32, 50000, 1200, 8000]) |> Enum.map(fn {size, i} ->
      {:ok, table} = :dets.open_file(:actual_rewrite_sequence, [file: String.to_charlist(path), type: :set])
      :ok = :dets.insert(table, {:state, %{schema: 4, seq: i, payload: String.duplicate("x", size)}})
      :ok = :dets.sync(table)
      :ok = :dets.close(table)
      {"actual-reopen-grow-shrink-close-#{i}", File.read!(path)}
    end)
  end
  def run(native, image, product, work, fixtures) do
    seed = File.read!(native)
    old = File.read!(image)
    [{slot, slot_pos, ptr}] = slot(seed)
    part = word(seed, 312)
    seg = word(seed, part)
    fl = word(seed, 0)
    small = object(seed, :erlang.term_to_binary({:state, %{schema: 4, seq: 1}}))
    # Read-only snapshots of actual source36 product tables are included as a
    # separate fixture; simple native/image tables isolate format compatibility.
    rewrites = sequence(work)
    tracer = spawn(fn -> trace_loop([]) end)
    Code.ensure_loaded!(:dets)
    true = (:erlang.trace_pattern({:dets, :open_file, :_}, true, [:local]) > 0)
    :erlang.trace(self(), true, [:call, {:tracer, tracer}])
    try do
      small_fl = word(small, 0)
      first_class = word(small, small_fl + 8)
      missing = binary_part(seed, 0, fl) <> binary_part(seed, fl + 16, byte_size(seed) - fl - 20)
      missing = missing <> <<(byte_size(missing) + 4 - word(seed, 184))::32>>
      checked = [
        check("actual-current-runtime-table", seed, :ok, work, tracer),
        check("actual-complete-source36-product-checkpoint", File.read!(product), :ok, work, tracer),
        check("actual-image-otp29-table", old, :ok, work, tracer),
        check("independent-layout-native-equivalence", small, :ok, work, tracer),
        check("header-cp0-no-native-open", put(seed, 8, 0), :needs_repair, work, tracer),
        check("bad-magic", put(seed, 4, 1), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("unknown-version", seal(put(seed, 16, 10)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("unsupported-unchecksummed-layout", bytes(seed, 168, <<0::128>>), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("header-md5", put(seed, 20, 512), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("reserved-header", bytes(seed, 190, <<1>>), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("invalid-linear-hash-recomputed-md5", seal(put(seed, 52, 256)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("huge-slot-count-recomputed-md5", seal(put(seed, 24, 0xFFFFFFFF)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("extra-object-header-count", seal(put(seed, 32, 2)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("bad-bucket-counter", seal(put(seed, 56, 2)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("unknown-hash-method", seal(put(seed, 48, 2)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("missing-part", put(seed, 312, 0), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("part-cycle", put(seed, part, part), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("part-in-header", put(seed, 312, 400), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("segment-out-of-bounds", put(seed, part, byte_size(seed)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("extra-directory-part", put(seed, 316, part), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("extra-segment-pointer", put(seed, part + 4, seg), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("extra-occupied-slot", seed |> put(seg + rem(slot + 1, 256) * 8, word(seed, slot_pos)) |> put(seg + rem(slot + 1, 256) * 8 + 4, ptr), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("active-segment-overlap", put(seed, slot_pos + 4, seg), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("wrong-slot-key-hash", seed |> put(slot_pos, 0) |> put(slot_pos + 4, 0) |> put(seg + rem(slot + 1, 256) * 8, word(seed, slot_pos)) |> put(seg + rem(slot + 1, 256) * 8 + 4, ptr), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("bucket-header-size", put(seed, ptr, word(seed, ptr) + 1), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("inactive-bucket", put(seed, ptr + 4, 0x03ABCDEF), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("invalid-free-class", put(seed, fl + 8, 33), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("free-active-overlap", put(seed, fl + 12, ptr), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("free-free-overlap", put(seed, fl + 28, word(seed, fl + 12)), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("free-block-misaligned-size", put(seed, fl, 15), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("free-block-huge-length", put(seed, fl, 0xFFFFFFFF), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("trailer-size", put(seed, byte_size(seed) - 4, 12), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("extra-trailing-byte", seed <> <<0>>, {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("truncated", binary_part(seed, 0, 187), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("compressed-etf", object(seed, :erlang.term_to_binary({:state, %{payload: String.duplicate("z", 1000)}}, [:compressed])), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("executable-etf", object(seed, :erlang.term_to_binary({:state, %{payload: fn -> :ok end}})), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("pid-etf", object(seed, :erlang.term_to_binary({:state, %{payload: self()}})), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("reference-etf", object(seed, :erlang.term_to_binary({:state, %{payload: make_ref()}})), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("unknown-atom-etf", object(seed, <<131,104,2,119,5,"state",116,0,0,0,1,119,34,"never_create_this_untrusted_atom_x",97,1>>), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("wrong-native-key", object(seed, :erlang.term_to_binary({:other_key, %{}})), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("non-map-state", object(seed, :erlang.term_to_binary({:state, []})), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("etf-trailing-byte", object(seed, :erlang.term_to_binary({:state, %{}}) <> <<0>>), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("etf-huge-map-count", object(seed, <<131,104,2,119,5,"state",116,0xFFFFFFFF::32>>), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("omitted-free-block", missing, {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("free-block-inside-live-padding", append_free(small, <<16::32,0x03ABCDEF::32,5::32,(ptr + 48)::32>>), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("misaligned-buddy-exact-cover", small |> put(small_fl + 12, ptr + 192) |> put(small_fl + 28, ptr + 64), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("forged-arena-base", seed |> put(184, 5448) |> put(byte_size(seed) - 4, byte_size(seed) - 5448), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("unsupported-custom-minimum", seed |> put(20, 512) |> put(24, 512) |> put(40, 512) |> seal(), {"RESTORE_INVALID_BACKUP", "schema"}, work, tracer),
        check("encoded-byte-limit", seed, {"RESTORE_INVALID_BACKUP", "limits"}, work, tracer, %{"max_backup_bytes" => 1}),
        check("expired-deadline", seed, {"RESTORE_TIMEOUT", "timeout"}, work, tracer, %{"deadline_ms" => System.monotonic_time(:millisecond) - 1})
      ]
      # The supported legacy hash method is exercised against a native opener,
      # not merely accepted syntactically by the preflight implementation.
      [{old_slot, old_pos, _}] = slot(small)
      legacy_slot = rem(apply(:erlang, :phash, [:state, 0x03FFFFFF]) - 1, 256)
      legacy = small |> put(48, 0) |> put(old_pos, 0) |> put(old_pos + 4, 0) |> put(seg + legacy_slot * 8, word(small, old_pos)) |> put(seg + legacy_slot * 8 + 4, ptr) |> seal()
      true = (old_slot in 0..255)
      true = (first_class == 7)
      more = Enum.map(rewrites, fn {name, b} -> check(name, b, :ok, work, tracer) end)
      retained = Enum.with_index(fixtures) |> Enum.map(fn {path, i} -> check("actual-retained-product-#{i}", File.read!(path), :ok, work, tracer) |> Map.put("fixture", path) end)
      checked ++ [check("legacy-phash-native-equivalence", legacy, :ok, work, tracer)] ++ more ++ retained
    after
      :erlang.trace(self(), false, [:call])
      :erlang.trace_pattern({:dets, :open_file, :_}, false, [:local])
      Process.exit(tracer, :normal)
    end
  end
end
File.mkdir_p!(work)
native = Path.join(work, "native-production.dets")
{:ok, table} = :dets.open_file(:native_production, [file: String.to_charlist(native), type: :set])
:ok = :dets.insert(table, {:state, %{schema: 4, project: "actual-otp27-checkpoint", seq: 1, values: [1,2,"three"]}})
:ok = :dets.sync(table)
:ok = :dets.close(table)
fixtures = case extra do
  [path] -> ADHD.JSON.decode!(File.read!(path))
  [] -> []
end
checks = CheckpointVectors.run(native, image_table, product_table, work, fixtures)
try do
  :erlang.binary_to_existing_atom("never_create_this_untrusted_atom_x", :utf8)
  raise "untrusted atom unexpectedly exists"
rescue ArgumentError -> :ok end
output = %{"schema" => "adhd/recovery-checkpoint-validation@1", "passed" => true,
  "scope" => "Pure raw DETSv9 preflight and actual read-only native lookup equality; no full recovery-service or resource-isolation claim",
  "parser_sha256" => CheckpointVectors.sha(File.read!(parser)), "harness_sha256" => CheckpointVectors.sha(File.read!(__ENV__.file)),
  "baseline_sha256" => CheckpointVectors.sha(File.read!(baseline)), "otp_release" => List.to_string(:erlang.system_info(:otp_release)),
  "erts_version" => List.to_string(:erlang.system_info(:version)), "checks" => checks,
  "image_checkpoint_sha256" => CheckpointVectors.sha(File.read!(image_table)), "image_producer_identity" => "sha256:84b8e414c05a4ff0051ce5c69511e4681c932c70c8d617568d2fcdb5659e859b",
  "image_producer_otp" => "29", "image_producer_erts" => "17.1.1",
  "complete_product_checkpoint_sha256" => CheckpointVectors.sha(File.read!(product_table)),
  "prior_attempts" => [%{"id" => "vectors01", "result" => "harness failed: synthetic builder omitted nonzero FlBase subtraction; both actual runtime tables passed"}, %{"id" => "vectors02", "result" => "PASS45, unknown-atom vector had length mismatch and only established structural rejection; corrected in current run"}]}
File.write!(report, JSON.encode!(output))
IO.puts("PASS #{length(checks)} raw-checkpoint groups")
