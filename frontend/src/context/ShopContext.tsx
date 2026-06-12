import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import type { Cart, CatalogItem } from '../types/commerce';
import { useAuth } from './AuthContext';
import { extractApiError } from '../utils/extractApiError';
import { toast } from '../utils/toast';

export interface AddProductOptions {
  selections?: Record<string, number>;
  quantity?: number;
  financialModel?: 'CAPEX' | 'OPEX';
  interval?: 'MONTH' | 'YEAR';
}

interface ShopContextValue {
  cart: Cart | null;
  managedServices: CatalogItem[];
  loadingCart: boolean;
  cartError: string;
  refreshCart: () => Promise<void>;
  refreshManagedServices: () => Promise<void>;
  /** Add a configured product (Phase 7: the configurator's confirmed selection). */
  addProductToCart: (productId: string, options?: AddProductOptions) => Promise<void>;
  /** Back-compat alias used by catalog pages — adds the product with default components. */
  addRouterToCart: (productId: string, quantity?: number) => Promise<void>;
  /** Add one standalone component à-la-carte (extra line / SIM / managed service). */
  addComponentToCart: (componentId: string, quantity?: number, appliesToLineId?: string) => Promise<void>;
  attachManagedService: (serviceProductId: string, routerLineId: string) => Promise<void>;
  changeServiceTier: (serviceLineId: string, newServiceProductId: string) => Promise<void>;
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
      setCartError(extractApiError(err, 'Failed to load cart'));
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

  const addProductToCart = useCallback(async (productId: string, options?: AddProductOptions) => {
    if (!accessToken) return;
    const data = await commerceApi.addCartLine(accessToken, {
      product_id: productId,
      selections: options?.selections ?? {},
      quantity: options?.quantity ?? 1,
      financial_model: options?.financialModel ?? 'CAPEX',
      interval: options?.interval ?? 'MONTH',
    });
    setCart(data);
    toast.success('Added to cart');
  }, [accessToken]);

  const addRouterToCart = useCallback(async (productId: string, quantity = 1) => {
    await addProductToCart(productId, { quantity });
  }, [addProductToCart]);

  const addComponentToCart = useCallback(async (componentId: string, quantity = 1, appliesToLineId?: string) => {
    if (!accessToken) return;
    const data = await commerceApi.addCartLine(accessToken, {
      component_id: componentId,
      quantity,
      applies_to_line_id: appliesToLineId,
    });
    setCart(data);
    toast.success('Added to cart');
  }, [accessToken]);

  /** A managed-service tier is a product whose primary component carries the
   * monthly charge — attach that component under the router line. */
  const primaryComponentId = useCallback(async (serviceProductId: string) => {
    if (!accessToken) return null;
    const detail = await commerceApi.getCatalogItem(accessToken, serviceProductId);
    const components = detail.components ?? [];
    const primary = components.find((c) => c.is_required) ?? components[0];
    return primary?.id ?? null;
  }, [accessToken]);

  const attachManagedService = useCallback(async (serviceProductId: string, routerLineId: string) => {
    if (!accessToken) return;
    const componentId = await primaryComponentId(serviceProductId);
    if (!componentId) {
      toast.error('Selected service has no purchasable component');
      return;
    }
    const data = await commerceApi.addCartLine(accessToken, {
      component_id: componentId,
      quantity: 1,
      applies_to_line_id: routerLineId,
    });
    setCart(data);
    toast.success('Managed service attached');
  }, [accessToken, primaryComponentId]);

  const changeServiceTier = useCallback(async (serviceLineId: string, newServiceProductId: string) => {
    if (!accessToken || !cart) return;
    const line = cart.lines.find((l) => l.id === serviceLineId);
    const componentId = await primaryComponentId(newServiceProductId);
    if (!componentId) {
      toast.error('Selected service has no purchasable component');
      return;
    }
    await commerceApi.removeCartLine(accessToken, serviceLineId);
    const data = await commerceApi.addCartLine(accessToken, {
      component_id: componentId,
      quantity: 1,
      applies_to_line_id: line?.applies_to_line_id ?? undefined,
    });
    setCart(data);
    toast.success('Service tier updated');
  }, [accessToken, cart, primaryComponentId]);

  const updateLineQuantity = useCallback(async (lineId: string, quantity: number) => {
    if (!accessToken) return;
    const data = await commerceApi.updateCartLine(accessToken, lineId, { quantity });
    setCart(data);
    toast.success(quantity <= 0 ? 'Removed from cart' : 'Cart updated');
  }, [accessToken]);

  const removeLine = useCallback(async (lineId: string) => {
    if (!accessToken) return;
    const data = await commerceApi.removeCartLine(accessToken, lineId);
    setCart(data);
    toast.success('Removed from cart');
  }, [accessToken]);

  const value = useMemo(
    () => ({
      cart,
      managedServices,
      loadingCart,
      cartError,
      refreshCart,
      refreshManagedServices,
      addProductToCart,
      addRouterToCart,
      addComponentToCart,
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
      addProductToCart,
      addRouterToCart,
      addComponentToCart,
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
