"""Capacity / constraint validation (Secure Office, Phase 5).

Resource-agnostic provide/consume model (spec §5): a device declares the
resources it offers (``product.attributes.capacity``); a component declares what
it consumes (``component.attributes.consumes``). Missing key = 0, so "this device
doesn't have that resource" is enforced too. One function covers every device and
every resource dimension without schema changes.

Overflow behavior is **block + warn** (our design — manager didn't specify; §3a #12).
The MIX 100-line minimum is an ACCOUNT-level aggregate, NOT a per-assembly rule,
and is intentionally out of scope here.
"""
from __future__ import annotations

from collections import defaultdict


def check_capacity(provided: dict | None, consumers: list[tuple[dict | None, int]]) -> list[dict]:
    """Return capacity violations (empty = OK).

    provided:  the device's capacity map, e.g. {"fxs_port": 8, "max_sims": 2}.
    consumers: list of (consumes_map, qty) for each child line.
    A resource the device doesn't declare counts as provided 0.
    """
    provided = provided or {}
    used: dict[str, int] = defaultdict(int)
    for consumes, qty in consumers:
        for resource, amount in (consumes or {}).items():
            used[resource] += amount * qty
    return [
        {'resource': resource, 'used': used[resource], 'provided': int(provided.get(resource, 0) or 0)}
        for resource in used
        if used[resource] > (provided.get(resource, 0) or 0)
    ]


def evaluate_constraints(constraints: list[dict] | None, used: dict, provided: dict | None) -> list[dict]:
    """Evaluate explicit (resource_key, type, value) constraints beyond MAX.

    Types: MAX (Σ used ≤ value), MIN (Σ used ≥ value), COMPAT (value truthy).
    Capacity MAX is already handled by check_capacity; this covers per-assembly
    MIN floors (e.g. "≥1 line per device") and boolean COMPAT fitment.
    """
    provided = provided or {}
    violations: list[dict] = []
    for c in constraints or []:
        rk = c.get('resource_key')
        typ = (c.get('type') or '').upper()
        val = c.get('value')
        amount = used.get(rk, 0)
        if typ == 'MAX' and val is not None and amount > val:
            violations.append({'resource': rk, 'type': 'MAX', 'used': amount, 'limit': val})
        elif typ == 'MIN' and val is not None and amount < val:
            violations.append({'resource': rk, 'type': 'MIN', 'used': amount, 'limit': val})
        elif typ == 'COMPAT' and not val:
            violations.append({'resource': rk, 'type': 'COMPAT', 'used': amount, 'limit': val})
    return violations


def format_violations(violations: list[dict]) -> str:
    parts = []
    for v in violations:
        if 'provided' in v:
            parts.append(f"{v['resource']}: needs {v['used']}, device provides {v['provided']}")
        else:
            parts.append(f"{v['resource']} {v.get('type')}: {v['used']} vs limit {v['limit']}")
    return '; '.join(parts)
