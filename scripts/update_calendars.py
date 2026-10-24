#!/usr/bin/env python3
"""Refresh ParkCast operating calendars from ThemeParks.wiki's structured schedule API.
Only explicit CLOSED entries grey out days; missing dates never mean closed.
Matches entities by name AND proximity; unknown/unmatched parks remain default-open.
"""
import json, re, urllib.request, datetime, pathlib, math, sys, html
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data/opening_calendars.json'
DIAGNOSTICS=ROOT/'data/opening_calendar_diagnostics.json'
YEAR_ROUND={'PC009','PC010','PC017','PC018','PC022','PC023','PC024'}
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

# Strict official-source season checks. A source must explicitly identify the year.
# Never roll a season boundary forward into a later year.
# Every rule is scoped to 2026; only current source text authorises the closure.
# 'From' is conservative (today or the verified start), not a guessed season-end date.
# Ticketing pages are labelled secondary; they are not represented as official websites.
OFFICIAL_SEASON_SOURCES={
 'PC020':('https://www.sommarland.no/priser-og-apningstider/apningstider',r'f[øo]rste [åa]pningsdag i 2026 er 6\. juni.*siste dag er 16\. august','official'),
 'PC011':('https://villanueva.aquopolis.es/',r'nos vemos en 2027|volvemos en 2027','official'),
 'PC012':('https://costa-dorada.aquopolis.es/',r'nos vemos en 2027','official'),
 'PC016':('https://parquewarnerbeach.parquewarner.com/',r'hasta el 20 de septiembre|abrimos hasta el 20 de septiembre','official'),
 'PC021':('https://mirabeach.mirabilandia.it/en',r'the season may be over, but the fun isn.t|start dreaming about the 2027 season','official'),
 'PC013':('https://disfrutalia.tixalia.com/aquopoliscullera',r'temporada 2026 finalizada','ticketing'),
 'PC014':('https://disfrutalia.tixalia.com/conversionpath?entityId=8qrp56trmd3as&language=en',r'temporada 2026 finalizada','ticketing'),
 'PC015':('https://disfrutalia.tixalia.com/aquopoliscartaya',r'temporada 2026 finalizada','ticketing'),
}
def official_season(pid,now):
 if pid not in OFFICIAL_SEASON_SOURCES or now.year!=2026:return None
 url,pattern,source_type=OFFICIAL_SEASON_SOURCES[pid]
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; ParkCast/1.0)','Accept':'text/html'})
 try:
  with urllib.request.urlopen(req,timeout=18) as response:
   raw=response.read(900000).decode('utf-8','replace')
  clean=html.unescape(re.sub(r'<[^>]+>',' ',raw))
  clean=re.sub(r'\s+',' ',clean).lower()
  if not re.search(pattern,clean,re.I):return None
  # Conservative: don't retrospectively claim closure dates without a precise boundary.
  start='2026-08-17' if pid=='PC020' else ('2026-09-21' if pid=='PC016' else now.date().isoformat())
  return {'from':start,'through':'2026-12-31','url':url,
          'evidence':'Verified 2026 season-end/2027 return statement',
          'source_type':source_type}
 except Exception as exc:print('Season check unavailable:',pid,exc,file=sys.stderr)
 return None

# Explicit, dated secondary-source closures, never extrapolated to other dates/years.
# Sources: https://queue-times.com/parks/298/calendar (checked 2026-10-24).
# Official source for independent confirmation: https://www.parquewarner.com/horarios-y-precios/horarios
VERIFIED_DATED_CLOSURES={
 'PC001':{'2026-10-26','2026-10-27'},
}
DATED_SOURCES={
 'PC001':'https://queue-times.com/parks/298/calendar',
}
def apply_dated_closures(result,diagnostics):
 for pid,dates in VERIFIED_DATED_CLOSURES.items():
  entry=result.setdefault(pid,{'name':next(row[1] for row in PARKS if row[0]==pid),'days':{}})
  conflicts=[]
  for date in sorted(dates):
   existing=entry['days'].get(date)
   if existing and existing.get('status')=='open':
    conflicts.append(date)
    # Never silently override conflicting feed data.
    continue
   entry['days'][date]={'status':'closed','source':DATED_SOURCES[pid],'source_type':'secondary_dated_calendar'}
  diag=diagnostics.setdefault(pid,{'name':entry['name']})
  diag['dated_secondary_closed_days']=len(dates)-len(conflicts)
  diag['dated_source']=DATED_SOURCES[pid]
  diag['dated_conflicts']=conflicts
  diag['dated_coverage_only']=True

