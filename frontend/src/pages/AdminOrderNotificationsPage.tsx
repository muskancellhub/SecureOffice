import { useEffect, useMemo, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';

const parseRecipientInput = (value: string): string[] =>
  Array.from(
    new Set(
      value
        .split(/[\n,;]+/g)
        .map((row) => row.trim().toLowerCase())
        .filter(Boolean),
    ),
  );

export const AdminOrderNotificationsPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const canManage = useMemo(
    () => isAdmin && new Set(user?.effective_permissions ?? []).has('manage_lifecycle'),
    [isAdmin, user?.effective_permissions],
  );

  const [input, setInput] = useState('');
  const [currentRecipients, setCurrentRecipients] = useState<string[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = async () => {
    if (!accessToken || !canManage) {
      setCurrentRecipients([]);
      setInput('');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const data = await commerceApi.getOrderNotificationRecipients(accessToken);
      setCurrentRecipients(data.recipients || []);
      setInput((data.recipients || []).join('\n'));
      setUpdatedAt(data.updated_at);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load order notification recipients');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [accessToken, canManage]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const onSave = async () => {
    if (!accessToken || !canManage) return;
    const recipients = parseRecipientInput(input);
    setSaving(true);
    setError('');
    try {
      const data = await commerceApi.updateOrderNotificationRecipients(accessToken, recipients);
      setCurrentRecipients(data.recipients || []);
      setInput((data.recipients || []).join('\n'));
      setUpdatedAt(data.updated_at);
      setNotice('Recipient list updated.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update recipients');
    } finally {
      setSaving(false);
    }
  };

  const previewRecipients = parseRecipientInput(input);

  return (
    <section className="content-wrap fade-in">
      {!isAdmin && <div className="error-text">Admin access required.</div>}
      {isAdmin && (
        <>
          <div className="content-head">
            <h1>Order Notifications</h1>
            <p className="lead">Define recipient emails for fulfillment handoff when an order is captured.</p>
          </div>

          {!canManage && <div className="error-text">Missing permission: `manage_lifecycle`.</div>}
          {error && <div className="error-text">{error}</div>}
          {notice && <div className="toast-notice">{notice}</div>}
          {loading && <div className="mini-note">Loading recipient settings...</div>}

          {canManage && (
            <article className="dashboard-panel">
              <h3>Fulfillment Recipient Emails</h3>
              <p className="mini-note">Enter one email per line (comma and semicolon separators are also supported).</p>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={10}
                placeholder="ops@company.com&#10;vendor-queue@partner.com"
              />
              <div className="mini-note" style={{ marginTop: '0.75rem' }}>
                Active recipients: {previewRecipients.length}
              </div>
              <div className="line-actions" style={{ marginTop: '1rem' }}>
                <button className="primary-btn" onClick={onSave} disabled={saving}>
                  {saving ? 'Saving...' : 'Save Recipients'}
                </button>
              </div>

              <div style={{ marginTop: '1rem' }}>
                <h4>Configured List</h4>
                {currentRecipients.length > 0 ? (
                  <ul>
                    {currentRecipients.map((email) => (
                      <li key={email}>{email}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mini-note">No recipients configured yet. Order emails will be skipped until saved.</p>
                )}
                {updatedAt && <p className="mini-note">Last updated: {new Date(updatedAt).toLocaleString()}</p>}
              </div>
            </article>
          )}
        </>
      )}
    </section>
  );
};
