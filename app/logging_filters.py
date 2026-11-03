"""Redact credentials even in third-party reconnect diagnostics."""
from collections import deque
import logging
import re
import threading
import traceback
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
        secrets.extend([config.KITE_API_KEY,config.KITE_API_SECRET,config.KITE_ACCESS_TOKEN,config.IPOGURU_API_KEY,config.ADMIN_TOKEN,config.ADMIN_PASSWORD_HASH])
        secrets=sorted(set(s for s in secrets if s),key=len,reverse=True)
        def scrub(value):
            if isinstance(value,dict):return {scrub(k):scrub(v) for k,v in value.items()}
            if isinstance(value,tuple):return tuple(scrub(v) for v in value)
            if isinstance(value,list):return [scrub(v) for v in value]
            if isinstance(value,bytes):return scrub(value.decode('utf-8',errors='replace')).encode()
            if not isinstance(value,str):return value
            for secret in secrets:value=value.replace(secret,'[redacted]')
            value = re.sub(r'(?i)((?:api_key|api_secret|access_token|request_token|admin_token|password|csrf_token)=)[^&\s]+',r'\1[redacted]',value)
            return re.sub(r'(?i)((?:authorization|cookie|set-cookie)\s*[:=]\s*)[^\r\n]+',r'\1[redacted]',value)
        # Preserve Uvicorn's five positional access-log fields for its formatter.
        record.msg=scrub(record.msg)
        record.args=scrub(record.args)
        if record.exc_info:record.exc_text=scrub(''.join(traceback.format_exception(*record.exc_info)))
        if record.stack_info:record.stack_info=scrub(record.stack_info)
        return True


def install():
    for name in ('kiteconnect.ticker','urllib3.connectionpool','requests','httpx','httpcore','uvicorn.access','uvicorn.error','divine.connections'):
        logger=logging.getLogger(name)
        if not any(isinstance(f,CredentialFilter) for f in logger.filters):logger.addFilter(CredentialFilter())
