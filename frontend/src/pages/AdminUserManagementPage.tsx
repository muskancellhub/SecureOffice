import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Building2, KeyRound, MoreVertical, RotateCw, Save, ShieldCheck, UserPlus, X } from 'lucide-react';
import * as usersApi from '../api/usersApi';
import * as commerceApi from '../api/commerceApi';
import * as authApi from '../api/authApi';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';
import type { UserRole } from '../types/auth';
import type { PermissionCatalogItem, UserSummary } from '../types/users';
import { extractApiError, isValidEmail } from '../utils/extractApiError';

const USER_SCOPE = ['view_catalog', 'manage_cart', 'generate_quotes', 'view_quotes', 'view_orders', 'view_lifecycle', 'view_billing'];
const ADMIN_SCOPE = [
  ...USER_SCOPE,
  'send_quotes', 'convert_quotes', 'manage_users', 'manage_permissions',
  'manage_catalog_sync', 'manage_managed_services', 'manage_lifecycle', 'manage_billing',
];
const SUPER_SCOPE = [...ADMIN_SCOPE, 'manage_admins'];

const allowedScopeByRole: Record<UserRole, string[]> = {
  USER: USER_SCOPE,
  ADMIN: ADMIN_SCOPE,
  SUPER_ADMIN: SUPER_SCOPE,
};

// Roles shown as columns in the permission matrix (our real roles).
const MATRIX_ROLES: { role: UserRole; label: string }[] = [
  { role: 'SUPER_ADMIN', label: 'Super Admin' },
  { role: 'ADMIN', label: 'Admin' },
  { role: 'USER', label: 'User' },
];

const ROLE_LABEL: Record<UserRole, string> = { SUPER_ADMIN: 'Super Admin', ADMIN: 'Admin', USER: 'User' };
const ROLE_TONE: Record<UserRole, string> = { SUPER_ADMIN: 'super', ADMIN: 'admin', USER: 'user' };

const initialsOf = (name: string, email: string): string => {
  const src = (name || email || 'U').trim();
  const parts = src.split(/[\s._-]+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('') || src[0]?.toUpperCase() || 'U');
};

const AVATAR_TONES = ['indigo', 'blue', 'violet', 'teal', 'rose'];
const avatarTone = (seed: string): string => {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_TONES[h % AVATAR_TONES.length];
};

