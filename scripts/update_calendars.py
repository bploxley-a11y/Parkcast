#!/usr/bin/env python3
"""Refresh ParkCast operating calendars from ThemeParks.wiki's structured schedule API.
Only explicit CLOSED entries grey out days; missing dates never mean closed.
Matches entities by name AND proximity; unknown/unmatched parks remain default-open.
"""
import json, re, urllib.request, datetime, pathlib, math, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data/opening_calendars.json'
API='https://api.themeparks.wiki/v1'
PARKS=[
 ('PC001','Parque Warner Madrid',40.229,-3.593,['parque warner madrid','parque warner']),
 ('PC002','Parque de Atracciones Madrid',40.413,-3.750,['parque de atracciones de madrid','parque de atracciones madrid']),
 ('PC003','Movie Park Germany',51.622,6.972,['movie park germany']),
 ('PC004','Slagharen',52.626,6.555,['slagharen','attractiepark slagharen']),
 ('PC005','Bobbejaanland',51.2,4.904,['bobbejaanland']),
 ('PC006','Mirabilandia',44.338,12.263,['mirabilandia']),
 ('PC007','Tusenfryd',59.748,10.779,['tusenfryd']),
 ('PC008','BonBon-Land',55.263,11.862,['bonbon-land','bonbon land','bonbonland']),
 ('PC009','Tropical Islands',52.039,13.748,['tropical islands']),
 ('PC010','Blackpool Zoo',53.82,-3.012,['blackpool zoo']),
 ('PC011','Aquopolis Villanueva',40.45,-4.005,['aquopolis villanueva','aquopolis villanueva de la cañada']),
 ('PC012','Aquopolis Costa Dorada',41.077,1.147,['aquopolis costa dorada','aquopolis la pineda']),
 ('PC013','Aquopolis Cullera',39.185,-0.245,['aquopolis cullera']),
 ('PC014','Aquopolis Torrevieja',37.99,-0.683,['aquopolis torrevieja']),
 ('PC015','Aquopolis Cartaya',37.283,-7.155,['aquopolis cartaya']),
 ('PC016','Warner Beach',40.229,-3.593,['parque warner beach','warner beach']),
 ('PC017','Madrid Zoo',40.40941,-3.76268,['zoo aquarium madrid','zoo madrid','zoo aquarium de madrid']),
 ('PC018','Selwo Marina',36.59238,-4.53221,['selwo marina']),
 ('PC019','Teleferico Benalmadena',36.59886,-4.53982,['teleferico benalmadena','teleférico benalmádena']),
 ('PC020','Bo Sommerland',59.447249,9.07274,['bø sommerland','bo sommerland']),
 ('PC021','Mirabeach',44.338,12.263,['mirabeach','mira beach']),
 ('PC022','Bournemouth Oceanarium',50.71592,-1.87681,['oceanarium bournemouth','bournemouth oceanarium','oceanarium']),
 ('PC023','Lakes Aquarium',54.27816,-2.95591,['lakes aquarium']),
 ('PC024','Atlantis Madrid Xanadu',40.29947,-3.92401,['atlantis aquarium madrid','atlantis aquarium']),
]
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'ParkCast-Calendar/1.0 (schedule monitoring)','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def norm(s):return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()
def distance(a,b,c,d):return math.hypot((a-c)*111,(b-d)*85)
def catalog():
 data=fetch(API+'/destinations');out=[]
 for dest in data.get('destinations',[]) if isinstance(data,dict) else data:
  out.extend(dest.get('parks',[]))
 return out
def locate(row,entities):
 pid,name,lat,lon,aliases=row
 found=[]
 for e in entities:
  en=norm(e.get('name',''));alt=[norm(x) for x in aliases]
  if en not in alt:continue
  pos=e.get('location') or {};a=pos.get('latitude');b=pos.get('longitude')
  if a is not None and b is not None and distance(float(a),float(b),lat,lon)>35:continue
  found.append(e)
 return found[0] if len(found)==1 else None

def parse_schedule(data):
 entries=data.get('schedule',[]) if isinstance(data,dict) else []
 result={}
 for e in entries:
  if not isinstance(e,dict):continue
  date=str(e.get('date',''))[:10]
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):continue
  typ=str(e.get('type','')).upper()
  opening=e.get('openingTime');closing=e.get('closingTime')
  if typ=='OPERATING' and opening and closing:
   def hm(v):return str(v)[11:16] if 'T' in str(v) else str(v)[:5]
   result[date]={'status':'open','hours':hm(opening)+'–'+hm(closing)}
  elif typ in ('CLOSED','CLOSURE','NON_OPERATING'):
   result[date]={'status':'closed'}
 return result

def main():
 try:old=json.loads(OUT.read_text())
 except Exception:old={'parks':{}}
 oldparks=old.get('parks',{});now=datetime.datetime.now(datetime.timezone.utc)
 try:entities=catalog()
 except Exception as exc:
  print('Directory unavailable; preserving previous data:',exc,file=sys.stderr);return 0
 result={};checked=0; diagnostics={}; explicit_closed=0
 for row in PARKS:
  pid,name,*_=row; entity=locate(row,entities)
  if not entity:
   diagnostics[pid]={'name':name,'state':'not_matched','message':'No unique provider match; normal weather display retained'}
   print(pid,'not uniquely matched; no inferred closure');continue
  eid=entity.get('id')
  try:
   days=parse_schedule(fetch(f'{API}/entity/{eid}/schedule'))
   if not days:
    diagnostics[pid]={'name':name,'state':'empty_schedule','message':'Provider returned no dated operating records'}
    print(pid,'no explicit schedule records');continue
   # Drop old dates when a successful current schedule supersedes them.
   result[pid]={'name':name,'source':f'https://api.themeparks.wiki/v1/entity/{eid}/schedule','checked_at':now.isoformat(),'days':days}
   checked+=1
   nclosed=sum(d.get('status')=='closed' for d in days.values());explicit_closed+=nclosed
   diagnostics[pid]={'name':name,'state':'updated','published_open_days':sum(d.get('status')=='open' for d in days.values()),'explicit_closed_days':nclosed,'note':'Unlisted dates are not verified closures'}
  except Exception as exc:
   diagnostics[pid]={'name':name,'state':'fetch_error','message':str(exc)[:180]}
   print(pid,'schedule error',exc,file=sys.stderr)
   previous=oldparks.get(pid)
   if previous and previous.get('days'):result[pid]=previous
 # Preserve only previously sourced entries for unmatched parks; never synthesize.
 for pid,entry in oldparks.items():
  if pid not in result and entry.get('days'):result[pid]=entry
 payload={'updated_at':now.isoformat(),'provider':'ThemeParks.wiki','parks':result,'matched_and_updated':checked,'configured_parks':len(PARKS),'explicit_closed_days':explicit_closed,'diagnostics':diagnostics,'interpretation':'Missing provider dates are unknown, not closed. Only explicit closure records grey out tiles.'}
 OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
 print('Updated',checked,'of',len(PARKS),'parks; explicit closed dates:',explicit_closed)
 print('Not connected:',', '.join(r[0] for r in PARKS if diagnostics.get(r[0],{}).get('state')!='updated'))
 return 0
if __name__=='__main__':sys.exit(main())
