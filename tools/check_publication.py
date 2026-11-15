"""Structural privacy checks for this public tree; not a proof against unknown secrets."""
import hashlib,json,re,sys,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','.venv','__pycache__','analysis-output'}
PATTERNS={
    'personal_windows_path':re.compile(rb'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s"<>]+',re.I),
    'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'aws_access_key':re.compile(rb'(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])'),
    'jwt':re.compile(rb'eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}'),
    'signed_download_url':re.compile(rb'https?://[^\s"<>]+[?&](?:X-Amz-Signature|X-Amz-Credential)=',re.I),
}

def run():
    failures=[];files=[]
    local_image='firmware/original/redkey-v0.3.5.6.bin'
    if (ROOT/'.git').exists():
        tracked=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0')
        if local_image in tracked:failures.append((local_image,'vendor_binary_must_not_be_committed'))
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if not path.is_file() or any(p in SKIP or p.startswith('output-') for p in rel.parts):continue
        if rel.as_posix()==local_image:continue
        data=path.read_bytes();files.append(rel.as_posix())
        if path.suffix.lower() in ('.apk','.xapk','.aab','.har','.pcap','.pcapng','.bin'):
            failures.append((rel.as_posix(),'unapproved_binary_or_capture'))
        for label,pattern in PATTERNS.items():
            if pattern.search(data):failures.append((rel.as_posix(),label))
    binary=ROOT/local_image
    if binary.exists() and hashlib.sha256(binary.read_bytes()).hexdigest()!='370b8e6d29a77764cf685498fc9e855f93ac992e5ebf5ae17292e666c6b67bae':
        failures.append((local_image,'local_download_hash_mismatch'))
    page=(ROOT/'src/uploader/index.html').read_text(encoding='utf-8')
    if re.search(r'<input id="serial"[^>]*\bvalue="[^"]+"',page):failures.append(('src/uploader/index.html','prefilled_serial'))
    result={'files_checked':len(files),'failures':failures,'result':'pass' if not failures else 'fail',
            'vendor_binary_published':False,'scope':'Public content structure; known private values checked separately.'}
    print(json.dumps(result,indent=2));return bool(failures)

if __name__=='__main__':sys.exit(run())
