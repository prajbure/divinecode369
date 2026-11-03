"""Versioned client contract; financial values are produced by the existing backend."""
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class Meta(BaseModel):
    api_version: str = '1'
    cache_timestamp: str | None = None
    provider_timestamp: str | None = None
    stale: bool = False
    unavailable: bool = False
    source: str = 'Shared backend cache'
    message: str | None = None


class APIError(BaseModel):
    detail: str
    code: str


class Stock(BaseModel):
    symbol: str
    name: str
    sectors: list[str] = []
    sector_ids: list[str] = []
    prev_close: float | None = None
    open: float | None = None
    ltp: float | None = None
    difference: float | None = None
    difference_display: str | None = None
    change_pct: float | None = None
    match: bool = False
    near_match: bool = False
    match_type: str = 'unavailable'
    freshness: str = 'unavailable'
    provider_timestamp: str | None = None
    opening_date: str | None = None
    signal_state: str = 'unavailable'
    intelligence: dict[str, Any] = {}
    opportunity: dict[str, Any] = {}


class Sector(BaseModel):
    id: str
    name: str
    memberships: int
    unique_symbols: int
    available: int
    advancing: int
    declining: int
    unchanged: int
    average: float | None = None
    median: float | None = None
    breadth: float | None = None
    strength: float | None = None
    live: int = 0
    stale: int = 0
    stocks: list[Stock] = []


class StockPage(BaseModel):
    items: list[Stock]
    total: int
    page: int
    page_size: int
    meta: Meta


class SectorPage(BaseModel):
    items: list[Sector]
    memberships: int = 160
    unique_symbols: int = 148
    meta: Meta


class Timeline(BaseModel):
    open_date: str | None = None
    close_date: str | None = None
    allotment_date: str | None = None
    refund_date: str | None = None
    credit_to_demat_date: str | None = None
    listing_date: str | None = None


class Issue(BaseModel):
    price_min: float | None = None
    price_max: float | None = None
    price_band: str | None = None
    issue_price: float | None = None
    issue_size: float | None = None
    face_value: float | None = None
    lot_size: float | None = None
    min_investment: float | None = None
    sale_type: str | None = None
    listing_on: str | None = None
    nse_symbol: str | None = None


class Freshness(BaseModel):
    as_of: str | None = None
    status: str = 'unavailable'


class GMP(BaseModel):
    price: float | None = None
    percentage: float | None = None
    estimate: float | None = None
    estimate_basis: str | None = None
    freshness: Freshness = Field(default_factory=Freshness)


class Listing(BaseModel):
    price: float | None = None
    gain: float | None = None
    cmp: float | None = None
    current_gain: float | None = None
    freshness: Freshness = Field(default_factory=Freshness)


class IPO(BaseModel):
    slug: str
    name: str
    type: str = 'Unknown'
    status: str = 'Unknown'
    stage: str | None = None
    phase: str = 'closed'
    is_listed: bool = False
    logo: str | None = None
    timeline: Timeline = Field(default_factory=Timeline)
    issue: Issue = Field(default_factory=Issue)
    gmp: GMP = Field(default_factory=GMP)
    subscription_total: float | None = None
    listing: Listing = Field(default_factory=Listing)
    buckets: list[str] = []


class IPOPage(BaseModel):
    items: list[IPO]
    total: int
    page: int
    page_size: int
    counts: dict[str, int | None]
    meta: Meta


class IPODetail(BaseModel):
    ipo: IPO | None = None
    company: dict[str, Any] = {}
    registrar: dict[str, str | None] = {}
    documents: dict[str, str | None] = {}
    allotment_confirmed: bool = False
    research: dict[str, Any] | None = None
    locked: list[str] = []
    meta: Meta


class Resource(BaseModel):
    data: dict[str, Any] | None = None
    meta: Meta


class Health(BaseModel):
    kite_state: str
    ipo_state: str
    market_state: str
    live: int = 0
    stale: int = 0
    unavailable: int = 148
    provider_timestamp: str | None = None
    cache_timestamp: str | None = None
    notifications: str = 'Authenticated inbox; FCM not configured'
    ipo_cache_timestamp: str | None = None


class Overview(BaseModel):
    health: Health
    market_label: str
    summary: dict[str, Any]
    sectors: list[Sector]
    matches: list[Stock]
    ipo_highlights: list[IPO]
    regime: dict[str, Any]
    meta: Meta


class SavedItem(BaseModel):
    kind: Literal['ipo', 'stock']
    key: str = Field(min_length=1, max_length=150)
    label: str = Field(min_length=1, max_length=150)
    saved: bool = True
    updated_at: str | None = None


class Watchlist(BaseModel):
    items: list[SavedItem]
    updated_at: str


class AlertRule(BaseModel):
    id: str = Field(default='', max_length=64,pattern=r'^[A-Za-z0-9_-]*$')
    ipo_slug: str = Field(default='',pattern=r'^(?:[a-z0-9]+(?:-[a-z0-9]+)*)?$', max_length=150)
    event: Literal['opens', 'closes_tomorrow', 'gmp_threshold', 'gmp_change', 'subscription_threshold', 'allotment', 'listing','exact','near','price_above','price_below']
    threshold: float | None = Field(default=None, ge=0, le=1000000)
    enabled: bool = True
    deleted: bool = False
    kind: Literal['ipo','stock'] = 'ipo'
    symbol: str | None = Field(default=None,max_length=40)

    @model_validator(mode='after')
    def target_matches_event(self):
        stock_event=self.event in ('exact','near','price_above','price_below')
        if stock_event != (self.kind=='stock') or (self.kind=='ipo' and not self.ipo_slug) or (self.kind=='stock' and not self.symbol):
            raise ValueError('Choose a valid alert target and event.')
        return self


class AlertRules(BaseModel):
    items: list[AlertRule]
    delivery: str = 'inbox'


class AlertEvent(BaseModel):
    id: str
    rule_id: str
    ipo_slug: str = ''
    event: str
    title: str
    created_at: str
    source_timestamp: str | None = None
    kind: Literal['ipo','stock'] = 'ipo'
    symbol: str | None = None


class AlertInbox(BaseModel):
    items: list[AlertEvent]


class Preferences(BaseModel):
    theme: Literal['dark', 'light', 'system'] = 'dark'
    density: Literal['compact', 'comfortable', 'large'] = 'comfortable'
    notifications: bool = False


class History(BaseModel):
    symbol: str
    candles: list[dict[str, Any]]
    enabled: bool
    meta: Meta
