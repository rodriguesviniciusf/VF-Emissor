"""Entrada instalada: instância única, atualização antes de abrir e dados fixos."""
import json,os,sys,urllib.request,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'base'))
from desktop_storage import data_directory,migrate_bundled,backup_before_update
from app_updates import ReleaseUpdater,launch_installer

def main():
    data=data_directory(ROOT);data.mkdir(parents=True,exist_ok=True)
    mutex=None
    if sys.platform=='win32':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        mutex=kernel.CreateMutexW(None,False,'Local\\VFEmissorLocal')
        if not mutex:raise OSError('Não foi possível iniciar a instância do emissor.')
        if ctypes.get_last_error()==183:
            kernel.CloseHandle(mutex);webbrowser.open('http://127.0.0.1:8787');return 0
    try:
        migrate_bundled(ROOT,data)
        version=json.loads((ROOT/'version.json').read_text(encoding='utf-8'))['version']
        updater=ReleaseUpdater(ROOT,data,version)
        if sys.platform=='win32' and updater.configuration().get('repository'):
            print('VF Emissor: verificando atualizações...',flush=True)
            try:
                release=updater.check()
                if release.get('available'):
                    print('Baixando atualização '+release['version']+'...',flush=True)
                    installer=updater.download(release);backup_before_update(data,release['version']);launch_installer(installer,os.getpid());return 0
            except (ValueError,OSError):
                updater.status_write(error='Atualização não aplicada. O programa foi aberto na versão instalada; uma nova tentativa será feita ao iniciar novamente.')
        import server
        sys.argv=[str(ROOT/'server.py'),'--data-dir',str(data)]
        return server.main()
    finally:
        if mutex:kernel.CloseHandle(mutex)

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        import traceback
        data=data_directory(ROOT);data.mkdir(parents=True,exist_ok=True)
        with (data/'inicio-erro.log').open('a',encoding='utf-8') as out:traceback.print_exc(file=out)
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'O emissor não conseguiu iniciar. Consulte inicio-erro.log na pasta de dados.','VF Emissor',16)
        raise
