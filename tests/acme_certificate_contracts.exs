# Actual module-only certificate load. No TLS/CA/client/listener/application starts.
[domain, source, vectors, output] = System.argv()
Code.compile_file(domain)
input=File.read!(source)
Code.compile_string(input,source)
rows=ADHD.JSON.decode!(File.read!(vectors))
results=Enum.map(rows,fn row->
  actual=try do
    cert=ADHD.TLSCertificate.load(File.read!(row["chain"]),File.read!(row["key"]),row["domains"],row["allow_expired"])
    sni=Keyword.fetch!(ADHD.TLSCertificate.options(cert),:sni_fun)
    %{"accepted"=>true,"live"=>ADHD.TLSCertificate.live?(cert),"serial"=>cert.metadata["serial"],"wrong_sni_rejected"=>sni.(~c"foreign.example.org")==:unrecognized,"requested_sni_matches_live_state"=>(sni.(~c"hub.example.org")==[])==ADHD.TLSCertificate.live?(cert),"sha256"=>cert.metadata["sha256"]}
  rescue e->%{"accepted"=>false,"error_type"=>inspect(e.__struct__)}
  catch kind,_->%{"accepted"=>false,"error_type"=>Atom.to_string(kind)} end
  passed=actual["accepted"]==row["accepted"] and (not row["accepted"] or (actual["live"]==row["live"] and actual["wrong_sni_rejected"] and actual["requested_sni_matches_live_state"] and actual["serial"]==row["serial"]))
  %{"case"=>row["case"],"expected_accepted"=>row["accepted"],"actual"=>actual,"passed"=>passed}
end)
File.write!(output,JSON.encode!(%{"passed"=>Enum.all?(results,& &1["passed"]),"cases"=>results,"module_sha256"=>Base.encode16(:crypto.hash(:sha256,input),case: :lower),"application_started"=>false}))
if not Enum.all?(results,& &1["passed"]),do: System.halt(1)
