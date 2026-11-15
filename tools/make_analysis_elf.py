"""Reconstruct segment addresses in an ANALYSIS-ONLY ELF, never flash this output."""
import argparse,hashlib,json,struct
from pathlib import Path
from inspect_firmware import inspect,ROOT

def build(source,output):
    data=source.read_bytes();meta=inspect(source)
    if meta['sha256']!='370b8e6d29a77764cf685498fc9e855f93ac992e5ebf5ae17292e666c6b67bae':
        raise ValueError('This section layout is specific to the documented original image.')
    if output.exists():raise FileExistsError('Use a new output filename.')
    segments=meta['segments'];section_names=['.rodata','.data','.iram0','.flash.text','.iram1','.rtc']
    names=b'\0'+b''.join(n.encode()+b'\0' for n in section_names)+b'.shstrtab\0'
    blob=bytearray(52+32*len(segments));headers=[];sections=[bytes(40)];layout=[]
    for seg,name in zip(segments,section_names):
        blob+=b'\0'*((-len(blob))%16);offset=len(blob);address=int(seg['load_address'],16)
        payload=data[seg['file_offset']:seg['file_offset']+seg['bytes']];blob+=payload
        flags=6 if seg['index']>=2 else (3 if seg['index']==1 else 2)
        pflags=5 if flags==6 else (6 if flags==3 else 4)
        headers.append(struct.pack('<8I',1,offset,address,address,len(payload),len(payload),pflags,4))
        sections.append(struct.pack('<10I',names.index(name.encode()+b'\0'),1,flags,address,offset,len(payload),0,0,4,0))
        layout.append(dict(seg,elf_offset=offset,section=name))
    string_offset=len(blob);blob+=names
    sections.append(struct.pack('<10I',names.index(b'.shstrtab\0'),3,0,0,string_offset,len(names),0,0,1,0))
    blob+=b'\0'*((-len(blob))%4);shoff=len(blob);blob+=b''.join(sections)
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    blob[:52]=struct.pack('<16sHHIIIIIHHHHHH',ident,2,94,1,int(meta['entry_address'],16),52,shoff,0x300,52,32,len(headers),40,len(sections),len(sections)-1)
    blob[52:52+32*len(headers)]=b''.join(headers)
    for seg in layout:
        assert blob[seg['elf_offset']:seg['elf_offset']+seg['bytes']]==data[seg['file_offset']:seg['file_offset']+seg['bytes']]
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(blob)
    return {'purpose':'analysis_only_not_flashable','segments_verified':len(layout),'sha256':hashlib.sha256(blob).hexdigest()}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--image',type=Path,default=ROOT/'firmware/original/redkey-v0.3.5.6.bin')
    args=p.parse_args();print(json.dumps(build(args.image,args.output),indent=2))
