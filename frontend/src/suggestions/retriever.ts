import type { CatalogItem, IndoorOutdoor, ProductQuery, ProductRetriever } from './types';

const SEARCH_FIELDS: Array<keyof Pick<CatalogItem, 'model' | 'family' | 'notes'>> = ['model', 'family', 'notes'];

const normalizeText = (value: string | undefined): string => (value || '').trim().toLowerCase();

const priceForSort = (item: CatalogItem): number => {
  if (typeof item.price === 'number' && Number.isFinite(item.price) && item.price >= 0) {
    return item.price;
  }
  return Number.POSITIVE_INFINITY;
};

const indoorOutdoorMatches = (
  requested: IndoorOutdoor | undefined,
  candidate: CatalogItem['indoorOutdoor'],
): boolean => {
  if (!requested || requested === 'both') return true;
  if (!candidate || candidate === 'both') return true;
  return requested === candidate;
};

const textScore = (queryText: string | undefined, item: CatalogItem): number => {
  const q = normalizeText(queryText);
  if (!q) return 0;

  let score = 0;
  for (const field of SEARCH_FIELDS) {
    const text = normalizeText(item[field]);
    if (!text) continue;
    if (text === q) score += 18;
    else if (text.includes(q)) score += 8;
  }
  return score;
};

const scoreRetrievalCandidate = (item: CatalogItem, query: ProductQuery): number => {
  let score = 0;

  if (query.categories && query.categories.length > 0 && query.categories.includes(item.category)) score += 8;
  if (query.vendors && query.vendors.length > 0 && query.vendors.includes(item.vendor)) score += 10;
  if (query.wifiStandard && item.wifiStandard === query.wifiStandard) score += 10;
  if (query.smbOnly && item.smbFit) score += 8;
  if (item.pricingBasis === 'public' || item.pricingBasis === 'street') score += 6;
  if (indoorOutdoorMatches(query.indoorOutdoor, item.indoorOutdoor)) score += 4;

  score += textScore(query.query, item);

  const price = priceForSort(item);
  if (Number.isFinite(price)) {
    score += Math.max(0, 6 - price / 400);
  }

  return score;
};

export class LocalInMemoryProductRetriever implements ProductRetriever {
  constructor(private readonly catalog: CatalogItem[]) {}

  retrieveProducts(input: ProductQuery): CatalogItem[] {
    const categories = input.categories && input.categories.length > 0 ? new Set(input.categories) : null;
    const vendors = input.vendors && input.vendors.length > 0 ? new Set(input.vendors) : null;
    const queryText = normalizeText(input.query);

    const filtered = this.catalog.filter((item) => {
      if (categories && !categories.has(item.category)) return false;
      if (vendors && !vendors.has(item.vendor)) return false;
      if (input.wifiStandard && item.wifiStandard && item.wifiStandard !== input.wifiStandard) return false;
      if (!indoorOutdoorMatches(input.indoorOutdoor, item.indoorOutdoor)) return false;
      if (input.smbOnly && !item.smbFit) return false;

      if (queryText) {
        const anyTextMatch = SEARCH_FIELDS.some((field) => normalizeText(item[field]).includes(queryText));
        if (!anyTextMatch) return false;
      }

      return true;
    });

    const ranked = [...filtered].sort((a, b) => {
      const byScore = scoreRetrievalCandidate(b, input) - scoreRetrievalCandidate(a, input);
      if (byScore !== 0) return byScore;

      const byPrice = priceForSort(a) - priceForSort(b);
      if (byPrice !== 0) return byPrice;

      return `${a.vendor}-${a.model}`.localeCompare(`${b.vendor}-${b.model}`);
    });

    if (typeof input.limit === 'number' && input.limit > 0) {
      return ranked.slice(0, input.limit);
    }
    return ranked;
  }
}

export const retrieveCatalogItems = (retriever: ProductRetriever, input: ProductQuery): CatalogItem[] => {
  return retriever.retrieveProducts(input);
};

