import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image
from epicbyte.storage import Store
from epicbyte.studio import Studio, MAX_FILE, capabilities
from epicbyte.provider import Result

def proposal():
    return {'summary':'Produto','features':[{'id':'F1','description':'Pedido','category':'REQUESTED','acceptance_criteria':['Persistir dados']},{'id':'F2','description':'Sugestão','category':'RECOMMENDED','acceptance_criteria':['Notificar']}],'design_brief':{'colors':['#101820'],'accessibility':['WCAG AA']}}

def image_payload():
    data=io.BytesIO();Image.new('RGB',(20,10),'cyan').save(data,format='PNG')
    return {'name':'../../unsafe.svg','content':base64.b64encode(data.getvalue()).decode(),'use':'Layout','avoid':'Marca'}

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.db=self.root/'db.sqlite3';self.store=Store(self.db);self.studio=Studio(self.store,self.root)
        self.brief=self.studio.create('Um produto para clientes');self.ident=self.brief['id']
        (self.root/'agents').mkdir();(self.root/'agents/solution_strategist.md').write_text('Consultoria',encoding='utf-8')
    def tearDown(self):self.store.db.close();self.temp.cleanup()
    def save(self):return self.studio.save(self.ident,proposal(),0)
    def test_additive_migration_preserves_missions(self):
        self.store.create('old','historical',self.root/'workspace');Studio(self.store,self.root)
        self.assertEqual(self.store.mission('old')['source'],'historical')
    def test_versions_and_approval_survive_reopen(self):
        self.save();self.studio.approve(self.ident,1,['F1'],True)
        reopened=Store(self.db)
        try:self.assertEqual(Studio(reopened,self.root).get(self.ident)['approvals'][0]['version'],1)
        finally:reopened.db.close()
    def test_recommendations_do_not_leak_to_source(self):
        self.save();self.studio.approve(self.ident,1,['F1'],True);source=self.studio.approved_source(self.ident)
        self.assertIn('APPROVED',source);self.assertNotIn('Sugestão',source);self.assertNotIn('F2',source)
    def test_unapproved_and_stale_scope_rejected(self):
        with self.assertRaises(ValueError):self.studio.approved_source(self.ident)
        self.save();self.studio.approve(self.ident,1,['F1'],True);self.studio.save(self.ident,proposal(),1)
        with self.assertRaises(ValueError):self.studio.approved_source(self.ident)
        with self.assertRaises(ValueError):self.studio.approve(self.ident,1,['F1'],True)
    def test_unknown_selection_and_design_approval(self):
        self.save()
        for keys,design in [(['F3'],True),(['F1'],False),([],True),(['F1','F1'],True)]:
            with self.assertRaises(ValueError):self.studio.approve(self.ident,1,keys,design)
    def test_invalid_features_rejected(self):
        for features in [[],[{'id':'x','category':'APPROVED'}]]:
            data=proposal();data['features']=features
            with self.assertRaises(ValueError):self.studio.save(self.ident,data,0)
    def test_optimistic_version(self):
        self.save()
        with self.assertRaises(ValueError):self.studio.save(self.ident,proposal(),0)
    def test_upload_real_content_reencoded_and_isolated(self):
        result=self.studio.upload(self.ident,image_payload());ref=result['references'][0]
        self.assertEqual((ref['width'],ref['height']),(20,10));self.assertEqual(len(ref['sha256']),64)
        self.assertEqual(self.studio.image(self.ident,ref['id'])['mime'],'image/png')
        second=self.studio.create('Outra ideia')
        with self.assertRaises(ValueError):self.studio.image(second['id'],ref['id'])
        self.assertFalse((self.root/'unsafe.svg').exists())
    def test_malicious_and_corrupted_formats_rejected(self):
        for raw in [b'<svg onload="alert(1)"></svg>',b'%PDF-1.7',b'RIFFfakeWEBP',b'\x89PNG\r\n\x1a\n']:
            with self.assertRaises(ValueError):self.studio.upload(self.ident,{'name':'image.png','content':base64.b64encode(raw).decode()})
    def test_upload_size_and_quantity(self):
        with self.assertRaises(ValueError):self.studio.upload(self.ident,{'name':'huge.png','content':base64.b64encode(b'x'*(MAX_FILE+1)).decode()})
        for _ in range(8):self.studio.upload(self.ident,image_payload())
        with self.assertRaises(ValueError):self.studio.upload(self.ident,image_payload())
    def test_delete_control_and_frozen_references(self):
        b=self.studio.upload(self.ident,image_payload());key=b['references'][0]['id'];self.studio.remove(self.ident,key)
        self.assertFalse(self.studio.get(self.ident)['references'])
        self.save();self.studio.approve(self.ident,1,['F1'],True)
        with self.assertRaises(ValueError):self.studio.upload(self.ident,image_payload())
    def test_tampered_reference_rejected(self):
        b=self.studio.upload(self.ident,image_payload());key=b['references'][0]['id']
        (self.root/'.factory/references'/self.ident/(key+'.png')).write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.studio.image(self.ident,key)
    def provider(self,vision):
        provider=Mock();provider.capabilities.return_value={'images':vision,'model':'local-test'};provider.execute.return_value=Result(json.dumps(proposal()),'thread','turn',provider='codex-app-server');return provider
    def test_multimodal_contract_uses_real_attachment_paths(self):
        self.studio.upload(self.ident,image_payload());p=self.provider(True);b=self.studio.analyze(self.ident,self.root,p)
        self.assertTrue(p.execute.call_args.kwargs['images'][0].is_file());self.assertFalse(p.execute.call_args.kwargs['write']);self.assertEqual(b['versions'][0]['data']['visual_analysis']['status'],'ANALYZED');self.assertEqual(b['runs'][0]['status'],'COMPLETED')
    def test_no_vision_never_invents_analysis(self):
        self.studio.upload(self.ident,image_payload());p=self.provider(False);b=self.studio.analyze(self.ident,self.root,p)
        self.assertNotIn('images',p.execute.call_args.kwargs);self.assertIn('INDISPON',p.execute.call_args.args[0]);self.assertEqual(b['versions'][0]['data']['visual_analysis']['status'],'UNAVAILABLE')
    def test_failed_analysis_is_persisted(self):
        p=self.provider(False);p.execute.side_effect=RuntimeError('Servidor indisponível')
        with self.assertRaises(RuntimeError):self.studio.analyze(self.ident,self.root,p)
        b=self.studio.get(self.ident);self.assertEqual(b['runs'][0]['status'],'FAILED');self.assertFalse(b['versions'])
    def test_capability_types(self):
        caps=capabilities();self.assertFalse(caps['svg']);self.assertFalse(caps['pdf']);self.assertFalse(caps['video'])
    def test_planner_requires_approved_feature_traceability(self):
        from epicbyte.model import validate_approved_tasks
        for ids in [None,[],['F2']]:
            with self.assertRaises(ValueError):validate_approved_tasks({'tasks':[{'feature_ids':ids}]},['F1'])
        self.assertEqual(validate_approved_tasks({'tasks':[{'feature_ids':['F1']}]},['F1'])['tasks'][0]['feature_ids'],['F1'])
    def test_client_decisions_are_preserved_and_not_invented_by_model(self):
        data=proposal();data['client_decisions']=['Equipe interna apenas'];self.studio.save(self.ident,data,0)
        provider=self.provider(False);suggested=proposal();suggested['client_decisions']=['Decisão inventada']
        provider.execute.return_value=Result(json.dumps(suggested),'thread','turn')
        brief=self.studio.analyze(self.ident,self.root,provider)
        self.assertEqual(brief['versions'][-1]['data']['client_decisions'],['Equipe interna apenas'])
        self.studio.approve(self.ident,2,['F1'],True)
        self.assertIn('Equipe interna apenas',self.studio.approved_source(self.ident))
        self.assertNotIn('Decisão inventada',self.studio.approved_source(self.ident))
    def test_server_cancellation_prevents_provider_turn(self):
        provider=self.provider(False)
        with self.assertRaises(RuntimeError):self.studio.analyze(self.ident,self.root,provider,cancelled=lambda:True)
        provider.execute.assert_not_called()
        self.assertEqual(self.studio.get(self.ident)['runs'][0]['status'],'FAILED')
