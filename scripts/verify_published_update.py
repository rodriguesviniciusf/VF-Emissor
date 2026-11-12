"""Confere o canal publicado como faria um cliente antigo; não instala nem usa dados fiscais."""
import json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'base'))
from app_updates import ReleaseUpdater

expected=json.loads((ROOT/'version.json').read_text(encoding='utf-8'))['version']
channel=json.loads((ROOT/'release-channel.json').read_text(encoding='utf-8'))
with tempfile.TemporaryDirectory(prefix='vf-published-update-') as tmp:
    root=Path(tmp)
    (root/'release-channel.json').write_text(json.dumps(channel),encoding='utf-8')
    updater=ReleaseUpdater(root,root/'data','0.18.0')
    release=updater.check()
    assert release.get('available') and release['version']==expected, 'A versão esperada não está disponível no canal público.'
    installer=updater.download(release)
    print(json.dumps(dict(previous_version='0.18.0',offered_version=release['version'],available=True,
                         installer_bytes=installer.stat().st_size,sha256_verified=True,windows_exe_verified=True)))
