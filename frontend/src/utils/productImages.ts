import router1 from '../assets/products/router-1.svg';
import router2 from '../assets/products/router-2.svg';
import router3 from '../assets/products/router-3.svg';
import router4 from '../assets/products/router-4.svg';
import router5 from '../assets/products/router-5.svg';
import router6 from '../assets/products/router-6.svg';

const SAMPLE_ROUTER_IMAGES = [router1, router2, router3, router4, router5, router6];

const toHash = (value: string) => {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
};

export const pickRouterSampleImage = (seed: string) => {
  const index = toHash(seed) % SAMPLE_ROUTER_IMAGES.length;
  return SAMPLE_ROUTER_IMAGES[index];
};

export const getRouterImage = (params: {
  id?: string | null;
  sku?: string | null;
  name?: string | null;
  brand?: string | null;
  model?: string | null;
  imageUrl?: string | null;
}) => {
  if (params.imageUrl && params.imageUrl.trim()) return params.imageUrl;

  const seed = [params.id, params.sku, params.name, params.brand, params.model]
    .filter(Boolean)
    .join('|')
    .toLowerCase();

  return pickRouterSampleImage(seed || 'secure-office-router');
};
