# Independent boundary checks against generated recovery source, without a hub,
# writable DETS, network/model calls, or importing untrusted source artifacts.
[source,work] = System.argv()
File.mkdir_p!(work)
System.put_env("ADHD_PRIMITIVE_WORK",Path.expand(work))
Code.compiler_options(no_warn_undefined: :all)
for name <- ~w(domain project_backup), do: Code.require_file(Path.join(source,name<>".exs"))
ExUnit.start()
defmodule RecoveryPrimitiveTests do
  use ExUnit.Case
  alias ADHD.ProjectBackup,as: B
  alias ADHD.RecoveryFiles,as: F
  def frame(term) do
    bytes=:erlang.term_to_binary(term)
    <<"ADHDSTATE",1,(:crypto.hash(:sha256,bytes))::binary,bytes::binary>>
  end
  test "safe framing preserves native state and rejects unsafe/trailing/compressed values" do
    assert B.decode_snapshot(frame(%{schema: 3,example: [1,"original",{:actor,"mid"}]}))==%{schema: 3,example: [1,"original",{:actor,"mid"}]}
    assert B.decode_snapshot(frame(%{schema: 3,ready: MapSet.new(["event-1"])})).ready==MapSet.new(["event-1"])
    for term<-[%{schema: 3,job: self()},%{schema: 3,job: make_ref()},%{schema: 3,job: fn->:unsafe end},%{schema: 9},%{schema: 3,ready: %{__struct__: MapSet,map: %{bad: true}}},%{schema: 3,ready: %{__struct__: MapSet,map: %{},version: 2}}] do
      assert catch_throw(B.decode_snapshot(frame(term)))=={:recovery,"RESTORE_INVALID_BACKUP","schema"}
    end
    compressed=:erlang.term_to_binary(%{schema: 3,data: String.duplicate("x",10000)},[:compressed])
    assert catch_throw(B.decode_snapshot(<<"ADHDSTATE",1,(:crypto.hash(:sha256,compressed))::binary,compressed::binary>>))=={:recovery,"RESTORE_INVALID_BACKUP","limits"}
    body=:erlang.term_to_binary(%{schema: 3})<>"trailing"
    assert catch_throw(B.decode_snapshot(<<"ADHDSTATE",1,(:crypto.hash(:sha256,body))::binary,body::binary>>))=={:recovery,"RESTORE_INVALID_BACKUP","schema"}
  end
  test "regular private no-link files are exact length/hash and leave bytes unchanged" do
    dir=Path.join(System.get_env("ADHD_PRIMITIVE_WORK"),"files-"<>Integer.to_string(System.unique_integer([:positive])))
    File.mkdir_p!(dir);File.chmod!(dir,0o700);path=Path.join(dir,"payload")
    try do
      File.write!(path,"exact bytes");File.chmod!(path,0o600);uid=File.stat!(path).uid
      assert {"exact bytes",_}=F.read(path,11,uid,%{"bytes"=>11,"sha256"=>F.sha("exact bytes")})
      assert catch_throw(F.read(path,10,uid))=={:recovery,"RESTORE_INVALID_BACKUP","limits"}
      assert catch_throw(F.read(path,11,uid,%{"bytes"=>11,"sha256"=>String.duplicate("0",64)}))=={:recovery,"RESTORE_INVALID_BACKUP","hash"}
      File.ln!(path,Path.join(dir,"hardlink"));assert catch_throw(F.read(path,11,uid))=={:recovery,"RESTORE_INVALID_BACKUP","path"}
      File.rm!(Path.join(dir,"hardlink"));File.ln_s!(path,Path.join(dir,"symlink"));assert catch_throw(F.read(Path.join(dir,"symlink"),11,uid))=={:recovery,"RESTORE_INVALID_BACKUP","path"}
      assert File.read!(path)=="exact bytes"
    after File.rm_rf!(dir) end
  end
  test "duplicate JSON keys and malformed UTF8 are rejected" do
    assert catch_throw(F.json(~s({"x":1,"x":2})))=={:recovery,"RESTORE_INVALID_BACKUP","schema"}
    assert catch_throw(F.json(<<255>>))=={:recovery,"RESTORE_INVALID_BACKUP","schema"}
  end
end
