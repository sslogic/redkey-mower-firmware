import copy
import os
import hashlib
import io
import json
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
from botocore.stub import Stubber
from image_check import inspect_image,FACTORY_SHA
from transport import Cloud,UpdateError,ready_for_update,ota_is_fresh,verification_token,make_client
from app import Controller,FirmwareHost,create_server

ROOT=Path(__file__).resolve().parent
IMAGE=Path(os.environ.get('REDKEY_FIRMWARE_PATH',str(ROOT.parents[1]/'firmware'/'original'/'redkey-v0.3.5.6.bin'))).read_bytes()

def shadow(now=None,version=2):
    now=int(time.time()) if now is None else now
    return {'version':version,'state':{'reported':{'online':1,'mode':'charge','elec':80,
        'fw_version':{'ui_board':'0.3.5.6'},'ota_status':{'ota_state':'','ota_progress':0}}},
        'metadata':{'reported':{k:{'timestamp':now} for k in ('online','mode','elec')}}}

class UploaderTests(unittest.TestCase):
    def test_original_image_is_identified_not_relabelled(self):
        info=inspect_image(IMAGE)
        self.assertEqual(info['version'],'v0.3.5.6'); self.assertEqual(info['sha256'],FACTORY_SHA)
        self.assertTrue(info['factory_original'])
        self.assertEqual(json.loads((ROOT/'release.json').read_text())['custom_firmware_version'],'0.3.6.0')

    def test_corrupt_truncated_wrong_chip_and_wrong_project_rejected(self):
        bad=bytearray(IMAGE);bad[300]^=1
        wrong=bytearray(IMAGE);wrong[12]=0
        project=bytearray(IMAGE);project[80]=ord('x');project[-32:]=hashlib.sha256(project[:-32]).digest()
        for data in (bytes(bad),IMAGE[:-10],b'route JSON',bytes(wrong),bytes(project),IMAGE+b'extra'):
            with self.assertRaises(ValueError): inspect_image(data)

    def test_invalid_selection_preserves_valid_selection(self):
        c=Controller();c.select(IMAGE,'original.bin')
        with self.assertRaises(ValueError):c.select(b'bad','bad.bin')
        self.assertEqual(c.image['sha256'],FACTORY_SHA)

    def test_token_and_account_binding(self):
        expected=hashlib.md5(b'ABC1231700000001').hexdigest()+'1700000001'
        self.assertEqual(verification_token('ABC123',1700000000.6),expected)
        cloud=Cloud()
        with patch('transport.api_request',side_effect=[{'access_token':'test'},[{'sn':'OTHER'}]]):
            with self.assertRaisesRegex(UpdateError,'not in'):cloud.login('u','p','1','ABC123')
        self.assertIsNone(cloud.token)

    def test_eligibility_rejects_unknown_offline_moving_low_battery_and_stale(self):
        ready_for_update(shadow(1000),now=1000)
        for key,value in [('online',0),('online',4294967295),('mode','mow'),('mode','ota'),('elec',19),('elec',None)]:
            s=shadow(1000);s['state']['reported'][key]=value
            with self.assertRaises(UpdateError):ready_for_update(s,now=1000)
        with self.assertRaisesRegex(UpdateError,'stale'):ready_for_update(shadow(1000),now=2000)

    def test_cached_success_is_not_fresh(self):
        s=shadow(1000,8);s['metadata']['reported']['ota_status']={'ota_state':{'timestamp':900}}
        self.assertFalse(ota_is_fresh(s,1000,7))
        s['metadata']['reported']['ota_status']['ota_state']['timestamp']=1001
        self.assertTrue(ota_is_fresh(s,1000,7));self.assertFalse(ota_is_fresh(s,1000,8))

    def test_sdk_exact_publish_and_no_retries(self):
        creds={'endpoint':'example-ats.iot.us-east-1.amazonaws.com','region_name':'us-east-1',
            'access_key_id':'testing','secret_access_key':'testing','session_token':'testing'}
        client=make_client(creds); c=Cloud();c.client=client;c.sn='ABC123';c.last_credentials=time.monotonic()
        body={'state':{'desired':{'cmd':'ota_start','data':{'version':'0.3.6.0','url':'http://192.168.1.2/a.bin'}}}}
        with Stubber(client) as stub:
            stub.add_response('publish',{}, {'topic':'$aws/things/ABC123/shadow/name/service/update',
                'payload':json.dumps(body,separators=(',',':')).encode()})
            c.publish('0.3.6.0','http://192.168.1.2/a.bin');stub.assert_no_pending_responses()
        self.assertEqual(client.meta.config.retries['total_max_attempts'],1)
        creds['endpoint']='https://example.com'
        with self.assertRaises(UpdateError):make_client(creds)

    def test_controller_sends_once_and_locks_ambiguous_result(self):
        c=Controller();c.select(IMAGE,'factory.bin');c.cloud=Mock();c.cloud.sn='ABC123'
        c.shadow=shadow();c.cloud.shadow.return_value=shadow()
        payload={'confirmed':True,'serial':'ABC123','sha256':FACTORY_SHA,'address':'192.168.1.2'}
        with patch('app.FirmwareHost') as host:
            host.return_value.url='http://192.168.1.2/token/firmware.bin'
            c.cloud.publish.side_effect=UpdateError('uncertain')
            with self.assertRaises(UpdateError):c.start(payload)
            self.assertEqual(c.job['status'],'outcome_unknown')
            with self.assertRaises(UpdateError):c.start(payload)
            c.cloud.publish.assert_called_once_with('0.3.5.6',host.return_value.url)

    def test_file_host_full_range_and_path_isolation(self):
        with patch('app.lan_addresses',return_value=['127.0.0.1']):
            host=FirmwareHost(IMAGE,'127.0.0.1')
        try:
            with urllib.request.urlopen(host.url) as r:self.assertEqual(hashlib.sha256(r.read()).hexdigest(),FACTORY_SHA)
            req=urllib.request.Request(host.url,headers={'Range':'bytes=12-33'})
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status,206);self.assertEqual(r.read(),IMAGE[12:34])
            req=urllib.request.Request(host.url,method='HEAD')
            with urllib.request.urlopen(req) as r:self.assertEqual(int(r.headers['Content-Length']),len(IMAGE))
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(host.url+'/../../app.py')
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(host.url,headers={'Range':'bytes=99999999-'}))
        finally:host.close()

    def test_ui_csrf_host_and_initial_state_no_network(self):
        c=Controller();server=create_server(c,0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base+'/state') as r:self.assertFalse(json.load(r)['connected'])
            for req in (urllib.request.Request(base+'/upload',data=b'{}'),
                        urllib.request.Request(base+'/state',headers={'Host':'evil.example'})):
                with self.assertRaises(urllib.error.HTTPError) as result:urllib.request.urlopen(req)
                self.assertEqual(result.exception.code,403)
            self.assertIsNone(c.job)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