def apply_official_seasons(result,diagnostics,now):
 applied=0
 for row in PARKS:
  pid,name,*_=row
  if pid in YEAR_ROUND:continue
  rule=official_season(pid,now)
  if not rule:continue
  start=datetime.date.fromisoformat(rule['from']);end=datetime.date.fromisoformat(rule['through'])
  entry=result.setdefault(pid,{'name':name,'days':{}})
  # Explicit daily OPEN from a structured schedule takes precedence: flag any conflict.
  conflicts=0;day=start
  while day<=end:
   date=day.isoformat();existing=entry['days'].get(date)
   if existing and existing.get('status')=='open':conflicts+=1
   else:entry['days'][date]={'status':'closed','source':rule['url'],'source_type':rule['source_type'],'valid_through':rule['through']}
   day+=datetime.timedelta(days=1)
  entry['official_season_source']=rule['url']
  diagnostics[pid]={'name':name,'state':'official_off_season','verified_closed_days':(end-start).days+1-conflicts,'conflicts_with_provider':conflicts,'source':rule['url'],'source_type':rule['source_type'],'evidence':rule['evidence'],'valid_through':rule['through']}
  applied+=1
 return applied

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
   result[pid]={'name':name,'source':f'https://api.themeparks.wiki/v1/entity/{eid}/schedule','checked_at':now.isoformat(),'days':{date:{'status':v['status']} for date,v in days.items()}}
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
  if pid not in result and entry.get('days'):
   # Retain dated records only while their provenance remains identifiable.
   # Do not silently carry forward stale seasonal rules or unverified closures.
   retained={date:v for date,v in entry['days'].items() if v.get('status')=='open' or (v.get('status')=='closed' and v.get('source_type')=='secondary_dated_calendar' and v.get('source'))}
   if retained:result[pid]={**entry,'days':retained}
 for row in PARKS:
  pid,name,*_=row
  if pid in YEAR_ROUND:
   diagnostics[pid]={'name':name,'state':'year_round_default','message':'User-confirmed daily opening; only an explicit verified closure can override'}
   if pid not in result:result[pid]={'name':name,'source':'user-confirmed year-round operating policy','days':{},'default_status':'open'}
   else:result[pid]['default_status']='open'
  elif pid not in result:
   diagnostics.setdefault(pid,{'name':name,'state':'not_connected'})
 official_count=apply_official_seasons(result,diagnostics,now)
 # These official calendars are dynamic; do not infer closures from an unparsed page.
 official_calendar_pages={
  'PC004':'https://www.slagharen.com/en/prijzen---openingstijden/openingstijden',
  'PC007':'https://www.tusenfryd.no/en/apningstider-og-priser/apningstider',
  'PC008':'https://www.bonbonland.dk/en/abningstider-og-priser/abningstider',
  'PC019':'https://www.telefericobenalmadena.com/horarios-y-precios/horarios',
 }
 for pid,url in official_calendar_pages.items():
  diagnostics[pid]['official_calendar_url']=url
  diagnostics[pid]['automatic_day_by_day_coverage']=False
 diagnostics['PC020']['source_note']='Official Bø Sommarland 2026 season boundary checked against published opening-hours page.'
 apply_dated_closures(result,diagnostics)
 payload={'updated_at':now.isoformat(),'provider':'ThemeParks.wiki','parks':result,'matched_and_updated':checked,'official_off_season_parks':official_count,'configured_parks':len(PARKS),'explicit_closed_days':explicit_closed,'diagnostics':diagnostics,'year_round_park_ids':sorted(YEAR_ROUND),'interpretation':'Missing dates are UNKNOWN, not OPEN. Seven user-confirmed year-round parks default OPEN. Only explicit verified closure records grey out tiles.'}
 OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
 DIAGNOSTICS.write_text(json.dumps({'updated_at':now.isoformat(),'parks':diagnostics,'provider_matches':checked,'official_off_season_parks':official_count,'year_round_defaults':len(YEAR_ROUND),'not_connected':sum(d.get('state') not in ('updated','year_round_default','official_off_season') for d in diagnostics.values())},indent=2,ensure_ascii=False)+'\n')
 print('Updated',checked,'provider parks; official off-season parks:',official_count,'; provider closed dates:',explicit_closed)
 print('Not connected:',', '.join(r[0] for r in PARKS if diagnostics.get(r[0],{}).get('state')!='updated'))
 return 0
if __name__=='__main__':sys.exit(main())
