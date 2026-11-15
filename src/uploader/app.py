"""Local Redkey firmware upload UI. Launching never sends an OTA command."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import ipaddress
import json
import secrets
import socket
import threading
import time
import urllib.request
from urllib.parse import urlsplit,unquote
from image_check import inspect_image,MAX_IMAGE
from transport import Cloud,UpdateError,status_view,ready_for_update,ota_is_fresh

ROOT=Path(__file__).resolve().parent
RELEASE=json.loads((ROOT/'release.json').read_text())

def lan_addresses():
    result=[]
    for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
        addr=item[4][0]; ip=ipaddress.ip_address(addr)
        if ip.is_private and not ip.is_loopback and not ip.is_link_local and addr not in result:
            result.append(addr)
    return result

class FirmwareHost:
    def __init__(self,data,ip):
        if ip not in lan_addresses():
            raise UpdateError('Select this computer’s Wi-Fi/LAN address.')
        self.data=data; self.sent=0; self.path='/'+secrets.token_urlsafe(24)+'/firmware.bin'
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_HEAD(self): self.deliver(False)
            def do_GET(self): self.deliver(True)
            def deliver(self,body):
                if self.path!=owner.path:
                    self.send_error(404); return
                start=0; end=len(data)-1; code=200
                value=self.headers.get('Range')
                if value:
                    import re
                    m=re.fullmatch(r'bytes=(\d+)-(\d*)',value)
                    if not m:
                        self.send_error(416); return
                    start=int(m[1]); end=min(int(m[2]) if m[2] else end,end)
                    if not 0<=start<=end<len(data):
                        self.send_error(416); return
                    code=206
                self.send_response(code)
                self.send_header('Content-Type','application/octet-stream')
                self.send_header('Content-Length',str(end-start+1))
                self.send_header('Accept-Ranges','bytes')
                self.send_header('Cache-Control','no-store')
                if code==206: self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}')
                self.end_headers()
                if body:
                    try:
                        self.wfile.write(data[start:end+1]); owner.sent+=end-start+1
                    except (OSError,ConnectionError): pass
        self.server=ThreadingHTTPServer((ip,0),Handler)
        self.server.daemon_threads=True
        self.url=f'http://{ip}:{self.server.server_port}{self.path}'
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def close(self):
        self.server.shutdown(); self.server.server_close()

class Controller:
    def __init__(self):
        self.lock=threading.RLock(); self.cloud=Cloud(); self.image=None; self.data=None
        self.shadow=None; self.host=None; self.job=None; self.message='Choose firmware to begin.'
    def state(self):
        return {'release':RELEASE,'image':self.image,'connected':self.shadow is not None,
                'mower':status_view(self.shadow) if self.shadow else None,
                'serial':self.cloud.sn,'addresses':lan_addresses(),'job':self.job,
                'message':self.message,'bytes_served':self.host.sent if self.host else 0}
    def select(self,data,name):
        if self.job: raise UpdateError('An update session is active. Keep the selected image available until it ends.')
        checked=inspect_image(data)
        self.data=data; self.image=dict(checked,name=Path(name.replace('\\','/')).name[:120])
        self.message='Firmware integrity checks passed. Sign in to read the mower status.'
    def login(self,p):
        if self.job: raise UpdateError('Cannot change account during an update session.')
        cloud=Cloud()
        try: shadow=cloud.login(p['username'],p['password'],p['areaCode'],p['sn'])
        finally: p['password']=''
        self.cloud=cloud; self.shadow=shadow
        self.message='Connected to R HOME. Review the mower and firmware before uploading.'
    def refresh(self):
        self.shadow=self.cloud.shadow()
        if not self.job: return
        s=status_view(self.shadow)
        if ota_is_fresh(self.shadow,self.job['started'],self.job['baseline']):
            if s['ota_state']=='success':
                self.job['status']='device_reported_success'
                self.message='Mower reports update success. Refresh after reboot to verify the installed version.'
            elif s['ota_state']=='failed':
                self.job['status']='device_reported_failure'
                self.message='Mower reports that the update failed. Check R HOME for details.'
            elif s['mode']=='ota':
                self.job['status']='installing'; self.message='Mower is updating. Keep the computer and mower powered on.'
        if self.job['status']=='device_reported_success' and s['installed_version'].lstrip('v')==self.image['version'].lstrip('v'):
            meta=self.shadow.get('metadata',{}).get('reported',{}).get('fw_version',{}).get('ui_board',{})
            if meta.get('timestamp',0)>=self.job['started']:
                self.job['status']='version_confirmed'; self.message='Mower reports success and the selected firmware version.'
        if self.job['status'] in ('command_sent','outcome_unknown') and time.time()-self.job['started']>30:
            self.message='No fresh installation acknowledgment yet. Keep this window open and check R HOME; do not resend automatically.'
    def start(self,p):
        if self.job: raise UpdateError('An update was already requested in this session. Check its result before starting another.')
        if not self.image or not self.data or not self.shadow: raise UpdateError('Choose firmware and connect the mower first.')
        if p.get('sha256')!=self.image['sha256'] or p.get('serial')!=self.cloud.sn or p.get('confirmed') is not True:
            raise UpdateError('Review and confirm the selected image and mower.')
        self.shadow=self.cloud.shadow(); ready_for_update(self.shadow)
        self.host=FirmwareHost(self.data,p['address'])
        self.job={'status':'sending','started':int(time.time()),'baseline':self.shadow.get('version',0)}
        # Do not change either bytes or version. The descriptor identifies the actual build.
        try:
            self.cloud.publish(self.image['version'].lstrip('v'),self.host.url)
            self.job['status']='command_sent'
            self.message='Update command sent. Waiting for the mower to download and report progress.'
        except UpdateError:
            self.job['status']='outcome_unknown'
            self.message='Request outcome unknown. Keep firmware hosting active and check R HOME before retrying.'
            raise
    def close(self):
        if self.host: self.host.close()

def create_server(controller=None,port=49316):
    control=controller or Controller(); nonce=secrets.token_urlsafe(32)
    class UIHandler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,status,content,kind='application/json'):
            data=content if isinstance(content,bytes) else json.dumps(content).encode()
            self.send_response(status); self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'")
            self.end_headers(); self.wfile.write(data)
        def allowed(self,write=False):
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}': return False
            if write and self.headers.get('X-Local-Token')!=nonce: return False
            origin=self.headers.get('Origin')
            return origin in (None,f'http://127.0.0.1:{self.server.server_port}')
        def do_GET(self):
            if not self.allowed(): return self.send(403,{'error':'Local access only.'})
            if self.path=='/':
                page=(ROOT/'index.html').read_text(encoding='utf-8').replace('__NONCE__',nonce)
                return self.send(200,page.encode(),'text/html; charset=utf-8')
            if self.path=='/state':
                with control.lock: return self.send(200,control.state())
            self.send(404,{'error':'Not found.'})
        def do_POST(self):
            if not self.allowed(True): return self.send(403,{'error':'Reload this local page and try again.'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                limit=MAX_IMAGE if self.path=='/image' else 16384
                if not 0<size<=limit: return self.send(413,{'error':'File or request is too large or empty.'})
                data=self.rfile.read(size)
                if len(data)!=size: raise ValueError('Incomplete request.')
                with control.lock:
                    if self.path=='/image': control.select(data,unquote(self.headers.get('X-Filename','firmware.bin')))
                    else:
                        payload=json.loads(data)
                        if self.path=='/login': control.login(payload)
                        elif self.path=='/refresh': control.refresh()
                        elif self.path=='/upload': control.start(payload)
                        elif self.path=='/shutdown':
                            if control.job and payload.get('confirmed') is not True:
                                raise UpdateError('Confirm closing the uploader while an update session exists.')
                            self.send(200,{'closed':True})
                            threading.Thread(target=self.server.shutdown,daemon=True).start()
                            return
                        else: return self.send(404,{'error':'Not found.'})
                    self.send(200,control.state())
            except (UpdateError,ValueError,KeyError) as error:
                self.send(400,{'error':str(error)})
            except Exception:
                self.send(500,{'error':'Operation failed. Refresh status before trying again; an update command is never automatically retried.'})
    server=ThreadingHTTPServer(('127.0.0.1',port),UIHandler)
    server.daemon_threads=True; server.controller=control
    return server

if __name__=='__main__':
    server=create_server()
    print(f'Firmware uploader: http://127.0.0.1:{server.server_port}/',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.controller.close(); server.server_close()
