import sys,unittest,sqlite3,json,time
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from geopy.distance import geodesic
from reliable import *
from p2000 import Main,MessageItem

HOME=(51.71,4.70)
def msg(**kw):
    m=MessageItem();m.is_posted=False;m.body='A1 13991 Brinkgreverweg 7413 Deventer';m.capcodes=['000120901']
    m.location_verified=False;m.location_uncertainty_km=None;m.location_type='unknown'
    for k,v in kw.items():setattr(m,k,v)
    return m

class Tests(unittest.TestCase):
    def setUp(self): self.sensor={'id':2110,'name':'Lifeliner20','icon':'mdi:helicopter','capcode':'000120901','zone_radius':20,'zone_latitude':HOME[0],'zone_longitude':HOME[1],'sent_HA_discovery':False,'state_topic':'test/state','attribute_topic':'test/attrs'}
    def test_missing_gps(self): self.assertEqual(sensor_match(self.sensor,msg(),geodesic)[:2],(False,'missing_verified_location'))
    def test_deventer(self): self.assertEqual(sensor_match(self.sensor,msg(latitude=52.255,longitude=6.163,location_verified=True,location_uncertainty_km=0.1),geodesic)[:2],(False,'outside_radius'))
    def test_inside(self): self.assertTrue(sensor_match(self.sensor,msg(latitude=HOME[0],longitude=HOME[1],location_verified=True,location_uncertainty_km=.1),geodesic)[0])
    def test_uncertain_boundary(self):
        p=geodesic(kilometers=19.8).destination(HOME,0)
        self.assertFalse(sensor_match(self.sensor,msg(latitude=p.latitude,longitude=p.longitude,location_verified=True,location_uncertainty_km=.3),geodesic)[0])
    def test_nonfinite(self):
        for v in ['nan','inf','',None,'wrong']:
            self.assertFalse(sensor_match(self.sensor,msg(latitude=v,longitude=4.7,location_verified=True),geodesic)[0])
    def test_brand_types(self):
        for text in ['zeer grote brand','Zeer gr. Br','zeer grote br','zeer grootbrand']:
            self.assertEqual(incident_type('P 1 ('+text+') Br gebouw'),'zeer_grote_brand')
            self.assertFalse(non_location_match({'incident_type':'grote_brand'},msg(body=text)))
        for text in ['Grote Br','gr. br','grote brand','groot brand','grotebrand']:self.assertEqual(incident_type(text),'grote_brand')
        for text in ['Middel Br','middelbrand','middel brand']:self.assertEqual(incident_type(text),'middelbrand')
    def test_grip(self):
        for text in ['GRIP1','grip: 1','GRIP-1','(GRIP 1)']: self.assertEqual(grip_level(text),1)
        self.assertEqual(grip_level('GRIP 10'),0);self.assertEqual(grip_level('GRIP 1 opgeschaald GRIP 2'),2)
    def test_places(self):
        self.assertTrue(non_location_match({'towns':'Lage Zwaluwe,Moerdijk','discipline':'Brandweer'},msg(city='Lage Zwaluwe',disciplines='Ambulance, Brandweer')))
        self.assertFalse(non_location_match({'towns':'Moerdijk','discipline':'Brandweer'},msg(city='Deventer',body='Brand Moerdijkstraat Deventer',disciplines='Brandweer')))
    def test_parse(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.execute('CREATE TABLE places(city,abbreviation)')
        db.executemany('INSERT INTO places VALUES(?,?)',[('Deventer','DEVNTR'),('Amsterdam','AMSTDM'),('Nieuwe-Tonge','NWTONG'),('Lage Zwaluwe','LAGEZW')])
        fixture=SimpleNamespace(cursor=db.cursor())
        cases=[('A1 13991 Brinkgreverweg 7413 Deventer 99937 / REGIO 04','Brinkgreverweg 7413 Deventer'),('P 2 BAD-04 Brandgerucht Nieuwe Leliestraat Amsterdam 133331','Nieuwe Leliestraat Amsterdam'),('A2 Havenweg 3244LK Nieuwe-Tonge NWTONG bon 159844','Havenweg 3244 LK Nieuwe-Tonge'),('P 1 Br gebouw Kerkstraat LAGEZW','Kerkstraat Lage Zwaluwe')]
        for text,wanted in cases:self.assertEqual(extract_address(text,fixture)[0],wanted)
        self.assertEqual(extract_address('A1 Deventer Rit 122403',fixture)[0],'')
    def test_geocode_quality(self):
        r={'components':{'country_code':'nl','city':'Amsterdam','road':'Nieuwe Leliestraat','_type':'road'},'geometry':{'lat':52.375,'lng':4.88},'bounds':{'northeast':{'lat':52.376,'lng':4.881},'southwest':{'lat':52.374,'lng':4.879}}}
        self.assertIsNotNone(verified_result(r,'Amsterdam','Nieuwe Leliestraat',geodesic))
        for change in [{'bounds':{}},{'components':{'country_code':'nl','city':'Amsterdam','road':'Nieuwe Leliestraat','_type':'city'}},{'components':{'country_code':'nl','city':'Deventer','road':'Nieuwe Leliestraat','_type':'road'}}]:
            self.assertIsNone(verified_result({**r,**change},'Amsterdam','Nieuwe Leliestraat',geodesic))
    def test_actual_post_and_dedup(self):
        sent=[]
        app=Main.__new__(Main);app.sensors={2110:self.sensor};app.config={'mqtt':{'ha_autodiscovery':False}};app.mqtt_retain=False;app.debug=False;app.delivery_seen={};app.mqtt_sender=SimpleNamespace(publish=lambda **kw:sent.append(kw))
        app.post_data(msg());self.assertEqual(sent,[])
        app.post_data(msg(latitude=52.255,longitude=6.163,location_verified=True,location_uncertainty_km=.1));self.assertEqual(sent,[])
        good=lambda:msg(latitude=HOME[0],longitude=HOME[1],location_verified=True,location_uncertainty_km=.1)
        app.post_data(good());self.assertEqual(len(sent),2)
        app.post_data(good());self.assertEqual(len(sent),2)
    def test_mqtt_failure_retries(self):
        app=Main.__new__(Main);app.sensors={2110:self.sensor};app.config={'mqtt':{'ha_autodiscovery':False}};app.mqtt_retain=False;app.debug=False;app.delivery_seen={}
        app.mqtt_sender=SimpleNamespace(publish=lambda **kw:False)
        m=msg(latitude=HOME[0],longitude=HOME[1],location_verified=True,location_uncertainty_km=.1)
        app.post_data(m);self.assertFalse(m.is_posted);self.assertEqual(app.delivery_seen,{})
        sent=[];app.mqtt_sender=SimpleNamespace(publish=lambda **kw:sent.append(kw))
        app.post_data(m);self.assertTrue(m.is_posted);self.assertEqual(len(sent),2)
        self.assertTrue(all(p['qos']==1 for p in sent))

if __name__=='__main__':unittest.main(verbosity=2)
