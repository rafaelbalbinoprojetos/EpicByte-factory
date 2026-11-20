import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from epicbyte.api import make_server
from epicbyte.storage import Store

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'agents').mkdir()
        from epicbyte.model import AGENTS
        for agent in AGENTS: (self.root/'agents'/f'{agent}.md').write_text('Responsabilidade de '+agent)
        (self.root/'workspaces').mkdir()
        self.db = self.root/'test.sqlite3'
        self.store = Store(self.db)
        self.store.create('mission_test','# Teste',self.root/'workspaces/test')
        self.server = make_server(self.db,self.root,0)
        self.port = self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.store.db.close();self.temp.cleanup()
    def call(self,path='/api/state',body=None,auth=True,origin=None,host=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port)
        headers={'Host':host or f'127.0.0.1:{self.port}'}
        if auth: headers['Authorization']='Bearer '+self.server.access
        if origin: headers['Origin']=origin
        if body is not None: headers['Content-Type']='application/json'
        connection.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers)
        response=connection.getresponse();content=response.read().decode();code=response.status;connection.close()
        return code,content
    @property
    def origin(self): return f'http://127.0.0.1:{self.port}'
    def test_read_requires_local_authentication(self):
        self.assertEqual(self.call(auth=False)[0],403)
        self.assertEqual(self.call(host='evil.test')[0],403)
        self.assertEqual(self.call(origin='https://evil.test')[0],403)
        code,body=self.call();self.assertEqual(code,200)
        state=json.loads(body);self.assertEqual(len(state['agents']),9);self.assertEqual(state['missions'][0]['id'],'mission_test')
        self.assertFalse(state['diagnostic']['isolation_certified'])
    def test_mutation_rejects_csrf_and_missing_auth(self):
        self.assertEqual(self.call('/api/missions/mission_test/pause',{})[0],403)
        self.assertEqual(self.call('/api/missions/mission_test/pause',{},origin='https://evil.test')[0],403)
        self.assertEqual(self.call('/api/missions/mission_test/pause',{},auth=False,origin=self.origin)[0],403)
        self.assertEqual(self.store.mission('mission_test')['state'],'CREATED')
    def test_pause_is_persisted_and_events_cursor(self):
        code,_=self.call('/api/missions/mission_test/pause',{},origin=self.origin)
        self.assertEqual(code,200);self.assertEqual(self.store.mission('mission_test')['state'],'PAUSED')
        code,body=self.call('/api/events?after=1&once=1');self.assertEqual(code,200);self.assertIn('PAUSE_REQUESTED',body);self.assertNotIn('MISSION_CREATED',body)
    def payload(self): return dict(name='Teste',description='Objetivo',criteria='Testes',workspace='managed',dry_run=True,limits={'max_executions':5})
    def test_dry_run_has_no_workspace_or_provider(self):
        before=list((self.root/'workspaces').iterdir())
        code,body=self.call('/api/missions',self.payload(),origin=self.origin)
        self.assertEqual(code,200);self.assertTrue(json.loads(body)['dry_run']);self.assertEqual(before,list((self.root/'workspaces').iterdir()))
    def test_arbitrary_workspace_and_limits_rejected(self):
        data=self.payload();data['workspace']='C:/outside'
        self.assertEqual(self.call('/api/missions',data,origin=self.origin)[0],409)
        data=self.payload();data['limits']={'max_executions':101}
        self.assertEqual(self.call('/api/missions',data,origin=self.origin)[0],409)
    def test_creation_fails_closed_on_certification(self):
        data=self.payload();data['dry_run']=False
        with patch('epicbyte.write_backend.certify',return_value={'certified':False,'checks':[]}):
            code,_=self.call('/api/missions',data,origin=self.origin)
        self.assertEqual(code,409);self.assertFalse((self.root/'.factory/incoming').exists())
    def test_start_fails_closed(self):
        with patch('epicbyte.api.IsolationPolicy.require_write',side_effect=RuntimeError('not certified')):
            self.assertEqual(self.call('/api/missions/mission_test/start',{},origin=self.origin)[0],409)
        self.assertEqual(self.store.mission('mission_test')['state'],'CREATED');self.assertEqual(self.server.workers,{})
    def test_unknown_operation_and_terminal_controls(self):
        self.assertEqual(self.call('/api/missions/mission_test/delete',{},origin=self.origin)[0],409)
        self.store.transition('mission_test','FAILED')
        self.assertEqual(self.call('/api/missions/mission_test/pause',{},origin=self.origin)[0],409)
    def test_legacy_reads_preserved(self):
        self.assertEqual(self.call('/missions',auth=False)[0],200)
        self.assertEqual(self.call('/missions/mission_test/events',auth=False)[0],200)
        self.assertEqual(self.call('/missions',auth=False,origin='https://evil.test')[0],403)
    def test_invalid_cursor_is_bad_request(self):
        self.assertEqual(self.call('/api/events?after=bad')[0],400)
    def test_creation_contract_and_limits_persist(self):
        data=self.payload();data['dry_run']=False
        with patch('epicbyte.write_backend.certify',return_value={'certified':True,'checks':[]}):
            code,body=self.call('/api/missions',data,origin=self.origin)
        self.assertEqual(code,201)
        ident=json.loads(body)['id']
        mission=self.store.mission(ident)
        self.assertEqual(mission['state'],'CREATED')
        self.assertTrue(Path(mission['workspace']).is_relative_to(self.root/'workspaces'))
        from epicbyte.safety import validate_git
        self.assertEqual(validate_git(mission['workspace']),'develop')
        from epicbyte.engine import limits_for
        self.assertEqual(limits_for(self.store,ident).max_executions,5)
        reopened=Store(self.db)
        try: self.assertEqual(limits_for(reopened,ident).max_executions,5)
        finally: reopened.db.close()
    def test_start_authorizes_and_launches_only_python_worker(self):
        with patch('epicbyte.api.IsolationPolicy.require_write') as isolation, patch('epicbyte.diagnostics.doctor',return_value={'ready_read_only':True}), patch('epicbyte.api.subprocess.Popen') as process:
            process.return_value.poll.return_value=None
            code,_=self.call('/api/missions/mission_test/start',{},origin=self.origin)
            self.assertEqual(code,202)
            self.assertIn('epicbyte.worker',process.call_args.args[0])
            isolation.assert_called_once_with(Path(self.store.mission('mission_test')['workspace']))
            self.assertEqual(self.call('/api/missions/mission_test/start',{},origin=self.origin)[0],409)
            process.assert_called_once()
    def test_static_assets_and_traversal(self):
        folder=self.root/'frontend/dist';folder.mkdir(parents=True)
        (folder/'index.html').write_text('<title>Mission Control</title>')
        self.assertIn('Mission Control',self.call('/',auth=False)[1])
        self.assertEqual(self.call('/../../test.sqlite3',auth=False)[0],404)
    def test_corrupt_json_and_wrong_content_type(self):
        connection=http.client.HTTPConnection('127.0.0.1',self.port)
        headers={'Authorization':'Bearer '+self.server.access,'Origin':self.origin,'Content-Type':'application/json'}
        connection.request('POST','/api/missions','{',headers)
        response=connection.getresponse();self.assertEqual(response.status,409);response.read();connection.close()
    def test_boolean_contract_is_strict(self):
        data=self.payload();data['dry_run']='true'
        self.assertEqual(self.call('/api/missions',data,origin=self.origin)[0],409)
    def test_concurrent_state_and_sse_connections(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=12) as pool:
            paths=['/api/state','/api/events?once=1']*12
            results=list(pool.map(self.call,paths))
        self.assertTrue(all(code==200 for code,_ in results))
    def test_database_open_failure_is_http_error_not_connection_reset(self):
        import sqlite3
        with patch('epicbyte.api.Store',side_effect=sqlite3.OperationalError('locked')):
            code,body=self.call()
        self.assertEqual(code,503);self.assertIn('indispon',body)
    def test_brief_http_approval_and_scope_transfer(self):
        from test_studio import proposal
        code,body=self.call('/api/briefs',{'idea':'Produto solicitado'},origin=self.origin)
        self.assertEqual(code,201);ident=json.loads(body)['id']
        self.assertEqual(self.call(f'/api/briefs/{ident}/save',{'version':0,'proposal':proposal()},origin=self.origin)[0],200)
        self.assertEqual(self.call(f'/api/briefs/{ident}/approve',{'version':1,'selected':['F1'],'design_approved':True},origin=self.origin)[0],200)
        data=self.payload();data.update(dry_run=False,brief_id=ident)
        with patch('epicbyte.write_backend.certify',return_value={'certified':True,'checks':[]}):
            code,body=self.call('/api/missions',data,origin=self.origin)
        self.assertEqual(code,201);mission=json.loads(body)['id'];source=self.store.mission(mission)['source']
        self.assertIn('APPROVED',source);self.assertNotIn('F2',source)
        code,body=self.call(f'/api/briefs/{ident}');self.assertEqual(json.loads(body)['mission'],mission)
        self.assertEqual(self.call('/api/missions',data,origin=self.origin)[0],409)
    def test_upload_http_and_no_public_file_route(self):
        from test_studio import image_payload
        _,body=self.call('/api/briefs',{'idea':'Referências'},origin=self.origin);ident=json.loads(body)['id']
        code,body=self.call(f'/api/briefs/{ident}/references',image_payload(),origin=self.origin)
        self.assertEqual(code,201);key=json.loads(body)['references'][0]['id']
        self.assertEqual(self.call(f'/api/briefs/{ident}/references/{key}',auth=False)[0],403)
        code,body=self.call(f'/api/briefs/{ident}/references/{key}');self.assertEqual(code,200);self.assertIn('content',json.loads(body))
        self.assertEqual(self.call(f'/.factory/references/{ident}/{key}.png',auth=False)[0],404)
