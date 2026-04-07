import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import type { Cart, CatalogItem } from '../types/commerce';
import { useAuth } from './AuthContext';

interface ShopContextValue {
  cart: Cart | null;
  managedServices: CatalogItem[];
  loadingCart: boolean;
  cartError: string;
  refreshCart: () => Promise<void>;
  refreshManagedServices: () => Promise<void>;
  addRouterToCart: (catalogItemId: string, quantity?: number) => Promise<void>;
  addServiceToCart: (catalogItemId: string, quantity?: number) => Promise<void>;
  attachManagedService: (serviceCatalogItemId: string, routerLineId: string) => Promise<void>;
  changeServiceTier: (serviceLineId: string, newServiceCatalogItemId: string) => Promise<void>;
  updateLineQuantity: (lineId: string, quantity: number) => Promise<void>;
  removeLine: (lineId: string) => Promise<void>;
}

const ShopContext = createContext<ShopContextValue | undefined>(undefined);

export const ShopProvider = ({ children }: { children: React.ReactNode }) => {
  const { accessToken } = useAuth();
  const [cart, setCart] = useState<Cart | null>(null);
  const [managedServices, setManagedServices] = useState<CatalogItem[]>([]);
  const [loadingCart, setLoadingCart] = useState(true);
  const [cartError, setCartError] = useState('');

  const refreshCart = useCallback(async () => {
    if (!accessToken) return;
    setLoadingCart(true);
    setCartError('');
    try {
      const data = await commerceApi.getCart(accessToken);
      setCart(data);
    } catch (err: any) {
      setCartError(err?.response?.data?.detail || 'Failed to load cart');
    } finally {
      setLoadingCart(false);
    }
  }, [accessToken]);

  const refreshManagedServices = useCallback(async () => {
    if (!accessToken) return;
    try {
      const data = await commerceApi.getCatalog(accessToken, {
        type: 'SERVICE',
        service_kind: 'managed_router',
        sort: 'price_low',
      });
      setManagedServices(data);
    } catch {
      setManagedServices([]);
    }
  }, [accessToken]);

  useEffect(() => {
    refreshCart();
    refreshManagedServices();
  }, [refreshCart, refreshManagedServices]);

  const addRouterToCart = useCallback(async (catalogItemId: string, quantity = 1) => {
    if (!accessToken) return;
    const data = await commerceApi.addCartLine(accessToken, { catalog_item_id: catalogItemId, quantity });
    setCart(data);
  }, [accessToken]);

  const addServiceToCart = useCallback(async (catalogItemId: string, quantity = 1) => {
    if (!accessToken) return;
    const data = await commerceApi.addCartLine(accessToken, { catalog_item_id: catalogItemId, quantity });
    setCart(data);
  }, [accessToken]);

  const attachManagedService = useCallback(async (serviceCatalogItemId: string, routerLineId: string) => {
    if (!accessToken) return;
    const data = await commerceApi.addCartLine(accessToken, {
      catalog_item_id: serviceCatalogItemId,
      quantity: 1,
      applies_to_line_id: routerLineId,
    });
    setCart(data);
  }, [accessToken]);

  const changeServiceTier = useCallback(async (serviceLineId: string, newServiceCatalogItemId: string) => {
    if (!accessToken) return;
    const data = await commerceApi.updateCartLine(accessToken, serviceLineId, { catalog_item_id: newServiceCatalogItemId });
    setCart(data);
  }, [accessToken]);

  const updateLineQuantity = useCallback(async (lineId: string, quantity: number) => {
    if (!accessToken) return;
    const data = await commerceApi.updateCartLine(accessToken, lineId, { quantity });
    setCart(data);
  }, [accessToken]);

  const removeLine = useCallback(async (lineId: string) => {
    if (!accessToken) return;
    const data = await commerceApi.removeCartLine(accessToken, lineId);
    setCart(data);
  }, [accessToken]);

  const value = useMemo(
    () => ({
      cart,
      managedServices,
      loadingCart,
      cartError,
      refreshCart,
      refreshManagedServices,
      addRouterToCart,
      addServiceToCart,
      attachManagedService,
      changeServiceTier,
      updateLineQuantity,
      removeLine,
    }),
    [
      cart,
      managedServices,
      loadingCart,
      cartError,
      refreshCart,
      refreshManagedServices,
      addRouterToCart,
      addServiceToCart,
      attachManagedService,
      changeServiceTier,
      updateLineQuantity,
      removeLine,
    ],
  );

  return <ShopContext.Provider value={value}>{children}</ShopContext.Provider>;
};

export const useShop = () => {
  const ctx = useContext(ShopContext);
  if (!ctx) throw new Error('useShop must be used inside ShopProvider');
  return ctx;
};
