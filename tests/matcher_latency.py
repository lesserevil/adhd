#!/usr/bin/env python3
"""Measure short-response Nemotron match decisions on a small sequential sample."""
import argparse,json,math,statistics,time
from pathlib import Path
from urllib.request import Request,urlopen


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default='http://127.0.0.1:18770/v1/systemone');p.add_argument('--report',default='verification/matcher-latency.json');p.add_argument('--repetitions',type=int,default=3);args=p.parse_args()
 if not 1<=args.repetitions<=20:p.error('repetitions must be 1..20')
 rows=[]
 for repeat in range(args.repetitions):
  for name,text,expected in [('positive','I am changing the API response to include a task status field.',True),('negative','The office coffee machine was cleaned today.',False)]:
   request={'model':'Nemotron-Deciffusion-8B-v2.1','state':{'publication':{'text':text}},'questions':{'relevance':{'type':'noul','instructions':'Does this publication match the subscription: API changes affecting client integration?'}}}
   start=time.perf_counter()
   with urlopen(Request(args.url,data=json.dumps(request).encode(),headers={'Content-Type':'application/json'}),timeout=3) as response:raw=response.read();result=json.loads(raw)
   latency=round((time.perf_counter()-start)*1000,2);answer=result['answers']['relevance'];value=answer['noul']
   assert result['model']==request['model'] and answer['type']=='noul' and type(value) in (int,float) and math.isfinite(value) and 0<=value<=1
   decision=value>=.9;assert decision==expected,(name,decision)
   rows.append({'case':name,'repeat':repeat,'latency_ms':latency,'response_bytes':len(raw),'probability':value,'match':decision,'expected_match':expected})
 report={'schema':'adhd/short-matcher-latency@1','passed':True,'model':'Nemotron-Deciffusion-8B-v2.1','threshold':.9,'cases':rows,'min_ms':min(x['latency_ms'] for x in rows),'median_ms':statistics.median(x['latency_ms'] for x in rows),'max_ms':max(x['latency_ms'] for x in rows),'claim':'Small sequential sample on this host; no production latency SLA or load-capacity claim.'}
 Path(args.report).write_text(json.dumps(report,indent=2)+'\n');print('PASS short decisions; min/median/max ms:',report['min_ms'],report['median_ms'],report['max_ms'])

if __name__=='__main__':main()