const relativeTime = (iso: string): string => {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diff = Date.now() - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

export const AdminUserManagementPage = () => {
  const { accessToken, user } = useAuth();
  const { activeTenantId, activeTenant } = useTenant();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const isSuperAdmin = user?.role === 'SUPER_ADMIN';
  const actorPermissionSet = useMemo(() => new Set(user?.effective_permissions ?? []), [user?.effective_permissions]);
  const canManageUsers = isAdmin && actorPermissionSet.has('manage_users');
  const canManageAdmins = isSuperAdmin && actorPermissionSet.has('manage_admins');
  const canManagePermissions = isAdmin && actorPermissionSet.has('manage_permissions');

  const [users, setUsers] = useState<UserSummary[]>([]);
  const [catalog, setCatalog] = useState<PermissionCatalogItem[]>([]);
  const [orgName, setOrgName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // invite modal
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState<UserRole>('USER');
  const [inviting, setInviting] = useState(false);

  // super-admin password setup (admin-set: you choose the password)
  const [saSetupEmail, setSaSetupEmail] = useState('');
  const [saSetupPassword, setSaSetupPassword] = useState('');
  const [saSetupSending, setSaSetupSending] = useState(false);

  // row menu + edit-access modal
  const [menuUserId, setMenuUserId] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<UserSummary | null>(null);
  const [editRole, setEditRole] = useState<UserRole>('USER');
  const [editPermissions, setEditPermissions] = useState<string[]>([]);
  const [savingEdit, setSavingEdit] = useState(false);

  const inviteRoleOptions = useMemo<UserRole[]>(
    () => (isSuperAdmin && canManageAdmins ? ['USER', 'ADMIN'] : ['USER']),
    [canManageAdmins, isSuperAdmin],
  );

  useEffect(() => {
    if (!inviteRoleOptions.includes(inviteRole)) setInviteRole(inviteRoleOptions[0]);
  }, [inviteRole, inviteRoleOptions]);

  const load = async () => {
    if (!accessToken || !canManageUsers) { setUsers([]); setCatalog([]); return; }
    setLoading(true);
    setError('');
    try {
      const [fetchedUsers, fetchedCatalog, profile] = await Promise.all([
        usersApi.listUsers(accessToken),
        canManagePermissions ? usersApi.getPermissionCatalog(accessToken) : Promise.resolve([] as PermissionCatalogItem[]),
        commerceApi.getOnboardingProfile(accessToken).catch(() => null),
      ]);
      setUsers(fetchedUsers);
      setCatalog(fetchedCatalog);
      setOrgName(profile?.organization_name || '');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load users'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [accessToken, canManagePermissions, canManageUsers, isAdmin, activeTenantId]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(''), 2800);
    return () => window.clearTimeout(t);
  }, [notice]);

  const saPasswordError = (pw: string): string | null => {
    if (pw.length < 12) return 'Password must be at least 12 characters.';
    if (!/[a-z]/.test(pw)) return 'Password must include a lowercase letter.';
    if (!/[A-Z]/.test(pw)) return 'Password must include an uppercase letter.';
    if (!/\d/.test(pw)) return 'Password must include a number.';
    if (!/[^A-Za-z0-9]/.test(pw)) return 'Password must include a symbol.';
    return null;
  };

  const onSetSuperAdminCredentials = async () => {
    if (!accessToken) return;
    if (!isValidEmail(saSetupEmail)) { setError('Please enter a valid email address'); return; }
    const pwErr = saPasswordError(saSetupPassword);
    if (pwErr) { setError(pwErr); return; }
    setSaSetupSending(true);
    setError('');
    setNotice('');
    try {
      await authApi.setSuperAdminCredentials(accessToken, saSetupEmail.trim(), saSetupPassword);
      setNotice(`Super-admin password set for ${saSetupEmail.trim()}. Share it securely with them.`);
      setSaSetupEmail('');
      setSaSetupPassword('');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to set password. The email must be in SUPER_ADMIN_EMAILS.'));
    } finally {
      setSaSetupSending(false);
    }
  };

  const onInvite = async () => {
    if (!accessToken) return;
    if (!isValidEmail(inviteEmail)) { setError('Please enter a valid email address'); return; }
    setInviting(true);
    setError('');
    try {
      const result = await usersApi.inviteUser(accessToken, {
        email: inviteEmail,
        name: inviteName || undefined,
        role: inviteRole,
        tenant_id: isSuperAdmin && activeTenantId ? activeTenantId : undefined,
      });
      if (result.email_sent) {
        setNotice(`Invite sent to ${inviteEmail}`);
      } else {
        // Account created, but the email did not go out — surface the real reason
        // instead of a false "sent" so it isn't silently lost.
        setError(
          `User added, but the invite email could not be sent${result.email_error ? `: ${result.email_error}` : ''}. `
          + 'Check the email provider configuration/quota — they can still sign in at the login page with their email.',
        );
      }
      setInviteEmail('');
      setInviteName('');
      setInviteOpen(false);
      await load();
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to invite user'));
    } finally {
      setInviting(false);
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

  const openEdit = (target: UserSummary) => {
    setMenuUserId(null);
    setEditTarget(target);
    setEditRole(target.role);
    setEditPermissions(target.effective_permissions || []);
  };

  const togglePermission = (code: string) => {
    setEditPermissions((prev) => (prev.includes(code) ? prev.filter((p) => p !== code) : [...prev, code]));
  };

  const saveEdit = async () => {
    if (!accessToken || !editTarget) return;
    setSavingEdit(true);
    setError('');
    try {
      let updated = editTarget;
      if (editRole !== editTarget.role) {
        updated = await usersApi.updateUserRole(accessToken, editTarget.id, editRole);
      }
      if (canManagePermissions) {
        updated = await usersApi.updateUserPermissions(accessToken, editTarget.id, editPermissions);
      }
      setUsers((prev) => prev.map((u) => (u.id === editTarget.id ? updated : u)));
      setNotice(`Updated ${editTarget.name || editTarget.email}`);
      setEditTarget(null);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update access'));
    } finally {
      setSavingEdit(false);
    }
  };

  const editRoleOptions: UserRole[] = isSuperAdmin && canManageAdmins ? ['ADMIN', 'USER'] : ['USER'];

  if (!isAdmin) {
    return <section className="content-wrap fade-in"><div className="error-text">Admin access required.</div></section>;
  }

  return (
    <section className="content-wrap fade-in admin-users-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><ShieldCheck size={15} /> Admin</span>
          <h1>User access</h1>
          <p className="apx-subtitle">Manage team members, roles, and permissions across the workspace.</p>
          <div className="apx-scope">
            <span className="apx-scope-chip"><Building2 size={14} /> Scope: {orgName || activeTenant?.name || 'All tenants'}</span>
            <span className="apx-scope-meta">{users.length} member{users.length === 1 ? '' : 's'}</span>
          </div>
        </div>
        {canManageUsers && (
          <button className="apx-add-btn" onClick={() => setInviteOpen(true)}>
            <UserPlus size={18} /> Invite user
          </button>
        )}
      </header>

      {/* BUG-UA-001: prominent, full-width alert with retry — the old small red
          text between the header and the password form was easy to miss. */}
      {error && (
        <div className="admin-error-banner" role="alert">
          <AlertTriangle size={16} />
          <span className="admin-error-banner-msg">{error}</span>
          <button type="button" className="admin-error-banner-retry" onClick={load}>
            <RotateCw size={13} /> Retry
          </button>
        </div>
      )}
      {notice && <div className="toast-notice">{notice}</div>}

      {isSuperAdmin && (
        <div className="apx-table-card" style={{ padding: 20, marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <KeyRound size={16} /> Super-admin password
          </h3>
          <p className="apx-subtitle" style={{ marginTop: 0 }}>
            Set a password for a teammate listed in <code>SUPER_ADMIN_EMAILS</code>, then share it securely with them.
            Min 12 chars with upper, lower, number, and symbol.
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="email"
              placeholder="teammate@cellhubms.com"
              value={saSetupEmail}
              onChange={(e) => setSaSetupEmail(e.target.value)}
              style={{ flex: '1 1 240px', minWidth: 220 }}
            />
            <input
              type="text"
              placeholder="Password to set"
              value={saSetupPassword}
              onChange={(e) => setSaSetupPassword(e.target.value)}
              autoComplete="off"
              style={{ flex: '1 1 200px', minWidth: 200 }}
            />
            <button
              className="apx-add-btn"
              onClick={onSetSuperAdminCredentials}
              disabled={saSetupSending || !saSetupEmail || !saSetupPassword}
            >
              {saSetupSending ? 'Setting…' : 'Set password'}
            </button>
          </div>
        </div>
      )}

      {!canManageUsers && (
        <div className="error-text">You do not have `manage_users` permission. Ask a SUPER_ADMIN to update your access.</div>
      )}

      {canManageUsers && (
        <>
          <div className="apx-table-card usr-table-card">
            <div className="usr-thead">
              <span>User</span>
              <span>Role</span>
              <span>Status</span>
              <span>Joined</span>
              <span />
            </div>
            {loading && <div className="apx-empty">Loading…</div>}
            {!loading && users.length === 0 && <div className="apx-empty">No users found.</div>}
            {users.map((target) => {
              const editable = canEditTarget(target);
              return (
                <div key={target.id} className="usr-row">
                  <span className="usr-user">
                    <span className={`usr-avatar tone-${avatarTone(target.email)}`}>{initialsOf(target.name, target.email)}</span>
                    <span className="usr-user-copy">
                      <strong>{target.name || target.email.split('@')[0]}</strong>
                      <span>{target.email}</span>
                    </span>
                  </span>
                  <span><span className={`usr-role-badge tone-${ROLE_TONE[target.role]}`}>{ROLE_LABEL[target.role]}</span></span>
                  <span>
                    <span className={`usr-status ${target.is_verified ? 'active' : 'pending'}`}>
                      {target.is_verified ? 'Active' : 'Pending'}
                    </span>
                  </span>
                  <span className="usr-joined">{relativeTime(target.created_at)}</span>
                  <span className="usr-row-action">
                    {editable && (
                      <div className="usr-menu-wrap">
                        <button
                          className="apx-edit-btn usr-kebab"
                          aria-label="User actions"
                          onClick={() => setMenuUserId((id) => (id === target.id ? null : target.id))}
                        >
                          <MoreVertical size={16} />
                        </button>
                        {menuUserId === target.id && (
                          <div className="usr-menu" onMouseLeave={() => setMenuUserId(null)}>
                            <button onClick={() => openEdit(target)}>Edit access</button>
                          </div>
                        )}
                      </div>
                    )}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="apx-table-card usr-perms-card">
            <div className="usr-perms-title"><KeyRound size={17} /> Role permissions</div>
            <div className="usr-matrix">
              <div className="usr-matrix-head">
                <span>Permission</span>
                {MATRIX_ROLES.map((r) => <span key={r.role} className="usr-matrix-col">{r.label}</span>)}
              </div>
              {catalog.length === 0 && (
                <div className="apx-empty">
                  {canManagePermissions ? 'No permissions in catalog.' : 'Permission catalog requires `manage_permissions`.'}
                </div>
              )}
              {catalog.map((perm) => (
                <div key={perm.code} className="usr-matrix-row">
                  <span className="usr-perm-name" title={perm.code}>{perm.description || perm.code}</span>
                  {MATRIX_ROLES.map((r) => {
                    const has = allowedScopeByRole[r.role].includes(perm.code);
                    return (
                      <span key={r.role} className="usr-matrix-col">
                        {has ? <span className="usr-check">✓</span> : <span className="usr-dash">—</span>}
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Invite user modal */}
      {inviteOpen && (
        <div className="apx-modal-overlay" onClick={() => setInviteOpen(false)}>
          <div className="apx-modal apx-modal-sm" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setInviteOpen(false)}><X size={18} /></button>
            <h3 className="apx-modal-title">Invite user</h3>
            <p className="apx-modal-sub">We’ll email them a sign-in link. They log in with a one-time code.</p>
            <label className="apx-field">
              <span>Email address</span>
              <input type="email" placeholder="name@company.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} autoFocus />
            </label>
            <label className="apx-field">
              <span>Name (optional)</span>
              <input type="text" placeholder="Full name" value={inviteName} onChange={(e) => setInviteName(e.target.value)} />
            </label>
            <label className="apx-field">
              <span>Role</span>
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as UserRole)}>
                {inviteRoleOptions.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
            </label>
            {isSuperAdmin && (
              <p className="mini-note">Invited into <strong>{activeTenant?.name ?? 'the active tenant'}</strong> — change it with the tenant switcher.</p>
            )}
            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setInviteOpen(false)}>Cancel</button>
              <button className="apx-add-btn" onClick={onInvite} disabled={inviting || !inviteEmail}>
                <UserPlus size={15} /> {inviting ? 'Sending…' : 'Send invite'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit access modal */}
      {editTarget && (
        <div className="apx-modal-overlay" onClick={() => setEditTarget(null)}>
          <div className="apx-modal apx-modal-sm" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setEditTarget(null)}><X size={18} /></button>
            <h3 className="apx-modal-title">Edit access</h3>
            <p className="apx-modal-sub">{editTarget.name || editTarget.email} · <span className="apx-sku">{editTarget.email}</span></p>
            <label className="apx-field">
              <span>Role</span>
              <select value={editRole} onChange={(e) => setEditRole(e.target.value as UserRole)}>
                {editRoleOptions.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
            </label>
            {canManagePermissions && (
              <div className="apx-field">
                <span>Permissions</span>
                <div className="usr-perm-checks">
                  {catalog
                    .filter((item) => allowedScopeByRole[editRole].includes(item.code))
                    .map((item) => (
                      <label key={item.code} className="usr-perm-check">
                        <input type="checkbox" checked={editPermissions.includes(item.code)} onChange={() => togglePermission(item.code)} />
                        <span>{item.description || item.code}</span>
                      </label>
                    ))}
                </div>
              </div>
            )}
            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setEditTarget(null)}>Cancel</button>
              <button className="apx-add-btn" onClick={saveEdit} disabled={savingEdit}>
                <Save size={15} /> {savingEdit ? 'Saving…' : 'Save access'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
