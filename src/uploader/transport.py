"""R HOME authenticated OTA, following the recovered app command structure."""
import hashlib
import json
import re
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit
import boto3
from botocore.config import Config

API='https://api.anthbot.com/api/v1'

class UpdateError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise UpdateError('Unexpected service redirect; no credentials forwarded.')

def api_request(path,payload=None,token=None):
    headers={'version':'v1','Content-Type':'application/json'}
    if token:
        headers['Authorization']='Bearer '+token
    req=urllib.request.Request(API+path,headers=headers,
        data=None if payload is None else json.dumps(payload).encode())
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as response:
            result=json.loads(response.read(2*1024*1024))
    except urllib.error.HTTPError as error:
        raise UpdateError(f'R HOME returned HTTP {error.code}. Check account details and region.') from None
    except (OSError,ValueError):
        raise UpdateError('Could not read a response from R HOME. Check your Internet connection.') from None
    if not isinstance(result,dict) or result.get('code')!=0:
        raise UpdateError('R HOME rejected the request. Check account details and account region.')
    return result.get('data')

def verification_token(sn,now=None):
    t=str(int((time.time() if now is None else now)+0.5))
    return hashlib.md5((sn+t).encode()).hexdigest()+t

def make_client(credentials):
    endpoint=credentials.get('endpoint','')
    parts=urlsplit(endpoint if '://' in endpoint else 'https://'+endpoint)
    if (parts.scheme!='https' or not parts.hostname or
        not parts.hostname.endswith('.amazonaws.com') or parts.username or parts.password or
        parts.port not in (None,443) or parts.path not in ('','/') or parts.query or parts.fragment):
        raise UpdateError('R HOME returned an unsupported IoT endpoint.')
    region=credentials.get('region_name','')
    if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d',region):
        raise UpdateError('R HOME returned an invalid IoT region.')
    for key in ('access_key_id','secret_access_key','session_token'):
        if not isinstance(credentials.get(key),str) or not credentials[key]:
            raise UpdateError('R HOME did not return complete temporary credentials.')
    return boto3.client('iot-data',endpoint_url='https://'+parts.hostname,region_name=region,
        aws_access_key_id=credentials['access_key_id'],aws_secret_access_key=credentials['secret_access_key'],
        aws_session_token=credentials['session_token'],
        config=Config(connect_timeout=10,read_timeout=20,retries={'total_max_attempts':1}))

class Cloud:
    def __init__(self):
        self.token=None; self.client=None; self.sn=None; self.last_credentials=0

    def login(self,username,password,area,sn):
        if not re.fullmatch(r'[A-Za-z0-9_-]{6,64}',sn):
            raise UpdateError('Enter the mower serial number shown in R HOME.')
        auth=api_request('/login',{'username':username,'password':password,'areaCode':area})
        if not isinstance(auth,dict) or not auth.get('access_token'):
            raise UpdateError('Login did not return an access token.')
        self.token=auth['access_token']; self.sn=sn
        devices=api_request('/device/bind/list',token=self.token)
        if not isinstance(devices,list) or not any(isinstance(d,dict) and d.get('sn')==sn for d in devices):
            self.token=None; self.sn=None
            raise UpdateError('This mower serial is not in the signed-in account. Check the serial in R HOME.')
        self.refresh_credentials()
        return self.shadow()

    def refresh_credentials(self):
        if not self.token or not self.sn:
            raise UpdateError('Sign in first.')
        creds=api_request('/device/v2/iot/sts/arn',
            {'sn':self.sn,'verification_token':verification_token(self.sn)},self.token)
        try:
            self.client=make_client(creds)
            self.last_credentials=time.monotonic()
        finally:
            if isinstance(creds,dict): creds.clear()

    def ensure_client(self):
        if self.client is None or time.monotonic()-self.last_credentials>240:
            self.refresh_credentials()

    def shadow(self):
        self.ensure_client()
        try:
            response=self.client.get_thing_shadow(thingName=self.sn,shadowName='property')
            body=response['payload']
            try: data=json.loads(body.read(2*1024*1024))
            finally: body.close()
            if not isinstance(data.get('state',{}).get('reported'),dict):
                raise ValueError('Missing reported state')
            return data
        except Exception:
            raise UpdateError('Could not read the mower status. Check connection and account access.') from None

    def publish(self,version,url):
        self.ensure_client()
        command={'state':{'desired':{'cmd':'ota_start','data':{'version':version,'url':url}}}}
        try:
            self.client.publish(topic=f'$aws/things/{self.sn}/shadow/name/service/update',
                                payload=json.dumps(command,separators=(',',':')).encode())
        except Exception:
            # A timeout can happen after acceptance. Never automatically retry.
            raise UpdateError('Update request outcome is unknown. Check R HOME before attempting another update.') from None

def status_view(shadow):
    r=shadow.get('state',{}).get('reported',{})
    fw=r.get('fw_version',{}); ota=r.get('ota_status',{})
    return {'online':r.get('online')==1,'mode':r.get('mode','unknown'),
        'battery':r.get('elec'),'installed_version':fw.get('ui_board','unknown') if isinstance(fw,dict) else 'unknown',
        'ota_state':ota.get('ota_state','') if isinstance(ota,dict) else '',
        'ota_progress':ota.get('ota_progress',0) if isinstance(ota,dict) else 0,
        'shadow_version':shadow.get('version',0)}

def ready_for_update(shadow,now=None):
    s=status_view(shadow)
    if not s['online']: raise UpdateError('Mower is offline. Power it on and connect it to Wi-Fi.')
    if s['mode'] not in ('charge','pause','idle','sleep'):
        raise UpdateError('Stop the mower and place it on its charging station before updating.')
    if not isinstance(s['battery'],(int,float)) or not 20<=s['battery']<=100:
        raise UpdateError('The mower needs at least 20% battery for an update.')
    # Shadow envelope timestamp alone can be refreshed by unrelated writes.
    # Require recent device-field observations, rather than a cached online flag.
    metadata=shadow.get('metadata',{}).get('reported',{})
    observed=[metadata.get(k,{}).get('timestamp',0) for k in ('online','mode','elec')]
    current=time.time() if now is None else now
    if any(not isinstance(t,(int,float)) or not -30<=current-t<=300 for t in observed):
        raise UpdateError('Mower status is stale. Open R HOME, wake the mower, then refresh status.')
    return s

def ota_is_fresh(shadow,started,baseline):
    if shadow.get('version',0)<=baseline: return False
    meta=shadow.get('metadata',{}).get('reported',{}).get('ota_status',{})
    timestamp=meta.get('ota_state',{}).get('timestamp',0)
    return isinstance(timestamp,(int,float)) and timestamp>=started
