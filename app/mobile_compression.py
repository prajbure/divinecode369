"""Compress JSON snapshots; keep authentication and the existing SSE path untouched."""
from starlette.middleware.gzip import GZipMiddleware

class SnapshotCompression(GZipMiddleware):
    async def __call__(self,scope,receive,send):
        path=scope.get('path','')
        if scope['type']=='http' and scope.get('method')=='GET' and (path.startswith('/api/v1/mobile/') or path in ('/api/quotes','/api/status')):
            await super().__call__(scope,receive,send)
        else:
            await self.app(scope,receive,send)
