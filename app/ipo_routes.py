"""Dedicated IPO routes; no dependency on scanner, Kite or AI state."""
import re
from fastapi import APIRouter, HTTPException, Request
from .ipo_service import IPOService
from .ipoguru import IPOGuruClient


def create_ipo_router(require_admin, home_response, client=None):
    router=APIRouter()
    service=IPOService(client or IPOGuruClient())

    def slug_checked(slug):
        if len(slug)>150 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug):
            raise HTTPException(422,'Invalid IPO slug.')
        return slug

    @router.get('/ipo')
    @router.get('/ipo/{screen}')
    @router.get('/ipo/details/{slug}')
    def page(screen=None,slug=None):
        return home_response()

    @router.get('/api/ipo/status')
    def status():
        return service.client.status()

    @router.post('/api/ipo/verify')
    def verify(request:Request):
        require_admin(request)
        result=service.client.get('/me','account',verify=True)
        return {'provider':service.client.status(),'meta':result['meta']}

    @router.get('/api/ipo/overview')
    def overview():
        return service.overview()

    @router.get('/api/ipo/details/{slug}')
    def detail(slug:str):
        return service.detail(slug_checked(slug))

    @router.get('/api/ipo/details/{slug}/{kind}')
    def resource(slug:str,kind:str):
        if kind not in ('history','subscription','anchors'):
            raise HTTPException(404,'Unavailable in the Standard integration.')
        return service.resource(slug_checked(slug),kind)

    return router
