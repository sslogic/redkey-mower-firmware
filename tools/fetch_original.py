"""Download the public vendor image for LOCAL use; never add it to Git."""
import argparse,hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL='https://ldrobotota.s3.amazonaws.com/0.3.5.6.release.bin'
SHA256='370b8e6d29a77764cf685498fc9e855f93ac992e5ebf5ae17292e666c6b67bae'
SIZE=1972000

def fetch(output):
    if output.exists():
        if hashlib.sha256(output.read_bytes()).hexdigest()!=SHA256:
            raise ValueError('Existing file has a different hash; preserving it without overwrite.')
        return {'status':'existing_verified','sha256':SHA256,'bytes':SIZE}
    request=urllib.request.Request(URL,headers={'User-Agent':'redkey-firmware-research'})
    with urllib.request.urlopen(request,timeout=30) as response:
        if not response.url.startswith('https://'):raise ValueError('Download redirected away from HTTPS.')
        data=response.read(SIZE+1)
    if len(data)!=SIZE or hashlib.sha256(data).hexdigest()!=SHA256:
        raise ValueError('Vendor response does not match the documented original image; nothing saved.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(data)
    return {'status':'downloaded_verified','sha256':SHA256,'bytes':SIZE,
            'notice':'Contains vendor-embedded credential material. Keep local; do not commit.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'firmware/original/redkey-v0.3.5.6.bin')
    print(json.dumps(fetch(p.parse_args().output),indent=2))
