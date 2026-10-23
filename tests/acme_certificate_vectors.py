"""Independent cryptography-generated certificate graphs for actual TLSCertificate.load.
Private fixture keys remain in an owned mode0700 output directory; reports contain no PEM.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID, ObjectIdentifier
import ipaddress


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--elixir',type=Path,required=True)
    p.add_argument('--erlang-bin',type=Path,required=True)
    a=p.parse_args()
    work=a.work.resolve();work.mkdir(mode=0o700,parents=True,exist_ok=False)
    inputs={name:(a.source_root/name).read_bytes() for name in ['domain.exs','tls_certificate.exs']}
    for name,data in inputs.items():
        (work/name).write_bytes(data);(work/name).chmod(0o600)
    now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    keys={name:rsa.generate_private_key(public_exponent=65537,key_size=2048) for name in ['root','intermediate','leaf','other']}
    keys['weak']=rsa.generate_private_key(public_exponent=65537,key_size=1024)
    keys['p256']=ec.generate_private_key(ec.SECP256R1())
    keys['p384']=ec.generate_private_key(ec.SECP384R1())
    keys['p521']=ec.generate_private_key(ec.SECP521R1())
    keys['ed25519']=ed25519.Ed25519PrivateKey.generate()
    names={k:x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,k+'.example.org')]) for k in keys}
    def usage(ca=False,sign=True):
        return x509.KeyUsage(digital_signature=sign,content_commitment=False,key_encipherment=not ca,data_encipherment=False,key_agreement=False,key_cert_sign=ca,crl_sign=ca,encipher_only=None,decipher_only=None)
    def cert(key='leaf',issuer='root',ca=False,bc=True,pathlen=None,san=None,eku=None,ku=None,before=-3600,after=86400,unknown=False,signer=None):
        b=x509.CertificateBuilder().subject_name(names[key]).issuer_name(names[issuer]).public_key(keys[key].public_key()).serial_number(0xABCDEF).not_valid_before(now+dt.timedelta(seconds=before)).not_valid_after(now+dt.timedelta(seconds=after))
        if bc:b=b.add_extension(x509.BasicConstraints(ca=ca,path_length=pathlen),critical=True)
        if ku is not False:b=b.add_extension(usage(ca) if ku is None else ku,critical=True)
        if not ca or san is not None:
            b=b.add_extension(x509.SubjectAlternativeName(san if san is not None else [x509.DNSName('hub.example.org')]),critical=False)
        if not ca:
            b=b.add_extension(x509.ExtendedKeyUsage(eku if eku is not None else [ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        if unknown:b=b.add_extension(x509.UnrecognizedExtension(ObjectIdentifier('1.3.6.1.4.1.55555.1'),b'\x05\x00'),critical=True)
        sk=keys[signer or issuer]
        return b.sign(sk,None if isinstance(sk,ed25519.Ed25519PrivateKey) else hashes.SHA256())
    root=cert('root','root',ca=True,pathlen=3)
    inter=cert('intermediate','root',ca=True,pathlen=1)
    leaf=cert()
    rows=[]
    def add(name,chain,key='leaf',accepted=False,live=True,recovery=False,extra=b'',prefix=b'',key_prefix=b'',key_suffix=b''):
        folder=work/name;folder.mkdir(mode=0o700)
        chain_bytes=prefix+b''.join(c.public_bytes(serialization.Encoding.PEM) for c in chain)+extra
        private=key_prefix+keys[key].private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())+key_suffix
        for name_,data in [('chain.pem',chain_bytes),('key.pem',private)]:
            (folder/name_).write_bytes(data);(folder/name_).chmod(0o600)
        rows.append({'case':name,'chain':str(folder/'chain.pem'),'key':str(folder/'key.pem'),'domains':['hub.example.org'],'allow_expired':recovery,'accepted':accepted,'live':live,'serial':'abcdef'})
    add('valid-rsa-full-chain',[leaf,root],accepted=True)
    add('raw-chain-prefix',[leaf,root],prefix=b'junk\n')
    add('raw-chain-suffix',[leaf,root],extra=b'junk\n')
    add('raw-chain-interleaved',[leaf],extra=b'junk\n'+root.public_bytes(serialization.Encoding.PEM))
    add('raw-key-prefix',[leaf,root],key_prefix=b'junk\n')
    add('raw-key-suffix',[leaf,root],key_suffix=b'junk\n')
    add('valid-pem-whitespace',[leaf,root],prefix=b' \r\n',extra=b' \t\n',key_suffix=b' \n',accepted=True)
    add('valid-single-supplied-leaf',[leaf],accepted=True)
    add('valid-root-omitted',[cert(issuer='intermediate'),inter],accepted=True)
    add('valid-intermediate-chain',[cert(issuer='intermediate'),inter,root],accepted=True)
    for k in ['p256','p384']:
        add('valid-'+k,[cert(k),root],key=k,accepted=True)
    add('extra-ip-san',[cert(san=[x509.DNSName('hub.example.org'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),root])
    add('extra-uri-san',[cert(san=[x509.DNSName('hub.example.org'),x509.UniformResourceIdentifier('https://hub.example.org')]),root])
    add('wrong-dns-san',[cert(san=[x509.DNSName('foreign.example.org')]),root])
    add('unknown-critical-leaf',[cert(unknown=True),root])
    add('unknown-critical-single-leaf',[cert(unknown=True)])
    add('non-ca-issuer',[leaf,cert('root','root',ca=False)])
    add('missing-issuer-basicconstraints',[leaf,cert('root','root',ca=True,bc=False)])
    add('wrong-issuer-signature',[cert(signer='other'),root])
    add('wrong-private-key',[leaf,root],key='other')
    add('future-leaf',[cert(before=3600,after=86400),root])
    add('future-leaf-recovery',[cert(before=3600,after=86400),root],recovery=True)
    expired=cert(before=-86400,after=-60)
    add('expired-leaf',[expired,root])
    add('expired-leaf-recovery',[expired,root],accepted=True,live=False,recovery=True)
    add('expired-single-leaf-recovery',[expired],accepted=True,live=False,recovery=True)
    for k in ['weak','p521','ed25519']:
        add('unsupported-key-'+k,[cert(k),root],key=k)
    add('clientauth-only-leaf',[cert(eku=[ExtendedKeyUsageOID.CLIENT_AUTH]),root])
    add('ca-leaf-with-dns',[cert(ca=True,san=[x509.DNSName('hub.example.org')]),root])
    add('leaf-without-signature-usage',[cert(ku=usage(False,False)),root])
    add('issuer-without-keycertsign',[leaf,cert('root','root',ca=True,ku=usage(False))])
    add('expired-issuer',[leaf,cert('root','root',ca=True,before=-86400,after=-60)],recovery=True)
    add('future-issuer',[leaf,cert('root','root',ca=True,before=3600)],recovery=True)
    add('anchor-pathlen-exceeded',[cert(issuer='intermediate'),inter,cert('root','root',ca=True,pathlen=0)])
    add('unknown-critical-anchor',[leaf,cert('root','root',ca=True,unknown=True)])
    add('unknown-critical-intermediate',[cert(issuer='intermediate'),cert('intermediate','root',ca=True,unknown=True),root])
    add('expired-intermediate-recovery',[cert(issuer='intermediate'),cert('intermediate','root',ca=True,before=-86400,after=-60),root],recovery=True)
    add('valid-no-optional-keyusage',[cert(ku=False),root],accepted=True)
    add('weak-issuer-key',[cert(issuer='weak'),cert('weak','weak',ca=True)])
    add('pem-extra-noncertificate',[leaf,root],extra=keys['other'].public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    vectors=work/'vectors.json';vectors.write_text(json.dumps(rows));vectors.chmod(0o600)
    env=dict(os.environ,PATH=str(a.elixir.parent)+':'+str(a.erlang_bin)+':'+os.environ.get('PATH',''),ERL_FLAGS='+S 2:2')
    argv=[str(a.elixir),str(Path(__file__).with_name('acme_certificate_contracts.exs')),str(work/'domain.exs'),str(work/'tls_certificate.exs'),str(vectors),str(work/'result.json')]
    with (work/'stdout').open('wb') as out,(work/'stderr').open('wb') as err:
        result=subprocess.run(argv,env=env,stdout=out,stderr=err,timeout=60)
    report=json.loads((work/'result.json').read_text())
    report.update({'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source_files':{n:hashlib.sha256(b).hexdigest() for n,b in inputs.items()},'input_source_unchanged':all((a.source_root/n).read_bytes()==b for n,b in inputs.items()),'exit_code':result.returncode,'fixture_keys_retained_private_only':True,'certificate_fixture_sha256':{r['case']:hashlib.sha256(Path(r['chain']).read_bytes()).hexdigest() for r in rows}})
    (work/'review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'cases':len(rows),'unexpected':[r for r in report['cases'] if not r['passed']],'source_unchanged':report['input_source_unchanged']}))
    return result.returncode

if __name__=='__main__':raise SystemExit(main())
