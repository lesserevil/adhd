[hub,config]=System.argv()
[prefix,_]=String.split(File.read!(hub),"\nunless Code.ensure_loaded?(ADHD.CLI) do",parts: 2)
Code.compile_string(prefix,hub)
c=ADHD.JSON.decode!(File.read!(config))
p=ADHD.Storage.local_legacy_state(c["store_path"],c["project_id"],c["server_id"],ADHD.LocalLegacy.limits(c));s=p.state
out=%{"project_id"=>s.project,"schema"=>s.schema,"sequence"=>s.seq,
 "publications"=>Enum.map(s.publications,fn {_,r}->r.value end),
 "unacked_deliveries"=>Enum.flat_map(s.deliveries,fn {_,r}->if r.ack,do: [],else: [r.value] end),
 "acked_delivery_ids"=>Enum.flat_map(s.deliveries,fn {id,r}->if r.ack,do: [id],else: [] end),
 "receipts"=>Enum.map(s.idempotency,fn {{agent,mid},r}->%{"agent"=>agent,"message_id"=>mid,"command"=>r.command,"result"=>r.result} end)}
IO.puts(JSON.encode!(out))
