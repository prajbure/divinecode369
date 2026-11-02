"""Redact credentials even in third-party reconnect diagnostics."""
from collections import deque
import logging
import re
import threading
from . import config

_secrets=deque(maxlen=64)
_lock=threading.Lock()


def remember_secret(value):
    if isinstance(value,str) and value:
        with _lock:
            if value not in _secrets:_secrets.append(value)


class CredentialFilter(logging.Filter):
    def filter(self,record):
        with _lock:secrets=list(_secrets)
        secrets.extend([config.KITE_API_KEY,config.KITE_API_SECRET,config.KITE_ACCESS_TOKEN,config.IPOGURU_API_KEY])
        secrets=sorted(set(s for s in secrets if s),key=len,reverse=True)
        def scrub(value):
            if not isinstance(value,str):return value
            for secret in secrets:value=value.replace(secret,'[redacted]')
            return re.sub(r'(?i)((?:api_key|api_secret|access_token|request_token)=)[^&\s]+',r'\1[redacted]',value)
        # Preserve Uvicorn's five positional access-log fields for its formatter.
        record.msg=scrub(record.msg)
        if isinstance(record.args,tuple):record.args=tuple(scrub(v) for v in record.args)
        elif isinstance(record.args,dict):record.args={k:scrub(v) for k,v in record.args.items()}
        return True


def install():
    for name in ('kiteconnect.ticker','urllib3.connectionpool','requests','uvicorn.access','uvicorn.error','divine.connections'):
        logger=logging.getLogger(name)
        if not any(isinstance(f,CredentialFilter) for f in logger.filters):logger.addFilter(CredentialFilter())
