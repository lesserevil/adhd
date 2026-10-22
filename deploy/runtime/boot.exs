# Generic cache loader: the application tail and its argv remain application-owned.
source = "/app/hub.exs"
root = "/runtime/adhd"
fail = fn -> raise "Invalid precompiled application cache" end
regular = fn path ->
  case File.lstat(path) do
    {:ok, %{type: :regular, links: 1, uid: 0, mode: mode}} when :erlang.band(mode, 0o222) == 0 -> File.read!(path)
    _ -> fail.()
  end
end
sha = fn bytes -> :crypto.hash(:sha256, bytes) |> Base.encode16(case: :lower) end
# Docker payload files remain 0644/root-owned; cache files are immutable 0444.
payload = fn path -> case File.lstat(path) do
  {:ok, %{type: :regular, links: 1, uid: 0, mode: mode}} when :erlang.band(mode, 0o022) == 0 -> File.read!(path)
  _ -> fail.()
end end
source_bytes = payload.(source)
case System.argv() do
  [^source | rest] -> System.argv(rest)
  _ -> fail.()
end
Enum.each(["/runtime", root, root <> "/ebin", "/app"], fn path ->
  case File.lstat(path) do
    {:ok, %{type: :directory, uid: 0, mode: mode}} when :erlang.band(mode, 0o022) == 0 -> :ok
    _ -> fail.()
  end
end)
manifest = regular.(root <> "/manifest.json") |> JSON.decode!()
has_acme = manifest["schema"] == "adhd/precompiled-cache@2"
acme_files = ~w(LICENSE.lego LICENSE.musl acme-build.json acme-bundle.json acme-guard acme-pins.json lego lego-sbom.json)
expected_keys = ~w(schema source source_sha256 payload_manifest_sha256 inputs_sha256 boot_sha256 build_sha256 modules beams toolchain) ++ if(has_acme, do: ["acme"], else: [])
if Enum.sort(Map.keys(manifest)) != Enum.sort(expected_keys), do: fail.()
if manifest["schema"] not in ["adhd/precompiled-cache@1", "adhd/precompiled-cache@2"] or manifest["source"] != source or
   manifest["source_sha256"] != sha.(source_bytes) or manifest["boot_sha256"] != sha.(regular.(root <> "/boot.exs")) or
   manifest["payload_manifest_sha256"] != sha.(payload.("/app/manifest.json")), do: fail.()
if Enum.sort(File.ls!(root)) != Enum.sort(["boot.exs", "build.exs", "ebin", "inputs.json", "manifest.json"] ++ if(has_acme, do: acme_files, else: [])), do: fail.()
if manifest["build_sha256"] != sha.(regular.(root <> "/build.exs")) or
   manifest["inputs_sha256"] != sha.(regular.(root <> "/inputs.json")), do: fail.()
inputs = regular.(root <> "/inputs.json") |> JSON.decode!()
if Enum.sort(Map.keys(inputs)) != Enum.sort(~w(schema source_sha256 payload_manifest_sha256 files)) or
   inputs["schema"] != (if(has_acme, do: "adhd/container-compiler-inputs@2", else: "adhd/container-compiler-inputs@1")) or
   inputs["source_sha256"] != manifest["source_sha256"] or
   inputs["payload_manifest_sha256"] != manifest["payload_manifest_sha256"] or
   inputs["files"] != Map.merge(%{"boot.exs" => manifest["boot_sha256"], "build.exs" => manifest["build_sha256"]}, if(has_acme, do: manifest["acme"], else: %{})), do: fail.()
if has_acme do
  if Enum.sort(Map.keys(manifest["acme"])) != Enum.sort(acme_files), do: fail.()
  Enum.each(manifest["acme"], fn {name, digest} ->
    path = root <> "/" <> name
    if sha.(regular.(path)) != digest, do: fail.()
    expected_mode = if name in ["acme-guard", "lego"], do: 0o555, else: 0o444
    if :erlang.band(File.stat!(path).mode, 0o7777) != expected_mode, do: fail.()
  end)
end
toolchain = manifest["toolchain"]
if Enum.sort(Map.keys(toolchain)) != Enum.sort(~w(elixir otp erts architecture anchors)) or
   toolchain["elixir"] != System.version() or toolchain["otp"] != to_string(:erlang.system_info(:otp_release)) or
   toolchain["erts"] != to_string(:erlang.system_info(:version)) or
   toolchain["architecture"] != to_string(:erlang.system_info(:system_architecture)), do: fail.()
anchors = ["/proc/self/exe" | Enum.map([Kernel, Code, JSON, :elixir], &to_string(:code.which(&1)))]
if Enum.sort(Map.keys(toolchain["anchors"])) != Enum.sort(anchors), do: fail.()
Enum.each(anchors, fn path -> if sha.(File.read!(path)) != toolchain["anchors"][path], do: fail.() end)
ast = Code.string_to_quoted!(source_bytes, file: source)
forms = case ast do {:__block__, _, entries} -> entries; entry -> [entry] end
{modules, tail} = Enum.split_while(forms, &match?({:defmodule, _, _}, &1))
if modules == [] or tail == [] or Enum.any?(tail, &match?({:defmodule, _, _}, &1)), do: fail.()
names = Enum.map(modules, fn
  {:defmodule, _, [{:__aliases__, _, parts}, [do: _]]} when is_list(parts) ->
    if not Enum.all?(parts, &is_atom/1), do: fail.()
    Module.concat(parts)
  _ -> fail.()
end)
if length(Enum.uniq(names)) != length(names) or Enum.map(names, &Atom.to_string/1) != manifest["modules"], do: fail.()
if ADHD.ACMEClient in names and not has_acme, do: fail.()
if Enum.any?(tail, &match?({op, _, _} when op in [:alias, :import, :require, :use], &1)), do: fail.()
files = Enum.map(names, &(Atom.to_string(&1) <> ".beam"))
if Enum.sort(File.ls!(root <> "/ebin")) != Enum.sort(files) or Enum.sort(Map.keys(manifest["beams"])) != Enum.sort(files), do: fail.()
# Validate the entire closure before loading any application module.
binaries = Enum.zip(names, files) |> Enum.map(fn {name, file} ->
  path = root <> "/ebin/" <> file
  binary = regular.(path)
  if sha.(binary) != manifest["beams"][file] or Code.ensure_loaded?(name), do: fail.()
  {name, path, binary}
end)
Enum.each(binaries, fn {name, path, binary} ->
  case :code.load_binary(name, to_charlist(path), binary) do
    {:module, ^name} -> :ok
    _ -> fail.()
  end
end)
Code.eval_quoted({:__block__, [], tail}, [], file: source)
