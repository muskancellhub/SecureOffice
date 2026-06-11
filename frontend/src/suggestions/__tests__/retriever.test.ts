import { describe, expect, test } from 'vitest';

import { LocalInMemoryProductRetriever, retrieveCatalogItems } from '../retriever';
import type { CatalogItem } from '../types';
import { catalogFixture } from './fixtures';

const retriever = new LocalInMemoryProductRetriever(catalogFixture);
const models = (items: CatalogItem[]) => items.map((i) => i.model);

describe('filtering', () => {
  test('category filter', () => {
    const items = retriever.retrieveProducts({ categories: ['switch'] });
    expect(new Set(items.map((i) => i.category))).toEqual(new Set(['switch']));
  });

  test('vendor filter', () => {
    const items = retriever.retrieveProducts({ vendors: ['InHand'] });
    expect(items.every((i) => i.vendor === 'InHand')).toBe(true);
    expect(items.length).toBeGreaterThan(0);
  });

  test('wifiStandard filter rejects mismatches but passes items without the field', () => {
    const items = retriever.retrieveProducts({ wifiStandard: 'wifi6' });
    expect(models(items)).not.toContain('AP305C'); // wifi6e
    expect(models(items)).toContain('MS120-24P'); // no wifiStandard field -> passes
  });

  test('indoor/outdoor matrix', () => {
    const indoor = retriever.retrieveProducts({ categories: ['wifi_ap'], indoorOutdoor: 'indoor' });
    expect(models(indoor)).toContain('AP305C'); // 'both' passes either side
    const outdoor = retriever.retrieveProducts({ categories: ['wifi_ap'], indoorOutdoor: 'outdoor' });
    expect(models(outdoor)).not.toContain('MR44'); // indoor-only rejected
    expect(models(outdoor)).toContain('AP305C');
    const both = retriever.retrieveProducts({ categories: ['wifi_ap'], indoorOutdoor: 'both' });
    expect(both.length).toBe(3);
  });

  test('smbOnly excludes items without smbFit', () => {
    const items = retriever.retrieveProducts({ smbOnly: true });
    expect(models(items)).not.toContain('LIC-ENT');
  });

  test('text query matches model/family/notes and excludes non-matches', () => {
    const items = retriever.retrieveProducts({ query: 'MR44' });
    expect(models(items)).toEqual(['MR44']);
    expect(retriever.retrieveProducts({ query: 'zzz-no-match' })).toEqual([]);
  });
});

describe('ranking and limits', () => {
  test('exact text match outranks substring match', () => {
    const catalog: CatalogItem[] = [
      { vendor: 'A', model: 'ap9', category: 'wifi_ap', price: 100, pricingBasis: 'public' },
      { vendor: 'B', model: 'ap900-plus', category: 'wifi_ap', price: 100, pricingBasis: 'public' },
    ];
    const r = new LocalInMemoryProductRetriever(catalog);
    expect(models(r.retrieveProducts({ query: 'ap9' }))[0]).toBe('ap9');
  });

  test('price breaks score ties; vendor-model lexicographic as final tiebreak', () => {
    const catalog: CatalogItem[] = [
      { vendor: 'Zeta', model: 'X1', category: 'switch', price: 200, pricingBasis: 'public' },
      { vendor: 'Alpha', model: 'X1', category: 'switch', price: 200, pricingBasis: 'public' },
      { vendor: 'Mid', model: 'X2', category: 'switch', price: 100, pricingBasis: 'public' },
    ];
    const r = new LocalInMemoryProductRetriever(catalog);
    const ranked = r.retrieveProducts({ categories: ['switch'] });
    expect(ranked[0].model).toBe('X2'); // cheapest scores higher + price tiebreak
    expect(ranked[1].vendor).toBe('Alpha'); // lexicographic before Zeta
  });

  test('non-finite price ranks last', () => {
    const catalog: CatalogItem[] = [
      { vendor: 'A', model: 'PRICED', category: 'switch', price: 100, pricingBasis: 'public' },
      { vendor: 'B', model: 'FREEFORM', category: 'switch', price: Number.NaN, pricingBasis: 'public' },
    ];
    const r = new LocalInMemoryProductRetriever(catalog);
    expect(models(r.retrieveProducts({ categories: ['switch'] }))).toEqual(['PRICED', 'FREEFORM']);
  });

  test('limit slices; limit 0 returns all', () => {
    expect(retriever.retrieveProducts({ categories: ['wifi_ap'], limit: 2 })).toHaveLength(2);
    expect(retriever.retrieveProducts({ categories: ['wifi_ap'], limit: 0 })).toHaveLength(3);
  });

  test('retrieveCatalogItems delegates to the retriever', () => {
    const items = retrieveCatalogItems(retriever, { categories: ['firewall'] });
    expect(models(items)).toEqual(['MX75']);
  });
});
