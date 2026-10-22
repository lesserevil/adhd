# Packaging-only compiler. Never evaluates the application's command dispatcher.
source = "/app/hub.exs"
wrapper = "/image-root"
output = wrapper <> "/runtime/adhd"
fail = fn -> raise "Invalid precompiled application input" end
regular = fn path ->
  case File.lstat(path) do
    {:ok, %{type: :regular, links: 1}} -> File.read!(path)
    _ -> fail.()
  end
end
Enum.each(["/app", "/packaging"], fn path ->
  case File.lstat(path) do
    {:ok, %{type: :directory, uid: 0, mode: mode}} when :erlang.band(mode, 0o022) == 0 -> :ok
    _ -> fail.()
  end
end)
sha = fn bytes -> :crypto.hash(:sha256, bytes) |> Base.encode16(case: :lower) end
inputs_bytes = regular.("/packaging/inputs.json")
inputs = JSON.decode!(inputs_bytes)
acme_files = ~w(LICENSE.lego LICENSE.musl acme-build.json acme-bundle.json acme-guard acme-pins.json lego lego-sbom.json)
has_acme = inputs["schema"] == "adhd/container-compiler-inputs@2"
expected_files = Enum.sort(["boot.exs", "build.exs"] ++ if(has_acme, do: acme_files, else: []))
if Enum.sort(Map.keys(inputs)) != Enum.sort(~w(schema source_sha256 payload_manifest_sha256 files)) or
   inputs["schema"] not in ["adhd/container-compiler-inputs@1", "adhd/container-compiler-inputs@2"] or
   Enum.sort(Map.keys(inputs["files"])) != expected_files or
   Enum.sort(File.ls!("/packaging")) != Enum.sort(["inputs.json" | expected_files]), do: fail.()
Enum.each(inputs["files"], fn {name, digest} ->
  if sha.(regular.("/packaging/" <> name)) != digest, do: fail.()
end)
bytes = regular.(source)
if sha.(bytes) != inputs["source_sha256"] or
   sha.(regular.("/app/manifest.json")) != inputs["payload_manifest_sha256"], do: fail.()
ast = Code.string_to_quoted!(bytes, file: source)
forms = case ast do {:__block__, _, entries} -> entries; entry -> [entry] end
{modules, tail} = Enum.split_while(forms, &match?({:defmodule, _, _}, &1))
if modules == [] or tail == [] or Enum.any?(tail, &match?({:defmodule, _, _}, &1)), do: fail.()
names = Enum.map(modules, fn
  {:defmodule, _, [{:__aliases__, _, parts}, [do: _]]} when is_list(parts) ->
    if not Enum.all?(parts, &is_atom/1), do: fail.()
    Module.concat(parts)
  _ -> fail.()
end)
if length(names) != length(Enum.uniq(names)), do: fail.()
if ADHD.ACMEClient in names and not has_acme, do: fail.()
# No global lexical environment may be silently lost at this boundary.
if Enum.any?(tail, &match?({op, _, _} when op in [:alias, :import, :require, :use], &1)), do: fail.()
if File.exists?(wrapper), do: fail.()
File.mkdir_p!(Path.join(output, "ebin"))
compiled = Enum.flat_map(modules, &Code.compile_quoted(&1, source))
if Enum.map(compiled, &elem(&1, 0)) != names, do: fail.()
beams = Map.new(compiled, fn {name, binary} ->
  filename = Atom.to_string(name) <> ".beam"
  File.write!(Path.join([output, "ebin", filename]), binary, [:exclusive])
  {filename, sha.(binary)}
end)
boot = regular.("/packaging/boot.exs")
File.write!(Path.join(output, "boot.exs"), boot, [:exclusive])
File.write!(Path.join(output, "build.exs"), regular.("/packaging/build.exs"), [:exclusive])
File.write!(Path.join(output, "inputs.json"), inputs_bytes, [:exclusive])
# Runtime anchors bind the VM and the compiler/runtime modules used by this cache.
anchors = ["/proc/self/exe" | Enum.map([Kernel, Code, JSON, :elixir], &to_string(:code.which(&1)))]
toolchain = %{
  "elixir" => System.version(), "otp" => to_string(:erlang.system_info(:otp_release)),
  "erts" => to_string(:erlang.system_info(:version)),
  "architecture" => to_string(:erlang.system_info(:system_architecture)),
  "anchors" => Map.new(anchors, fn path -> {path, sha.(File.read!(path))} end)
}
acme = if has_acme, do: Map.take(inputs["files"], acme_files), else: %{}
Enum.each(acme, fn {name, _digest} ->
  File.write!(Path.join(output, name), regular.("/packaging/" <> name), [:exclusive])
end)
manifest = %{
  "schema" => "adhd/precompiled-cache@1", "source" => source,
  "source_sha256" => sha.(bytes), "payload_manifest_sha256" => sha.(regular.("/app/manifest.json")),
  "inputs_sha256" => sha.(inputs_bytes), "boot_sha256" => sha.(boot), "build_sha256" => sha.(regular.("/packaging/build.exs")),
  "modules" => Enum.map(names, &Atom.to_string/1), "beams" => beams, "toolchain" => toolchain
}
manifest = if has_acme, do: Map.merge(manifest, %{"schema" => "adhd/precompiled-cache@2", "acme" => acme}), else: manifest
File.write!(Path.join(output, "manifest.json"), JSON.encode!(manifest), [:exclusive])
Enum.each(Path.wildcard(output <> "/**/*"), fn path ->
  File.chmod!(path, if(File.dir?(path) or Path.basename(path) in ["acme-guard", "lego"], do: 0o555, else: 0o444))
end)
File.chmod!(output, 0o555)

# RUN/COPY output timestamps must not inherit wall clock build time.
Enum.each([wrapper, wrapper <> "/runtime", output | Path.wildcard(output <> "/**/*")], fn path ->
  File.touch!(path, 0)
end)
