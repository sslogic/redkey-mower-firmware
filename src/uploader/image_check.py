"""Validate the supported ESP32-S3 application container without altering bytes."""
import hashlib
import struct

MAX_IMAGE=16*1024*1024
FACTORY_SHA='370b8e6d29a77764cf685498fc9e855f93ac992e5ebf5ae17292e666c6b67bae'

def inspect_image(data):
    if not 288<=len(data)<=MAX_IMAGE or data[0]!=0xe9:
        raise ValueError('Choose an ESP32-S3 application .bin file, not a ZIP, ELF or route file.')
    if struct.unpack_from('<H',data,12)[0]!=9:
        raise ValueError('This image is not tagged for ESP32-S3.')
    if not 1<=data[1]<=16 or data[23]!=1:
        raise ValueError('Unsupported image header or missing appended SHA-256.')
    offset=24; checksum=0xef
    for i in range(data[1]):
        if offset+8>len(data)-32:
            raise ValueError('Truncated segment header.')
        address,length=struct.unpack_from('<II',data,offset); offset+=8
        if length==0 or offset+length>len(data)-32:
            raise ValueError('Truncated or invalid segment.')
        if i==0 and (length<256 or struct.unpack_from('<I',data,offset)[0]!=0xabcd5432):
            raise ValueError('Missing ESP application descriptor.')
        for value in data[offset:offset+length]:
            checksum^=value
        offset+=length
    check_offset=(offset//16)*16+15
    if check_offset+33!=len(data):
        raise ValueError('Unsupported trailing data or truncated image; signed/combined packages require separate handling.')
    if data[check_offset]!=checksum:
        raise ValueError('Firmware checksum failed.')
    if hashlib.sha256(data[:-32]).digest()!=data[-32:]:
        raise ValueError('Firmware SHA-256 integrity check failed.')
    def field(start,length):
        return data[start:start+length].split(b'\0',1)[0].decode('ascii',errors='strict')
    version=field(48,32); project=field(80,32)
    if project!='mgc01_esp32_ui_board':
        raise ValueError('The image project does not match the inspected Redkey controller.')
    if not version or len(version)>31:
        raise ValueError('Missing application version.')
    digest=hashlib.sha256(data).hexdigest()
    return {'version':version,'project':project,'chip':'ESP32-S3','bytes':len(data),
            'sha256':digest,'factory_original':digest==FACTORY_SHA,'integrity':'passed'}
