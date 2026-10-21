# A controlled local writer freeze with real HTTP/A2A clients. This does not
# claim a black-box relocation fault; separate syscall-kill suites prove those.
[artifact,root]=System.argv()
[modules,_]=String.split(File.read!(artifact),"\nunless Code.ensure_loaded?(ADHD.CLI)",parts: 2)
Code.compile_string(modules,artifact)
{:ok,_}=Application.ensure_all_started(:inets)
{:ok,_}=Application.ensure_all_started(:ssl)
if File.exists?(root),do: raise("Fixture directory must be fresh")
File.mkdir_p!(root)
{:ok,probe}=:gen_tcp.listen(0,[:binary,active: false,ip: {127,0,0,1}])
{:ok,{_,port}}=:inet.sockname(probe)
:gen_tcp.close(probe)
token=Base.url_encode64(:crypto.strong_rand_bytes(32),padding: false)
admin=Base.url_encode64(:crypto.strong_rand_bytes(32),padding: false)
c=ADHD.Config.validate(%{"server_id"=>String.duplicate("b",32),"project_id"=>"red","projects"=>[%{"id"=>"red","name"=>"Red"},%{"id"=>"blue","name"=>"Blue"}],"host"=>"127.0.0.1","port"=>port,"agents"=>%{"agent"=>token},"agent_projects"=>%{"agent"=>["red"]},"admin_token"=>admin,"matcher"=>nil,"federation"=>%{"description"=>"Wire fixture","peers"=>[%{"project_id"=>"remote","url"=>"http://127.0.0.1:1","token"=>String.duplicate("p",36),"inbound_token"=>String.duplicate("q",36)}]},"eventing"=>%{"enabled"=>false},"store_path"=>Path.join(root,"old.dets")},root)
:persistent_term.put({ADHD.Config,:config},c)
{:ok,_}=ADHD.Store.start_link(c)
ADHD.Projects.prepare(c,c)
{:ok,server}=ADHD.Server.start_link(c)
check=fn value->if not value,do: raise("HTTP freeze invariant failed") end
request=fn path,credential,body->
  {:ok,socket}=:gen_tcp.connect({127,0,0,1},port,[:binary,active: false],3000)
  content=JSON.encode!(body)
  head="POST "<>path<>" HTTP/1.1\r\nHost: 127.0.0.1:"<>to_string(port)<>"\r\nAuthorization: Bearer "<>credential<>"\r\nContent-Type: application/json\r\nContent-Length: "<>to_string(byte_size(content))<>"\r\nConnection: close\r\n\r\n"
  :ok=:gen_tcp.send(socket,head<>content)
  receive_all=fn again,acc->case :gen_tcp.recv(socket,0,5000) do
    {:ok,part}->if byte_size(acc)+byte_size(part)>1048576,do: raise("Unexpected oversized response"),else: again.(again,acc<>part)
    {:error,:closed}->acc
    _->raise("HTTP response deadline exceeded")
  end end
  response=receive_all.(receive_all,"");:gen_tcp.close(socket)
  [head,bytes]=String.split(response,"\r\n\r\n",parts: 2)
  [status_line|headers]=String.split(head,"\r\n")
  [_,status|_]=String.split(status_line," ")
  hs=Map.new(headers,fn line->[key,value]=String.split(line,":",parts: 2);{String.downcase(key),String.trim(value)} end)
  {String.to_integer(status),hs,ADHD.JSON.decode!(bytes)}
end
rpc=fn command,mid->%{"jsonrpc"=>"2.0","id"=>"wire-freeze","method"=>"SendMessage","params"=>%{"message"=>%{"messageId"=>mid,"role"=>"ROLE_USER","parts"=>[%{"data"=>command}]}}} end
command=%{"op"=>"publish","project_id"=>"red","text"=>"Retry identical rejected mutation"}
mid="freeze-retry-message"
passed=[]
try do
  moves=ADHD.Store.prepare_moves(Map.put(c,"store_path",Path.join(root,"new.dets")),c)
  {status,headers,value}=request.("/admin/api",admin,%{"op"=>"overview","project_id"=>"red"})
  check.(status==503 and headers["retry-after"]=="1" and value["error"]["code"]=="CONFIG_APPLY_IN_PROGRESS")
  passed=["admin-http-rejects-frozen-writer-with-503-and-bounded-retry-after"|passed]
  {status,_,value}=request.("/a2a",token,rpc.(command,mid))
  check.(status==200 and value["error"]["code"] == -32000)
  check.(Enum.any?(value["error"]["data"],fn info->get_in(info,["metadata","code"])=="CONFIG_APPLY_IN_PROGRESS" end))
  passed=["a2a-preserves-jsonrpc-service-error-and-retryable-domain-identity"|passed]
  ADHD.Store.abort_moves(moves)
  state=ADHD.Scope.with_project("red",fn->ADHD.Store.snapshot() |> ADHD.Store.unwrap() end)
  check.(map_size(state.publications)==0 and not Map.has_key?(state.idempotency,{"agent",mid}))
  {200,_,first}=request.("/a2a",token,rpc.(command,mid))
  {200,_,second}=request.("/a2a",token,rpc.(command,mid))
  check.(is_map(first["result"]) and is_map(second["result"]))
  check.(get_in(first,["result","message","parts"])==get_in(second,["result","message","parts"]))
  state=ADHD.Scope.with_project("red",fn->ADHD.Store.snapshot() |> ADHD.Store.unwrap() end)
  check.(map_size(state.publications)==1 and Map.has_key?(state.idempotency,{"agent",mid}))
  passed=["rejected-mutation-consumes-no-receipt-and-identical-retry-accepts-exactly-one-original"|passed]
  {401,headers,value}=request.("/federation/v1",token,%{"protocol_version"=>1,"op"=>"catalog"})
  check.(headers["www-authenticate"]=="Bearer" and value["protocol_version"]==1 and value["error"]["code"]=="UNAUTHORIZED")
  passed=["legacy-v1-authentication-errors-retain-version-and-bearer-challenge"|passed]
  :persistent_term.put({ADHD.Config,:config},Map.delete(c,"project_id"))
  {400,_,value}=request.("/federation/v1",String.duplicate("q",36),%{"protocol_version"=>1,"op"=>"catalog"})
  check.(value["protocol_version"]==1 and value["error"]["code"]=="PROJECT_REQUIRED")
  passed=["legacy-v1-no-default-project-errors-retain-wire-version"|passed]
  :persistent_term.put({ADHD.Config,:config},c)
  IO.puts(JSON.encode!(%{"suite"=>"adhd/store-freeze-wire@1","passed"=>true,"artifact_sha256"=>Base.encode16(:crypto.hash(:sha256,File.read!(artifact)),case: :lower),"checks"=>Enum.map(Enum.reverse(passed),&%{"name"=>&1,"passed"=>true}),"limitations"=>["Controlled local freeze setup; actual HTTP response and A2A retry assertions. Real syscall/crash qualification is separate."]}))
after
  GenServer.stop(server)
  for id<-ADHD.Projects.ids(c) do
    pid=if id==c["project_id"],do: Process.whereis(ADHD.Store),else: :global.whereis_name({ADHD.Store,id})
    if is_pid(pid) and Process.alive?(pid),do: GenServer.stop(pid)
  end
end
