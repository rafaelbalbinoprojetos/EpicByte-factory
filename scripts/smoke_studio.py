"""HTTP smoke against the existing database. Never starts a mission or writes a workspace."""
import http.client
import json
from pathlib import Path
import threading
from epicbyte.api import make_server
ROOT=Path(__file__).resolve().parents[1]
server=make_server(ROOT/'.factory/factory.sqlite3',ROOT,0)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
report={}
try:
 for route in ['/','/api/state','/api/events?once=1','/api/capabilities']:
  conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=25)
  conn.request('GET',route,headers={'Authorization':'Bearer '+server.access})
  res=conn.getresponse();raw=res.read();report[route]={'status':res.status,'bytes':len(raw)}
  if route=='/api/state':
   data=json.loads(raw);report['preserved_missions']=[{'id':m['id'],'state':m['state']} for m in data['missions']];report['agents']=[a['name'] for a in data['agents']]
  if route=='/api/capabilities':report['capabilities']=json.loads(raw)
  conn.close()
 report['passed']=all(report[r]['status']==200 for r in ['/','/api/state','/api/events?once=1','/api/capabilities'])
finally:
 server.shutdown();server.server_close();thread.join()
(ROOT/'logs/studio_http_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
