"""Conservative media-perception watch: only recent, attributable weather headlines.
No headline is treated as a verified forecast or an automatic attendance adjustment.
"""
import datetime as dt
import email.utils
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'media_weather.json'
PARKS={
 'PC001':'Parque Warner Madrid','PC002':'Parque de Atracciones Madrid',
 'PC003':'Movie Park Germany','PC004':'Slagharen','PC005':'Bobbejaanland',
 'PC006':'Mirabilandia','PC007':'Tusenfryd','PC008':'BonBon-Land',
 'PC009':'Tropical Islands Berlin','PC010':'Zoo Aquarium Madrid',
 'PC011':'Aquopolis Villanueva','PC012':'Aquopolis Torrevieja',
 'PC013':'Aquopolis Cullera','PC014':'Aquopolis Costa Dorada',
 'PC015':'Aquopolis Cartaya','PC016':'Aquopolis Sevilla',
 'PC017':'Selwo Marina','PC018':'Atlantis Aquarium',
 'PC019':'Blackpool Zoo','PC020':'Teleferico Benalmadena',
 'PC021':'Parque de Atracciones Zaragoza','PC022':'Parque Warner Beach',
 'PC023':'Zoo de Madrid','PC024':'Atlantis Madrid Xanadu',
 'PC025':'Weltvogelpark Walsrode','PC026':'Selwo Aventura','PC027':'Faunia',
}
# Restrict alerts to media framing likely to deter visits, rather than all weather news.
RISK=re.compile(r'(?i)storm|severe weather|weather warning|weather alert|flood|heavy rain|torrential|blizzard|snowstorm|heatwave|extreme heat|strong wind|gale|thunderstorm|tempestad|tormenta|alerta meteorol[oó]gica|lluvias torrenciales|inundaci[oó]n|nevadas|ola de calor|vientos fuertes|unwetter|sturmwarnung|starkregen|hochwasser|schneesturm|hittegolf|stormwaarschuwing|orage|intemp[eé]ries|maltempo|allerta meteo|uvær|stormvarsel')
now=dt.datetime.now(dt.timezone.utc)
out={'updated_at':now.isoformat(),'parks':{}}
for pid,name in PARKS.items():
 try:
  query=f'"{name}" (storm OR weather OR lluvia OR tormenta OR unwetter OR maltempo OR météo)'
  url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query+' when:3d','hl':'en','gl':'GB','ceid':'GB:en'})
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 ParkCast/1.0'})
  with urllib.request.urlopen(req,timeout=12) as res:root=ET.fromstring(res.read(600000))
  alerts=[]
  for item in root.findall('.//item'):
   title=(item.findtext('title') or '').strip()
   description=re.sub('<[^>]+>',' ',item.findtext('description') or '')
   if not RISK.search(title):continue
   if name.casefold() not in (title+' '+description).casefold():continue
   try:published=email.utils.parsedate_to_datetime(item.findtext('pubDate')).astimezone(dt.timezone.utc)
   except (ValueError,TypeError):continue
   if not (dt.timedelta(0)<=now-published<=dt.timedelta(hours=72)):continue
   link=item.findtext('link') or ''
   if not link.startswith('https://'):continue
   alerts.append({'headline':title[:180],'url':link,'published_at':published.isoformat(),'source':item.findtext('source') or 'News coverage'})
   if len(alerts)>=2:break
  if alerts:out['parks'][pid]=alerts
 except Exception as exc:print(f'Media watch unavailable for {pid}: {exc}')
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(f"Media weather headlines found for {len(out['parks'])} parks")
