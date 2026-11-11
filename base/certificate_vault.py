"""Cofre A1 por empresa. DPAPI de usuário; nunca há fallback em texto claro."""
import base64,ctypes,hashlib,json,os,sys,tempfile
from pathlib import Path

class WindowsProtector:
    def __init__(self):
        if sys.platform!='win32':raise ValueError('Salvar o certificado exige a proteção do Windows.')
    def _call(self,data,entropy,decrypt=False):
        from ctypes import wintypes as W
        class Blob(ctypes.Structure):_fields_=[('size',W.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
        def blob(value):
            buf=ctypes.create_string_buffer(value);return Blob(len(value),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte))),buf
        inp,keep=blob(data);ent,keep_ent=blob(entropy);out=Blob()
        crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        name='CryptUnprotectData' if decrypt else 'CryptProtectData';fn=getattr(crypt,name)
        fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p if decrypt else W.LPCWSTR,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,W.DWORD,ctypes.POINTER(Blob)];fn.restype=W.BOOL
        kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
        if not fn(ctypes.byref(inp),None if decrypt else 'VF Emissor A1',ctypes.byref(ent),None,None,1,ctypes.byref(out)):
            raise ValueError('O Windows não conseguiu abrir ou proteger este certificado. Selecione o A1 novamente nesta conta do Windows.')
        try:return ctypes.string_at(out.data,out.size)
        finally:
            if out.data:ctypes.memset(out.data,0,out.size);kernel.LocalFree(out.data)
    def protect(self,data,entropy):return self._call(data,entropy)
    def unprotect(self,data,entropy):return self._call(data,entropy,True)

class CertificateVault:
    def __init__(self,root,protector=None):self.root=Path(root);self.protector=protector
    def path(self,cid):return self.root/(hashlib.sha256(str(cid).encode()).hexdigest()+'.dpapi')
    def exists(self,cid):return self.path(cid).is_file()
    def entropy(self,cid,cnpj):return ('VF-Emissor:A1:v1:'+str(cid)+':'+str(cnpj)).encode()
    def save(self,cid,cnpj,pfx,password):
        protector=self.protector or WindowsProtector()
        payload=json.dumps(dict(format=1,company=str(cid),cnpj=str(cnpj),pfx=base64.b64encode(pfx).decode(),password=password),ensure_ascii=False).encode()
        sealed=protector.protect(payload,self.entropy(cid,cnpj))
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,temp=tempfile.mkstemp(dir=self.root,prefix='.a1-')
        try:
            with os.fdopen(fd,'wb') as f:f.write(sealed);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.path(cid))
        finally:
            if os.path.exists(temp):os.unlink(temp)
    def load(self,cid,cnpj):
        sealed=self.path(cid).read_bytes()
        if len(sealed)>8*1024*1024:raise ValueError('Arquivo de certificado protegido inválido.')
        try:data=json.loads((self.protector or WindowsProtector()).unprotect(sealed,self.entropy(cid,cnpj)))
        except (ValueError,UnicodeError) as e:raise ValueError('Não foi possível abrir o certificado salvo. Selecione o A1 novamente nesta conta do Windows.') from e
        if not isinstance(data,dict) or data.get('format')!=1 or data.get('company')!=str(cid) or data.get('cnpj')!=str(cnpj) or not isinstance(data.get('pfx'),str) or not isinstance(data.get('password'),str):raise ValueError('Certificado salvo não pertence a esta empresa.')
        return base64.b64decode(data['pfx'],validate=True),data['password']
    def remove(self,cid):self.path(cid).unlink(missing_ok=True)
