import { useEffect, useMemo, useState } from 'react';
import * as usersApi from '../api/usersApi';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types/auth';
import type { PermissionCatalogItem, UserSummary } from '../types/users';

const USER_SCOPE = ['view_catalog', 'manage_cart', 'generate_quotes', 'view_quotes', 'view_orders', 'view_lifecycle', 'view_billing'];
const ADMIN_SCOPE = [
  ...USER_SCOPE,
  'send_quotes',
  'convert_quotes',
  'manage_users',
  'manage_permissions',
  'manage_catalog_sync',
  'manage_managed_services',
  'manage_lifecycle',
  'manage_billing',
];
const SUPER_SCOPE = [...ADMIN_SCOPE, 'manage_admins'];

const allowedScopeByRole: Record<UserRole, string[]> = {
  USER: USER_SCOPE,
  ADMIN: ADMIN_SCOPE,
  SUPER_ADMIN: SUPER_SCOPE,
};

export const AdminUserManagementPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const isSuperAdmin = user?.role === 'SUPER_ADMIN';
  const actorPermissionSet = useMemo(() => new Set(user?.effective_permissions ?? []), [user?.effective_permissions]);
  const canManageUsers = isAdmin && actorPermissionSet.has('manage_users');
  const canManageAdmins = isSuperAdmin && actorPermissionSet.has('manage_admins');
  const canManagePermissions = isAdmin && actorPermissionSet.has('manage_permissions');

  const [users, setUsers] = useState<UserSummary[]>([]);
  const [catalog, setCatalog] = useState<PermissionCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [createRole, setCreateRole] = useState<UserRole>('USER');
  const [tenantId, setTenantId] = useState('');

  const [roleSavingUserId, setRoleSavingUserId] = useState<string | null>(null);
  const [permissionSavingUserId, setPermissionSavingUserId] = useState<string | null>(null);
  const [permissionEditorUserId, setPermissionEditorUserId] = useState<string | null>(null);
  const [workingPermissions, setWorkingPermissions] = useState<string[]>([]);

  const createRoleOptions = useMemo<UserRole[]>(
    () => {
      if (!canManageUsers) return [];
      return isSuperAdmin && canManageAdmins ? ['ADMIN', 'USER'] : ['USER'];
    },
    [canManageAdmins, canManageUsers, isSuperAdmin],
  );

  useEffect(() => {
    if (createRoleOptions.length === 0) return;
    if (!createRoleOptions.includes(createRole)) {
      setCreateRole(createRoleOptions[0]);
    }
  }, [createRole, createRoleOptions]);

  const load = async () => {
    if (!accessToken || !isAdmin || !canManageUsers) {
      setUsers([]);
      setCatalog([]);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const [fetchedUsers, fetchedCatalog] = await Promise.all([
        usersApi.listUsers(accessToken),
        canManagePermissions ? usersApi.getPermissionCatalog(accessToken) : Promise.resolve([]),
      ]);
      setUsers(fetchedUsers);
      setCatalog(fetchedCatalog);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [accessToken, canManagePermissions, canManageUsers, isAdmin]);

  const onCreateUser = async () => {
    if (!accessToken || !canManageUsers) return;
    setCreating(true);
    setError('');
    try {
      await usersApi.createUser(accessToken, {
        name,
        email,
        mobile: mobile || undefined,
        password,
        role: createRole,
        tenant_id: isSuperAdmin && tenantId ? tenantId : undefined,
      });
      setName('');
      setEmail('');
      setMobile('');
      setPassword('');
      setTenantId('');
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to create user');
    } finally {
      setCreating(false);
    }
  };

  const canEditTarget = (target: UserSummary) => {
    if (!user || !canManageUsers) return false;
    if (user.role === 'SUPER_ADMIN') {
      if (target.role === 'SUPER_ADMIN') return false;
      if (target.role === 'ADMIN' && !canManageAdmins) return false;
      return true;
    }
    return user.role === 'ADMIN' && target.role === 'USER' && target.tenant_id === user.tenant_id;
  };

  const onUpdateRole = async (target: UserSummary, nextRole: UserRole) => {
    if (!accessToken) return;
    setRoleSavingUserId(target.id);
    setError('');
    try {
      const updated = await usersApi.updateUserRole(accessToken, target.id, nextRole);
      setUsers((prev) => prev.map((u) => (u.id === target.id ? updated : u)));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update role');
    } finally {
      setRoleSavingUserId(null);
    }
  };

  const openPermissions = (target: UserSummary) => {
    setPermissionEditorUserId(target.id);
    setWorkingPermissions(target.effective_permissions || []);
  };

  const onTogglePermission = (code: string) => {
    setWorkingPermissions((prev) => (prev.includes(code) ? prev.filter((p) => p !== code) : [...prev, code]));
  };

  const onSavePermissions = async (target: UserSummary) => {
    if (!accessToken || !canManagePermissions) return;
    setPermissionSavingUserId(target.id);
    setError('');
    try {
      const updated = await usersApi.updateUserPermissions(accessToken, target.id, workingPermissions);
      setUsers((prev) => prev.map((u) => (u.id === target.id ? updated : u)));
      setPermissionEditorUserId(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update permissions');
    } finally {
      setPermissionSavingUserId(null);
    }
  };

  return (
    <section className="content-wrap fade-in">
      {!isAdmin && <div className="error-text">Admin access required.</div>}
      {isAdmin && (
        <>
          <div className="content-head">
            <h1>User Access</h1>
            <p className="lead">SUPER_ADMIN can create admins. ADMIN can create users. Manage role-based permissions here.</p>
          </div>

          {error && <div className="error-text">{error}</div>}

          {!canManageUsers && (
            <div className="error-text">You do not have `manage_users` permission. Ask a SUPER_ADMIN to update your access.</div>
          )}

          {canManageUsers && (
            <>
              <div className="selector-card">
                <h3>Create User</h3>
                <div className="inline-fields">
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
                  <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
                </div>
                <div className="inline-fields">
                  <input value={mobile} onChange={(e) => setMobile(e.target.value)} placeholder="Mobile (optional)" />
                  <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password (min 8 chars)" type="password" />
                </div>
                <div className="inline-fields">
                  <select value={createRole} onChange={(e) => setCreateRole(e.target.value as UserRole)}>
                    {createRoleOptions.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                  {isSuperAdmin ? (
                    <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="Tenant ID (optional)" />
                  ) : (
                    <input value={user?.tenant_id || ''} disabled />
                  )}
                </div>
                <button
                  className="primary-btn"
                  onClick={onCreateUser}
                  disabled={creating || createRoleOptions.length === 0 || !name || !email || password.length < 8}
                >
                  {creating ? 'Creating...' : 'Create User'}
                </button>
              </div>

              {loading && <div className="mini-note">Loading users...</div>}

              <div className="table-wrap">
                <table className="cart-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Tenant</th>
                      <th>Permissions</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((target) => {
                      const editable = canEditTarget(target);
                      const allowedPermissions = allowedScopeByRole[target.role];
                      return (
                        <tr key={target.id}>
                          <td>{target.name}</td>
                          <td>{target.email}</td>
                          <td>
                            <select
                              value={target.role}
                              disabled={!editable || roleSavingUserId === target.id}
                              onChange={(e) => onUpdateRole(target, e.target.value as UserRole)}
                            >
                              {(isSuperAdmin && canManageAdmins ? ['ADMIN', 'USER'] : ['USER']).map((role) => (
                                <option key={role} value={role}>
                                  {role}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>{target.tenant_id.slice(0, 8)}...</td>
                          <td>{target.effective_permissions.length}</td>
                          <td>
                            <button className="secondary-btn" disabled={!editable || !canManagePermissions} onClick={() => openPermissions(target)}>
                              Configure
                            </button>
                            {permissionEditorUserId === target.id && canManagePermissions && (
                              <div className="permissions-editor">
                                {catalog
                                  .filter((item) => allowedPermissions.includes(item.code))
                                  .map((item) => (
                                    <label key={item.code} className="permission-row">
                                      <input
                                        type="checkbox"
                                        checked={workingPermissions.includes(item.code)}
                                        onChange={() => onTogglePermission(item.code)}
                                      />
                                      <span><strong>{item.code}</strong> - {item.description}</span>
                                    </label>
                                  ))}
                                <div className="permission-actions">
                                  <button
                                    className="primary-btn"
                                    onClick={() => onSavePermissions(target)}
                                    disabled={permissionSavingUserId === target.id}
                                  >
                                    {permissionSavingUserId === target.id ? 'Saving...' : 'Save Permissions'}
                                  </button>
                                  <button className="ghost-btn" onClick={() => setPermissionEditorUserId(null)}>
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {users.length === 0 && (
                      <tr>
                        <td colSpan={6} className="mini-note">No users found.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {!canManagePermissions && canManageUsers && (
            <div className="mini-note">Permission editor is disabled for your account (`manage_permissions` required).</div>
          )}

          {!canManageUsers && (
            <div className="table-wrap">
              <table className="cart-table">
                <tbody>
                  <tr>
                    <td colSpan={6} className="mini-note">No access to user records.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
};
