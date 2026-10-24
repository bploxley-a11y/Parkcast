#!/usr/bin/env python3
"""Madrid municipal data -> conservative, sourced ParkCast access alerts.
No external Python dependencies. Fail closed (never invent a closure).
"""
import datetime as dt
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'madrid_alerts.json'
API = 'https://datos.madrid.es/id/api/3/action/package_show?id='
PACKAGES = {'traffic':'202062-0-trafico-incidencias-viapublica', 'agenda':'300107-0-agenda-actividades-eventos'}
NEAR = re.compile(r'casa de campo|avenida de portugal|avda\.? de portugal|paseo de extremadura|puerta del angel|puerta del ángel|bat[aá]n|lago de la casa de campo|zool[oó]gico|parque de atracciones|paseo de la venta|camino de la venta|carretera de la casa de campo', re.I)
CLOSURE = re.compile(r'corte|cortad[ao]|cerrad[ao]|cierre|interrupci[oó]n|prohibici[oó]n|desv[ií]o|restricci[oó]n|sin acceso|ocupaci[oó]n de calzada',re.I)
SEVERE = re.compile(r'corte total|cierre total|cortada completamente|sin acceso|prohibido el acceso',re.I)

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ParkCast/5.0 (open-data integration)', 'Accept':'application/json, application/xml, text/xml, */*'})
    with urllib.request.urlopen(req,timeout=25) as response:
        return response.read(12_000_000)

def resources(package):
    doc=json.loads(get(API+package))
    if not doc.get('success'): raise ValueError('Municipal resource metadata unavailable')
    return doc['result']['resources']

def flatten(node):
    return ' '.join(s.strip() for s in node.itertext() if s and s.strip())

def parse_traffic(blob):
    root=ET.fromstring(blob)
    # Use record-shaped nodes rather than searching the entire XML as one event.
    parents={child:parent for parent in root.iter() for child in parent}
    records=[]
    for e in root.iter():
        tag=e.tag.rsplit('}',1)[-1].lower()
        if tag in ('incidencia','incidente','incident','registro','item'):
            records.append(e)
    if not records:
        # Unknown schema: don't generate alerts without record-level evidence.
        raise ValueError('Unrecognised traffic XML record schema; no alerts inferred')
    alerts=[]
    today=dt.datetime.now(dt.timezone.utc).date()
    for e in records[:10000]:
        desc=flatten(e)
        if not NEAR.search(desc) or not CLOSURE.search(desc): continue
        # Avoid falsely assuming an event remains active: extract dates when supplied.
        fields={x.tag.rsplit('}',1)[-1].lower(): (x.text or '').strip() for x in e.iter() if len(x)==0}
        dates=[]
        for key,value in fields.items():
            if any(s in key for s in ('fecha','date','inicio','fin','start','end')):
                m=re.search(r'(20\d\d)[-/](\d\d)[-/](\d\d)',value)
                if m:
                    try: dates.append(dt.date(*map(int,m.groups())))
                    except ValueError: pass
        if not dates: continue  # No defensible date range
        start,end=min(dates),max(dates)
        if end<today or start>today+dt.timedelta(days=14):continue
        severity='bad' if SEVERE.search(desc) else 'mid'
        alerts.append({'from':max(start,today).isoformat(),'to':min(end,today+dt.timedelta(days=14)).isoformat(),
                       'name':re.sub(r'\s+',' ',desc)[:220], 'severity':severity,
                       'source':'https://datos.madrid.es/dataset/202062-0-trafico-incidencias-viapublica',
                       'parks':['PC002','PC017'], 'kind':'road_closure'})
    return alerts[:60]

def main():
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    status={'traffic':'unavailable','agenda':'unavailable'}
    alerts=[]; context=[]
    try:
        r=resources(PACKAGES['traffic'])
        xml=[x for x in r if 'xml' in (x.get('format','').lower()) or x.get('url','').lower().endswith('.xml')]
        if not xml:raise ValueError('No traffic XML resource')
        alerts=parse_traffic(get(xml[0]['url']))
        status['traffic']='ok'
    except Exception as exc:
        print('Traffic feed unavailable:',exc,file=sys.stderr)
    try:
        # Events calendar is context only: a listed event does not establish a road closure.
        r=resources(PACKAGES['agenda'])
        candidates=[x for x in r if 'json' in x.get('format','').lower()]
        if not candidates:raise ValueError('No agenda JSON resource')
        doc=json.loads(get(candidates[0]['url']))
        records=doc if isinstance(doc,list) else doc.get('@graph',doc.get('features',doc.get('records',[])))
        if not isinstance(records,list):raise ValueError('Unrecognised agenda format')
        today=dt.datetime.now(dt.timezone.utc).date()
        for item in records:
            txt=json.dumps(item,ensure_ascii=False)
            if not NEAR.search(txt):continue
            dates=re.findall(r'20\d\d-\d\d-\d\d',txt)
            if not dates:continue
            if not any(today.isoformat()<=d<=(today+dt.timedelta(days=14)).isoformat() for d in dates):continue
            name=item.get('title',item.get('name','Event near Casa de Campo')) if isinstance(item,dict) else 'Event near Casa de Campo'
            if isinstance(name,dict):name=name.get('es',str(name))
            context.append({'date':min(dates),'name':str(name)[:160], 'source':'https://datos.madrid.es/dataset/300107-0-agenda-actividades-eventos'})
        status['agenda']='ok'
    except Exception as exc:
        print('Agenda feed unavailable:',exc,file=sys.stderr)
    payload={'updated_at':now,'sources':status,'alerts':alerts,'nearby_events':context[:30],
             'method':'Only dated municipal traffic incidents with explicit closure language near Casa de Campo can change a colour. Agenda events are informational only. Geographic/route relevance remains heuristic.',
             'licence':'Madrid City Council open data, CC BY 4.0'}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Wrote',OUT,'alerts',len(alerts),'nearby events',len(context),'sources',status)

if __name__=='__main__':main()
