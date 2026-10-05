"""Guarded API-only staging overlay. Catalogue, vectors and other services stay pinned."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

SERVICE = 'scanapp-scanapp-z1mwj4-api-1'
IMAGE = 'scanapp-speed029-api:20261004'
BASE = 'sha256:8c8697aa6ad188aa8337a4fdba6a6ad23cc61ca7378f4e172de6ecd9c0f1062c'
CONFIG_HASH = 'e23320269091eb661c7ad7f371479975eb81931fdb6bc8ef18f716b3b060c705'
OVERRIDE_ENV = {'OCR_PARALLEL_FOOTER_HALVES': '1'}
RELEASE = 'speed029'
EXTRA_HASHES = {}
EXPECTED = {
    'ocr.py':'33b73313dc9d9aa084d400e1e10d543df5c7e72626eb3cc8795cabe670486605',
    'local_match.py':'aa114ae6876e49bb99e6fbcfd73e610a0e5ed31d0a3b1bb47c7e3292cf6bb51f',
    'reference_features.py':'8ecf690bcc8b6382a7ed6dbdef8cb0e4e2f87224a02bed5cdb93b758a627338d',
    'runtime.py':'1458a8456155e908023e90d4ecdb243c98d08924977091282f620ebe9b33aa5a',
}

def command(args, quiet=False):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL if quiet else None)

def inspect():
    return json.loads(command(['docker','inspect',SERVICE]))[0]

def health():
    return json.loads(command(['docker','exec',SERVICE,'python','-c',
        "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=5).read().decode())"], quiet=True))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--context', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--activate', action='store_true')
    args = p.parse_args()
    assert args.activate, 'Explicit activation required'
    before = inspect(); assert before['Image'] == BASE and not before['State']['OOMKilled']
    healthy = health(); assert healthy['ready']
    for name, expected in EXPECTED.items():
        actual = command(['docker','exec',SERVICE,'sha256sum','/app/app/recognition/'+name]).split()[0]
        assert actual == expected, 'Deployed source changed: '+name
    assert command(['docker','exec',SERVICE,'sha256sum','/app/app/config.py']).split()[0] == CONFIG_HASH
    for relative, expected in EXTRA_HASHES.items():
        assert command(['docker','exec',SERVICE,'sha256sum','/app/'+relative]).split()[0] == expected
    labels = before['Config']['Labels']
    assert labels['com.docker.compose.project'] == 'scanapp-scanapp-z1mwj4'
    originals = [Path(path) for path in labels['com.docker.compose.project.config_files'].split(',')]
    hashes = {str(path):digest(path) for path in originals}
    args.archive.mkdir(parents=True, exist_ok=False); os.chmod(args.archive,0o700)
    frozen = []
    for index, path in enumerate(originals):
        target = args.archive/f'compose-{index}.yaml'
        shutil.copyfile(path,target);os.chmod(target,0o600);frozen.append(target)
    working = Path(labels['com.docker.compose.project.working_dir'])
    common = ['docker','compose','--project-directory',str(working),'-p','scanapp-scanapp-z1mwj4']
    for path in frozen: common += ['-f',str(path)]
    overlay = args.archive/'speed-compose.yaml'
    overlay.write_text('services:\n  api:\n    image: '+IMAGE+'\n    environment:\n'+
        ''.join(f'      {key}: "{value}"\n' for key,value in OVERRIDE_ENV.items()))
    activate = common+['-f',str(overlay)]
    candidate = json.loads(command(activate+['config','--format','json']))['services']['api']
    env = dict(entry.split('=',1) for entry in before['Config']['Env'])
    assert candidate['image'] == IMAGE
    assert not [key for key,value in candidate['environment'].items()
        if key not in OVERRIDE_ENV and str(value) != env.get(key)], 'Unexpected environment change'
    assert all(str(candidate['environment'][key]) == value for key,value in OVERRIDE_ENV.items())
    assert int(candidate['mem_limit']) == before['HostConfig']['Memory']
    assert int(candidate['memswap_limit']) == before['HostConfig']['MemorySwap']
    other_args=['docker','inspect','--format','{{.Id}}','scanapp-scanapp-z1mwj4-web-1','scanapp-scanapp-z1mwj4-scraper-1']
    others=command(other_args)
    rollback_image='scanapp-'+RELEASE+'-rollback:20261004'
    command(['docker','tag',BASE,rollback_image])
    rollback_overlay=args.archive/'rollback-image-compose.yaml'
    rollback_overlay.write_text('services:\n  api:\n    image: '+rollback_image+'\n')
    rollback=common+['-f',str(rollback_overlay)]
    subprocess.run(['docker','build','-t',IMAGE,str(args.context)],check=True)
    candidate_hashes={str(path.relative_to(args.context)):digest(path)
        for path in (args.context/'app').rglob('*.py')}
    assert inspect()['Id'] == before['Id'] and health() == healthy, 'Deployment/catalogue changed during build'
    assert all(digest(Path(path)) == value for path,value in hashes.items()), 'Compose changed during build'
    (args.archive/'rollback-command.json').write_text(json.dumps(rollback+['up','-d','--no-deps','--no-build','api']))
    (args.archive/'health-before.json').write_text(json.dumps(healthy,indent=2))
    changed = False
    try:
        changed=True
        subprocess.run(activate+['up','-d','--no-deps','--no-build','api'],check=True)
        after=None
        for _ in range(50):
            try:
                observed=health()
                if observed['ready']:
                    after=observed;break
            except Exception:
                pass
            time.sleep(3)
        assert after == healthy, 'Catalogue/model/coverage/health contract changed'
        running=inspect();assert not running['State']['OOMKilled']
        assert running['Config']['Image'] == IMAGE and command(other_args) == others
        assert running['HostConfig']['Memory'] == before['HostConfig']['Memory']
        for relative, expected in candidate_hashes.items():
            actual=command(['docker','exec',SERVICE,'sha256sum','/app/'+relative]).split()[0]
            assert actual == expected, relative
        flag=command(['docker','exec',SERVICE,'python','-c',
            "from app.config import Settings;print(Settings().ocr_parallel_footer_halves)"]).strip()
        assert flag == 'True'
        report=dict(published=True,ready=True,api_image=running['Image'],
            catalogue_import_id=after['catalogue_import_id'],catalogue_unchanged=True,
            other_services_unchanged=True,resources_unchanged=True,rollback_archive=str(args.archive))
        (args.archive/'publication.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    except Exception:
        if changed: subprocess.run(rollback+['up','-d','--no-deps','--no-build','api'],check=True)
        raise


if __name__ == '__main__': main()
