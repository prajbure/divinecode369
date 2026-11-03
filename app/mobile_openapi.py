"""Document the cookie/bearer alternatives without changing enforcement."""
from fastapi.openapi.utils import get_openapi

def install(app):
    def schema():
        if app.openapi_schema:return app.openapi_schema
        result=get_openapi(title=app.title,version=app.version,routes=app.routes)
        security=result.setdefault('components',{}).setdefault('securitySchemes',{})
        security['MobileBearer']={'type':'http','scheme':'bearer','bearerFormat':'Opaque scoped device access credential','description':'Owner-approved PKCE device flow. 15-minute access, rotating refresh, revocable family. No provider administration.'}
        security['AdminCookie']={'type':'apiKey','in':'cookie','name':'__Host-divine_admin','description':'HTTPS owner browser session. Unsafe requests also require exact Origin and X-CSRF-Token.'}
        for path,operations in result['paths'].items():
            scoped=path.startswith('/api/v1/mobile/') and path.split('/api/v1/mobile/')[1].split('/')[0] in {'watchlist','alerts','preferences','history','predictions'}
            owner=path.startswith(('/auth/mobile/requests/','/auth/mobile/sessions'))
            device=path in {'/auth/mobile/logout','/auth/mobile/session'}
            for method,operation in operations.items():
                if method not in {'get','put','post','delete','patch','head','options'}:continue
                if scoped:operation['security']=[{'MobileBearer':[]},{'AdminCookie':[]}]
                elif owner:operation['security']=[{'AdminCookie':[]}]
                elif device:operation['security']=[{'MobileBearer':[]}]
                if (scoped or owner) and method not in {'get','head','options'}:
                    operation.setdefault('parameters',[]).append({'in':'header','name':'X-CSRF-Token','required':False,'schema':{'type':'string'},'description':'Required with an administrator cookie; mobile bearer credentials use their separate scoped authorization.'})
        app.openapi_schema=result
        return result
    app.openapi=schema
