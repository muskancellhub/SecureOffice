import { useEffect, useMemo, useState } from 'react';
import { Building2, Clock, Mail, Plus, Save, X } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { extractApiError, isValidEmail } from '../utils/extractApiError';

const normalizeEmail = (value: string): string => value.trim().toLowerCase();

export const AdminOrderNotificationsPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const canManage = useMemo(
    () => isAdmin && new Set(user?.effective_permissions ?? []).has('manage_lifecycle'),
    [isAdmin, user?.effective_permissions],
  );

  const [recipients, setRecipients] = useState<string[]>([]);
  const [original, setOriginal] = useState<string[]>([]);
  const [orgName, setOrgName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [updatedAt, setUpdatedAt] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = async () => {
    if (!accessToken || !canManage) { setRecipients([]); setOriginal([]); return; }
    setLoading(true);
    setError('');
    try {
      const [data, profile] = await Promise.all([
        commerceApi.getOrderNotificationRecipients(accessToken),
        commerceApi.getOnboardingProfile(accessToken).catch(() => null),
      ]);
      const list = data.recipients || [];
      setRecipients(list);
      setOriginal(list);
      setUpdatedAt(data.updated_at);
      setOrgName(profile?.organization_name || '');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load order notification recipients'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [accessToken, canManage]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const dirty = useMemo(() => {
    if (recipients.length !== original.length) return true;
    const a = [...recipients].sort();
    const b = [...original].sort();
    return a.some((v, i) => v !== b[i]);
  }, [recipients, original]);

  const addRecipient = () => {
    const email = normalizeEmail(newEmail);
    if (!email) return;
    if (!isValidEmail(email)) { setError('Please enter a valid email address'); return; }
    if (recipients.includes(email)) { setError('That email is already in the list'); return; }
    setError('');
    setRecipients((prev) => [...prev, email]);
    setNewEmail('');
  };

  const removeRecipient = (email: string) => {
    setRecipients((prev) => prev.filter((e) => e !== email));
  };

  const onSave = async () => {
    if (!accessToken || !canManage) return;
    setSaving(true);
    setError('');
    try {
      const data = await commerceApi.updateOrderNotificationRecipients(accessToken, recipients);
      const list = data.recipients || [];
      setRecipients(list);
      setOriginal(list);
      setUpdatedAt(data.updated_at);
      setNotice('Recipient list saved.');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update recipients'));
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return <section className="content-wrap fade-in"><div className="error-text">Admin access required.</div></section>;
  }

  return (
    <section className="content-wrap fade-in order-emails-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><Mail size={15} /> Admin</span>
          <h1>Order emails</h1>
          <p className="apx-subtitle">Recipients notified when an order is captured for fulfillment handoff.</p>
          <div className="apx-scope">
            <span className="apx-scope-chip"><Building2 size={14} /> Scope: {orgName || 'All tenants'}</span>
            <span className="apx-scope-meta">{recipients.length} recipient{recipients.length === 1 ? '' : 's'}</span>
          </div>
        </div>
      </header>

      {!canManage && <div className="error-text">Missing permission: `manage_lifecycle`.</div>}
      {error && <div className="error-text">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}
      {loading && <div className="mini-note">Loading recipient settings…</div>}

      {canManage && (
        <div className="apx-table-card oe-card">
          <div className="oe-card-head">
            <h3 className="apx-modal-title" style={{ margin: 0 }}>Fulfillment recipients</h3>
            {updatedAt && (
              <span className="oe-updated"><Clock size={14} /> Updated {new Date(updatedAt).toLocaleString()}</span>
            )}
          </div>

          <div className="oe-add-row">
            <div className="apx-search oe-input">
              <Mail size={16} />
              <input
                type="email"
                placeholder="ops@company.com"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addRecipient(); } }}
              />
            </div>
            <button className="apx-add-btn" onClick={addRecipient} disabled={!newEmail.trim()}>
              <Plus size={17} /> Add recipient
            </button>
          </div>

          {recipients.length === 0 ? (
            <div className="oe-empty">
              <span className="oe-empty-icon"><Mail size={26} strokeWidth={1.3} /></span>
              <p>No recipients yet. Order emails will be skipped until at least one is saved.</p>
            </div>
          ) : (
            <ul className="oe-list">
              {recipients.map((email) => (
                <li key={email} className="oe-row">
                  <span className="oe-avatar"><Mail size={16} /></span>
                  <span className="oe-email">{email}</span>
                  <button className="oe-remove" aria-label={`Remove ${email}`} title="Remove" onClick={() => removeRecipient(email)}>
                    <X size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="oe-foot">
            <span className="oe-foot-note">
              {dirty ? 'Unsaved changes' : 'All changes saved'}
            </span>
            <button className="apx-add-btn" onClick={onSave} disabled={saving || !dirty}>
              <Save size={15} /> {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
