"""Inspect a locally downloaded image; this tool never flashes or contacts a device."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'/'uploader'))
from image_check import inspect_image

def inspect(path):
    data=path.read_bytes();result=inspect_image(data)
    result.update(entry_address=hex(struct.unpack_from('<I',data,4)[0]),
                  secure_version=struct.unpack_from('<I',data,36)[0],segments=[])
    offset=24
    for index in range(data[1]):
        address,size=struct.unpack_from('<II',data,offset);offset+=8
        result['segments'].append({'index':index,'load_address':hex(address),'file_offset':offset,'bytes':size})
        offset+=size
    result['checksum_offset']=(offset//16)*16+15
    result['appended_digest']=data[-32:].hex()
    result['appended_digest_matches']=hashlib.sha256(data[:-32]).digest()==data[-32:]
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',nargs='?',type=Path,default=ROOT/'firmware/original/redkey-v0.3.5.6.bin')
    print(json.dumps(inspect(p.parse_args().image),indent=2))
