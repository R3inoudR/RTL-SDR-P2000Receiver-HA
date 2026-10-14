"""Conservative P2000 matching and address/geocode validation."""
import re
import math
import json
import time
import fnmatch
import unicodedata

def norm(value):
    value=unicodedata.normalize('NFKD',str(value)).casefold()
    return re.sub(r'\s+', ' ', value).strip()

def incident_type(body):
    text=norm(body)
    if re.search(r'\bzeer\s+(?:groot|grote|gr\.?)\s*(?:brand|br)\b',text): return 'zeer_grote_brand'
    if re.search(r'\b(?:groot|grote|gr\.?)\s*(?:brand|br)\b',text): return 'grote_brand'
    if re.search(r'\bmiddel\s*(?:brand|br)\b',text): return 'middelbrand'
    return ''

def grip_level(body):
    levels=re.findall(r'\bgrip\s*[-:]?\s*([1-4])(?!\d)',norm(body))
    return max(map(int,levels),default=0)

def match_patterns(patterns, values):
    patterns=[p.strip() for p in patterns.split(',') if p.strip()]
    return not patterns or any(fnmatch.fnmatchcase(norm(v),norm(p)) for p in patterns for v in values)

def non_location_match(sensor,msg):
    if sensor.get('incident_type') and incident_type(msg.body)!=sensor['incident_type']: return False
    if sensor.get('grip_level') and grip_level(msg.body)!=int(sensor['grip_level']): return False
    if sensor.get('towns') and norm(msg.city) not in [norm(t) for t in sensor['towns'].split(',')]: return False
    for key,values in [('keyword',[msg.body]),('capcode',msg.capcodes),('discipline',msg.disciplines.split(', ')),('region',msg.region.split(', '))]:
        if not match_patterns(sensor.get(key,''),values): return False
    return True

def coordinates(lat,lon):
    try:
        lat,lon=float(lat),float(lon)
        if not (math.isfinite(lat) and math.isfinite(lon) and 50.7<=lat<=53.7 and 3<=lon<=7.6): return None
        return lat,lon
    except (TypeError,ValueError): return None

def sensor_match(sensor,msg,geodesic):
    if not non_location_match(sensor,msg): return False,'criteria',None
    radius=sensor.get('zone_radius')
    if radius is None: return True,'matched',None
    try: radius=float(radius)
    except (ValueError,TypeError): return False,'invalid_radius',None
    location=coordinates(msg.latitude,msg.longitude)
    home=coordinates(sensor.get('zone_latitude'),sensor.get('zone_longitude'))
    if radius<=0 or not home: return False,'invalid_radius',None
    if not location or not getattr(msg,'location_verified',False): return False,'missing_verified_location',None
    uncertainty=getattr(msg,'location_uncertainty_km',float('inf'))
    try: uncertainty=float(uncertainty)
    except (TypeError,ValueError): return False,'invalid_uncertainty',None
    if not math.isfinite(uncertainty) or uncertainty<0: return False,'invalid_uncertainty',None
    distance=geodesic(home,location).km
    if distance+uncertainty>radius: return False,'outside_radius',distance
    return True,'matched',distance

def extract_address(body,db):
    rows=db.cursor.execute('SELECT city, abbreviation FROM places').fetchall()
    hits=[]
    for row in rows:
        city,abbreviation=row['city'],row['abbreviation']
        for candidate in (city,abbreviation):
            if not candidate: continue
            for m in re.finditer(r'(?<!\w)'+re.escape(candidate)+r'(?!\w)',body,re.I):
                hits.append((len(city),m.start(),m.end(),city))
    if not hits: return '', '', '', ''
    # Prefer the full multi-word city over a short city occurring inside it.
    _,start,end,city=max(hits,key=lambda h:(h[0],h[1]))
    before=body[:start].strip()
    # An abbreviation often follows the already written full town.
    before=re.sub(re.escape(city)+r'\s*$','',before,flags=re.I).strip()
    postcode=re.search(r'\b([1-9]\d{3})(?:\s*([A-Z]{2}))?\s*$',before)
    postalcode=''
    if postcode:
        postalcode=postcode.group(1)+((' '+postcode.group(2)) if postcode.group(2) else '')
        before=before[:postcode.start()].strip()
    road=re.search(r"((?:(?:Nieuwe|Oude|Sint|St\.|Van|van|De|de|Het|het|Den|den|ten|ter)\s+){0,3}[\w'Ã¢â‚¬â„¢.-]+(?:straat|weg|laan|plein|singel|dreef|kade|dijk|pad|hof|haven|tunnel|steeg|park|hoeven|borch|veld|dam|brug|baan))\s*(\d+[a-zA-Z]?)?\s*$",before,re.I)
    if not road: return '', '', postalcode, city
    street=road.group(1)
    number=road.group(2) or ''
    address=' '.join(p for p in (street,number,postalcode,city) if p)
    return address,street,postalcode,city

def verified_result(result,city,street,geodesic):
    components=result.get('components',{})
    if components.get('country_code','').lower()!='nl': return None
    place=next((components[k] for k in ('city','town','village','municipality') if components.get(k)), '')
    aliases={"'s-gravenhage":'den haag',"'s-hertogenbosch":'den bosch'}
    canon=lambda v: aliases.get(norm(v),norm(v).removesuffix(' zh').removesuffix(' nh').removesuffix(' gld').removesuffix(' nb'))
    if canon(place)!=canon(city): return None
    if components.get('_type') in ('city','town','village','municipality','county','state','country'): return None
    if norm(components.get('road',''))!=norm(street): return None
    point=coordinates(result.get('geometry',{}).get('lat'),result.get('geometry',{}).get('lng'))
    bounds=result.get('bounds',{})
    if not point or not bounds.get('northeast') or not bounds.get('southwest'): return None
    try:
        ne,sw=bounds['northeast'],bounds['southwest']
        uncertainty=max(geodesic(point,(lat,lon)).km for lat in (ne['lat'],sw['lat']) for lon in (ne['lng'],sw['lng']))
    except (KeyError,TypeError,ValueError): return None
    if not math.isfinite(uncertainty) or uncertainty>5: return None
    return {'latitude':point[0],'longitude':point[1],'uncertainty':uncertainty,'type':components.get('_type','unknown'),'mapurl':f'https://www.openstreetmap.org/?mlat={point[0]}&mlon={point[1]}#map=17/{point[0]}/{point[1]}'}

def resolve_location(app,address,city,street):
    empty={'latitude':'','longitude':'','mapurl':'','verified':False,'uncertainty':None,'type':'unknown'}
    if not address or not app.use_opencage: return empty
    cur=app.database.cursor
    cur.execute('CREATE TABLE IF NOT EXISTS verified_geocodes (query TEXT PRIMARY KEY, result TEXT, created REAL)')
    cached=cur.execute('SELECT result,created FROM verified_geocodes WHERE query=?',(address,)).fetchone()
    if cached and time.time()-cached[1]<30*86400: return json.loads(cached[0])
    try:
        response=app.open_geocode(address,app.opencagetoken)
        for result in response.get('results',[]):
            valid=verified_result(result,city,street,app.geodesic)
            if valid:
                valid['verified']=True
                cur.execute('INSERT OR REPLACE INTO verified_geocodes VALUES(?,?,?)',(address,json.dumps(valid),time.time()))
                app.database.db.commit()
                return valid
        app.log(f'Location rejected: no verified street result for {address}')
    except Exception as err:
        # Never include request URLs/keys in logs.
        app.log(f'Geocoding unavailable ({type(err).__name__}); radius profiles will reject this message')
    return empty
