from app.models.user import UserRole

PERM_VIEW_CATALOG = 'view_catalog'
PERM_MANAGE_CART = 'manage_cart'
PERM_GENERATE_QUOTES = 'generate_quotes'
PERM_VIEW_QUOTES = 'view_quotes'
PERM_SEND_QUOTES = 'send_quotes'
PERM_CONVERT_QUOTES = 'convert_quotes'
PERM_VIEW_ORDERS = 'view_orders'
PERM_VIEW_LIFECYCLE = 'view_lifecycle'
PERM_VIEW_BILLING = 'view_billing'
PERM_MANAGE_USERS = 'manage_users'
PERM_MANAGE_ADMINS = 'manage_admins'
PERM_MANAGE_PERMISSIONS = 'manage_permissions'
PERM_MANAGE_CATALOG_SYNC = 'manage_catalog_sync'
PERM_MANAGE_MANAGED_SERVICES = 'manage_managed_services'
PERM_MANAGE_LIFECYCLE = 'manage_lifecycle'
PERM_MANAGE_BILLING = 'manage_billing'
PERM_MANAGE_PRICING = 'manage_pricing'

PERM_MANAGE_PRODUCTS = 'manage_products'
PERM_VIEW_VENDOR_ORDERS = 'view_vendor_orders'
PERM_MANAGE_VENDOR_TEAM = 'manage_vendor_team'
PERM_VIEW_VENDOR_ANALYTICS = 'view_vendor_analytics'

PERM_PLACE_ORDERS = 'place_orders'
PERM_VIEW_COMPANY_ORDERS = 'view_company_orders'
PERM_MANAGE_COMPANY_USERS = 'manage_company_users'
PERM_VIEW_COMPANY_BILLING = 'view_company_billing'

PERMISSION_CATALOG: dict[str, str] = {
    PERM_VIEW_CATALOG: 'Browse catalog and product details',
    PERM_MANAGE_CART: 'Manage cart and solution builder',
    PERM_GENERATE_QUOTES: 'Generate quotes from cart',
    PERM_VIEW_QUOTES: 'View quotes and quote details',
    PERM_SEND_QUOTES: 'Send quote to customer/procurement',
    PERM_CONVERT_QUOTES: 'Convert quote into order',
    PERM_VIEW_ORDERS: 'View orders and order timelines',
    PERM_VIEW_LIFECYCLE: 'View contracts, subscriptions, assets, and workflows',
    PERM_VIEW_BILLING: 'View billing analytics, invoices, and payment history',
    PERM_MANAGE_USERS: 'Create and manage standard users',
    PERM_MANAGE_ADMINS: 'Create and manage admin users',
    PERM_MANAGE_PERMISSIONS: 'Edit user/admin permission assignments',
    PERM_MANAGE_CATALOG_SYNC: 'Run and manage CDW catalog sync',
    PERM_MANAGE_MANAGED_SERVICES: 'Edit managed service catalog settings',
    PERM_MANAGE_LIFECYCLE: 'Advance lifecycle workflow and update subscription lifecycle states',
    PERM_MANAGE_BILLING: 'Run invoicing and record invoice payments',
    PERM_MANAGE_PRICING: 'Manage customer and deal-level discount rules',
    PERM_MANAGE_PRODUCTS: 'Manage vendor product listings',
    PERM_VIEW_VENDOR_ORDERS: 'View orders for vendor products',
    PERM_MANAGE_VENDOR_TEAM: 'Manage vendor team members',
    PERM_VIEW_VENDOR_ANALYTICS: 'View vendor analytics and reports',
    PERM_PLACE_ORDERS: 'Place orders as a company buyer',
    PERM_VIEW_COMPANY_ORDERS: 'View company order history',
    PERM_MANAGE_COMPANY_USERS: 'Manage company team members',
    PERM_VIEW_COMPANY_BILLING: 'View company billing and invoices',
}

USER_PERMISSION_SCOPE = {
    PERM_VIEW_CATALOG,
    PERM_MANAGE_CART,
    PERM_GENERATE_QUOTES,
    PERM_VIEW_QUOTES,
    PERM_VIEW_ORDERS,
    PERM_VIEW_LIFECYCLE,
    PERM_VIEW_BILLING,
}

ADMIN_PERMISSION_SCOPE = USER_PERMISSION_SCOPE | {
    PERM_SEND_QUOTES,
    PERM_CONVERT_QUOTES,
    PERM_MANAGE_USERS,
    PERM_MANAGE_PERMISSIONS,
    PERM_MANAGE_CATALOG_SYNC,
    PERM_MANAGE_MANAGED_SERVICES,
    PERM_MANAGE_LIFECYCLE,
    PERM_MANAGE_BILLING,
    PERM_MANAGE_PRICING,
}

SUPER_ADMIN_PERMISSION_SCOPE = set(PERMISSION_CATALOG.keys())

VENDOR_ADMIN_PERMISSION_SCOPE = {
    PERM_MANAGE_PRODUCTS,
    PERM_VIEW_VENDOR_ORDERS,
    PERM_MANAGE_VENDOR_TEAM,
    PERM_VIEW_VENDOR_ANALYTICS,
    PERM_VIEW_CATALOG,
}

VENDOR_USER_PERMISSION_SCOPE = {
    PERM_VIEW_VENDOR_ORDERS,
    PERM_VIEW_CATALOG,
    PERM_VIEW_VENDOR_ANALYTICS,
}

COMPANY_ADMIN_PERMISSION_SCOPE = {
    PERM_PLACE_ORDERS,
    PERM_VIEW_CATALOG,
    PERM_VIEW_COMPANY_ORDERS,
    PERM_MANAGE_COMPANY_USERS,
    PERM_VIEW_COMPANY_BILLING,
}

COMPANY_USER_PERMISSION_SCOPE = {
    PERM_VIEW_CATALOG,
    PERM_VIEW_COMPANY_ORDERS,
    PERM_PLACE_ORDERS,
}

ROLE_DEFAULT_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.USER: USER_PERMISSION_SCOPE,
    UserRole.ADMIN: ADMIN_PERMISSION_SCOPE,
    UserRole.SUPER_ADMIN: SUPER_ADMIN_PERMISSION_SCOPE,
}


def normalize_permissions(permissions: list[str] | None) -> list[str]:
    if not permissions:
        return []
    clean = [str(p).strip() for p in permissions if str(p).strip() in PERMISSION_CATALOG]
    return sorted(set(clean))


def default_permissions_for_role(role: UserRole) -> list[str]:
    return sorted(ROLE_DEFAULT_PERMISSIONS.get(role, set()))


def effective_permissions_for_role(role: UserRole, explicit_permissions: list[str] | None) -> list[str]:
    normalized = normalize_permissions(explicit_permissions)
    if normalized:
        return normalized
    return default_permissions_for_role(role)


def allowed_permissions_for_role(role: UserRole) -> list[str]:
    return sorted(ROLE_DEFAULT_PERMISSIONS.get(role, set()))
