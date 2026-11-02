"""Explain exact matches, verified same-issuer aliases and unavailable members."""
from collections import defaultdict

from . import provider
from .scanner import reference_groups
from .storage import now_iso


def reconciliation_report(store):
    memberships = defaultdict(list)
    for group in reference_groups():
        for index, entry in enumerate(group["stocks"]):
            memberships["NSE:" + entry[0]].append({"sector_id": group["id"], "sector": group["name"], "entry": index + 1, "display_name": entry[1], "configured_status": entry[3] if len(entry) > 3 else None})
    with store.connection() as db:
        rows = {r["symbol"]: dict(r) for r in db.execute("SELECT i.*, r.provider_symbol, r.kind, r.note, r.source, r.tick_size, r.checked_at FROM instruments i LEFT JOIN instrument_resolutions r USING(symbol)")}
    registry = provider.alias_registry()
    instruments = []
    for symbol, entries in sorted(memberships.items()):
        record = rows.get(symbol, {})
        known = registry["unavailable"].get(symbol, {})
        alias = registry["aliases"].get(symbol)
        suspended = any(e["configured_status"] == "suspended" for e in entries)
        verified = bool(record.get("status") == "valid" and record.get("instrument_token")) and not suspended
        state = "verified" if verified else "suspended" if suspended else "unavailable" if record.get("status") == "unavailable" else "unverified"
        instruments.append({"requested_symbol": symbol, "state": state,
                            "provider_symbol": record.get("provider_symbol") if verified else None,
                            "candidate_provider_symbol": "NSE:" + alias["provider_symbol"] if alias else None,
                            "resolution_kind": record.get("kind") if verified else known.get("kind", "unresolved_alias" if alias else "unverified"),
                            "explanation": record.get("note") or known.get("reason") or (alias["reason"] if alias else "Exact configured symbol" if verified else "Awaiting a successful Kite instrument-master audit"),
                            "source": record.get("source") or known.get("source") or (alias["source"] if alias else "kite:/instruments"),
                            "checked_at": record.get("checked_at"), "tick_size": record.get("tick_size"),
                            "token_verified": verified, "memberships": entries})
    duplicates = [{"symbol": s, "memberships": entries, "extra_entries": len(entries) - 1} for s, entries in memberships.items() if len(entries) > 1]
    verified = [r for r in instruments if r["state"] == "verified"]
    return {"generated_at": now_iso(), "source": "Approved unchanged sector configuration + last verified Kite instrument master + cited issuer/exchange notices",
            "total_configured_entries": sum(len(v) for v in memberships.values()),
            "unique_requested_instruments": len(memberships), "scan_candidates": sum(not any(e["configured_status"] == "suspended" for e in entries) for entries in memberships.values()),
            "verified_kite_instruments": len(verified), "verified_exact": sum(r["resolution_kind"] == "exact" for r in verified),
            "verified_aliases": sum(r["resolution_kind"] != "exact" for r in verified),
            "duplicate_membership_count": sum(d["extra_entries"] for d in duplicates), "duplicate_memberships": duplicates,
            "unavailable_instruments": [r for r in instruments if r["state"] in {"unavailable", "suspended"}],
            "unresolved_aliases": [r for r in instruments if r["state"] != "verified" and r["candidate_provider_symbol"]],
            "renamed_or_withdrawn": [r for r in instruments if r["resolution_kind"] in {"renamed", "not_listed_on_nse", "suspended"}],
            "instruments": instruments,
            "note": "Approved membership keys stay unchanged. Verified same-company quote aliases are displayed explicitly. No BSE substitute, new company or invented quote is introduced."}
