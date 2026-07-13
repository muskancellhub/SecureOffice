"""Unit tests for the deterministic global-search logic (Slices 2-6).

Covers the pure functions — prefix tsquery building, action/command detection,
Reciprocal Rank Fusion, the tenant/ownership scoping spine, entity-hit mapping,
and cross-entity fusion — without touching the DB, OpenAI, or pgvector.
"""
from types import SimpleNamespace

from app.routes.search import (
    PROVIDERS,
    SearchHit,
    _build_tsquery,
    _detect_actions,
    _merge_cross_entity,
    _rrf,
    _scope_sql,
)


class _FakeDB:
    def __init__(self, tenant_id):
        self.info = {'tenant_id': tenant_id}


_ORDER = next(p for p in PROVIDERS if p.type == 'order')


class TestBuildTsquery:
    def test_appends_prefix_star_and_ands_terms(self):
        assert _build_tsquery('cisco wif') == 'cisco:* & wif:*'

    def test_or_operator_for_expansion(self):
        assert _build_tsquery('firewall router', op='|') == 'firewall:* | router:*'

    def test_strips_punctuation_and_injection(self):
        # No stray SQL/tsquery operators survive — only alnum terms remain.
        assert _build_tsquery("a'; DROP TABLE products; --") == \
            'a:* & DROP:* & TABLE:* & products:*'

    def test_empty_query_is_empty(self):
        assert _build_tsquery('   !!! ') == ''


class TestDetectActions:
    def test_make_a_new_network_design(self):
        hits = _detect_actions('make a new network design')
        assert len(hits) == 1
        assert hits[0].type == 'action'
        assert hits[0].id == 'action:create-design'

    def test_create_design_with_context(self):
        hits = _detect_actions('create design for a dentist office')
        assert [h.id for h in hits] == ['action:create-design']

    def test_new_network_phrase(self):
        assert _detect_actions('new network for my office')[0].id == 'action:create-design'

    def test_plain_product_search_yields_no_action(self):
        assert _detect_actions('cisco router') == []

    def test_design_word_without_create_verb_is_not_an_action(self):
        # A bare noun search shouldn't hijack into a command.
        assert _detect_actions('design') == []


class TestRRF:
    def test_item_in_multiple_lanes_outranks_single_lane_item(self):
        # 'a' appears in both lanes; 'b' only in one -> 'a' scores higher.
        scores = _rrf([['a', 'b'], ['a', 'c']])
        assert scores['a'] > scores['b']
        assert scores['a'] > scores['c']

    def test_higher_rank_scores_higher_within_a_lane(self):
        scores = _rrf([['first', 'second', 'third']])
        assert scores['first'] > scores['second'] > scores['third']

    def test_empty_lanes(self):
        assert _rrf([[], []]) == {}

    def test_reciprocal_rank_values(self):
        # Single lane, k=60: rank1 -> 1/61, rank2 -> 1/62.
        scores = _rrf([['x', 'y']], k=60)
        assert abs(scores['x'] - 1 / 61) < 1e-9
        assert abs(scores['y'] - 1 / 62) < 1e-9


class TestScopeSql:
    """The security spine — must always tenant-scope, and owner-scope non-admins."""

    def test_non_admin_gets_tenant_and_owner_predicates(self):
        db = _FakeDB('tenant-1')
        user = {'role': 'USER', 'user_id': 'user-9'}
        sql, params = _scope_sql(db, 'e', _ORDER, user)
        assert 'e.tenant_id = :s_tenant' in sql
        assert 'e.created_by = :s_uid' in sql
        assert params == {'s_tenant': 'tenant-1', 's_uid': 'user-9'}

    def test_admin_is_tenant_scoped_but_not_owner_scoped(self):
        db = _FakeDB('tenant-1')
        user = {'role': 'ADMIN', 'user_id': 'admin-1'}
        sql, params = _scope_sql(db, 'e', _ORDER, user)
        assert 'e.tenant_id = :s_tenant' in sql
        assert 'created_by' not in sql          # admin sees the whole tenant
        assert params == {'s_tenant': 'tenant-1'}

    def test_super_admin_uses_effective_tenant_from_db_info(self):
        # get_db stashes the (possibly X-Tenant-Id-targeted) tenant; scope follows it.
        db = _FakeDB('other-tenant')
        user = {'role': 'SUPER_ADMIN', 'user_id': 'sa-1'}
        sql, params = _scope_sql(db, 'e', _ORDER, user)
        assert params['s_tenant'] == 'other-tenant'
        assert 'created_by' not in sql

    def test_no_effective_tenant_and_admin_is_unfiltered(self):
        db = _FakeDB(None)
        user = {'role': 'SUPER_ADMIN', 'user_id': 'sa-1'}
        sql, params = _scope_sql(db, 'e', _ORDER, user)
        assert sql == 'true'
        assert params == {}

    def test_non_admin_still_owner_scoped_without_tenant(self):
        db = _FakeDB(None)
        user = {'role': 'USER', 'user_id': 'user-9'}
        sql, params = _scope_sql(db, 'e', _ORDER, user)
        assert sql == 'e.created_by = :s_uid'
        assert params == {'s_uid': 'user-9'}


class TestEntityHit:
    def test_order_hit_shape_and_deeplink(self):
        row = SimpleNamespace(id='abc-123', public_id='OID0007', status='SHIPPED')
        hit = _ORDER.to_hit(row)
        assert hit.type == 'order'
        assert hit.title == 'Order OID0007'
        assert hit.subtitle == 'Shipped'            # humanized status
        assert hit.url == '/shop/orders/abc-123'

    def test_status_underscores_humanized(self):
        row = SimpleNamespace(id='q1', public_id='QID0002', status='PENDING_REVIEW')
        hit = next(p for p in PROVIDERS if p.type == 'quote').to_hit(row)
        assert hit.subtitle == 'Pending Review'
        assert hit.url == '/shop/quotes/q1'


class TestMergeCrossEntity:
    def _hit(self, t, i):
        return SearchHit(id=i, type=t, title=f'{t}-{i}')

    def test_dedups_by_type_and_id(self):
        a = [self._hit('product', '1'), self._hit('product', '2')]
        b = [self._hit('product', '1')]  # same (type,id) as a[0]
        merged = _merge_cross_entity([a, b], limit=10)
        keys = [(h.type, h.id) for h in merged]
        assert keys.count(('product', '1')) == 1

    def test_cross_type_interleaves_by_rank(self):
        products = [self._hit('product', 'p1'), self._hit('product', 'p2')]
        orders = [self._hit('order', 'o1')]
        merged = _merge_cross_entity([products, orders], limit=10)
        # rank-1 of each list ties; both out-rank product rank-2.
        top2 = {(h.type, h.id) for h in merged[:2]}
        assert top2 == {('product', 'p1'), ('order', 'o1')}
        assert merged[2].id == 'p2'

    def test_respects_limit(self):
        big = [self._hit('product', str(i)) for i in range(20)]
        assert len(_merge_cross_entity([big], limit=5)) == 5
