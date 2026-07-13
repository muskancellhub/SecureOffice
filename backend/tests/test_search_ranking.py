"""Unit tests for the deterministic global-search logic (Slices 2-5).

Covers the pure functions — prefix tsquery building, action/command detection,
and Reciprocal Rank Fusion — without touching the DB, OpenAI, or pgvector.
"""
from app.routes.search import _build_tsquery, _detect_actions, _rrf


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
