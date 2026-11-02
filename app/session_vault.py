"""Windows user-bound DPAPI storage. No plaintext token fallback on other OSes."""
from contextlib import suppress
import csv
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import uuid


class VaultError(RuntimeError):
    pass


class DPAPI:
    def __init__(self):
        if os.name!='nt':raise VaultError('Persistent encrypted Kite sessions require Windows DPAPI on this installation.')

    def _convert(self,value,decrypt=False):
        class Blob(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
        buffer=ctypes.create_string_buffer(value)
        source=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
        result=Blob()
        crypt=ctypes.WinDLL('crypt32',use_last_error=True)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.LocalFree.argtypes=[ctypes.c_void_p]
        kernel.LocalFree.restype=ctypes.c_void_p
        # CRYPTPROTECT_UI_FORBIDDEN; default user scope, never LOCAL_MACHINE.
        operation=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        operation.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        operation.restype=wintypes.BOOL
        if not operation(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
            raise VaultError('Windows could not protect or unlock this Kite session for the current user.')
        try:return ctypes.string_at(result.data,result.size)
        finally:kernel.LocalFree(ctypes.cast(result.data,ctypes.c_void_p))

    def encrypt(self,value):return self._convert(value)
    def decrypt(self,value):return self._convert(value,True)


def private_directory(path):
    if path.is_symlink():raise VaultError('Session directory must not be a symbolic link.')
    path.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        try:
            owner=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
            sid=next(csv.reader(io.StringIO(owner.stdout)))[1]
            if not sid.startswith('S-1-'):raise ValueError('Invalid Windows identity')
            subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F'],capture_output=True,check=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        except (subprocess.SubprocessError,ValueError,IndexError,StopIteration,OSError):
            raise VaultError('Could not restrict the session directory to the current Windows user.') from None
    else:
        path.chmod(0o700)


class SessionVault:
    def __init__(self,path,api_key,codec=None,secure_directory=None):
        self.path=Path(path)
        self.identity=hashlib.sha256(api_key.encode()).hexdigest()
        self.codec=codec
        self.secure_directory=secure_directory or private_directory

    def _codec(self):
        if self.codec is None:self.codec=DPAPI()
        return self.codec

    def save(self,record):
        # Encrypt before touching disk. The complete record, including metadata, is protected.
        value=b'DCV1'+self._codec().encrypt(json.dumps({**record,'identity':self.identity}).encode())
        self._write(value)

    def _write(self,value):
        self.secure_directory(self.path.parent)
        if self.path.is_symlink():raise VaultError('Session file must not be a symbolic link.')
        temporary=self.path.with_name('kite-'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as handle:
                handle.write(value);handle.flush();os.fsync(handle.fileno())
            if os.name!='nt':temporary.chmod(0o600)
            os.replace(temporary,self.path)
        except OSError:
            raise VaultError('Could not save the protected Kite session.') from None
        finally:
            with suppress(OSError):temporary.unlink(missing_ok=True)

    def load(self):
        if not self.path.exists():return None
        if self.path.is_symlink():raise VaultError('Session file must not be a symbolic link.')
        try:
            data=self.path.read_bytes()
            if data==b'DCDISCONNECTED':return {'disconnected':True}
            if len(data)>65536 or not data.startswith(b'DCV1'):raise ValueError('Invalid session')
            record=json.loads(self._codec().decrypt(data[4:]))
            if not isinstance(record,dict) or record.get('identity')!=self.identity:raise ValueError('Invalid identity')
            return record
        except (OSError,ValueError,UnicodeError):
            raise VaultError('The saved Kite session is invalid or belongs to a different API key.') from None

    def disconnect(self):
        # A credential-free tombstone also prevents an old .env token restoring.
        self._write(b'DCDISCONNECTED')
