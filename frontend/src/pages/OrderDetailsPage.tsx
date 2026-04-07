import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { OrderDetail, OrderLine, WorkflowInstance } from '../types/commerce';

const timelineSteps = ['Ordered', 'Supplier', 'QC', 'Shipped', 'Delivered'] as const;
const statusStepIndex: Record<string, number> = {
  SUBMITTED: 0,
  PROCESSING: 2,
  VENDOR_ORDERED: 2,
  SHIPPED: 3,
  DELIVERED: 4,
  ACTIVE: 4,
};

export const OrderDetailsPage = () => {
  const { orderId } = useParams();
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowInstance | null>(null);
  const [advancingWorkflow, setAdvancingWorkflow] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken || !orderId) return;
    setError('');
    try {
      const [orderData, workflowData] = await Promise.all([
        commerceApi.getOrder(accessToken, orderId),
        commerceApi.getOrderWorkflow(accessToken, orderId),
      ]);
      setOrder(orderData);
      setWorkflow(workflowData);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load order');
    }
  };

  useEffect(() => {
    load();
  }, [accessToken, orderId]);

  const parentNameById = useMemo(() => {
    const map = new Map<string, string>();
    (order?.lines || []).forEach((line) => map.set(line.id, line.name));
    return map;
  }, [order?.lines]);

  const activeStepIndex = useMemo(() => {
    if (workflow?.steps?.length) {
      const sorted = [...workflow.steps].sort((a, b) => a.sequence - b.sequence);
      const inProgressIndex = sorted.findIndex((step) => step.status === 'IN_PROGRESS');
      if (inProgressIndex >= 0) return inProgressIndex;
      const doneCount = sorted.filter((step) => step.status === 'DONE').length;
      return Math.max(0, Math.min(sorted.length - 1, doneCount - 1));
    }
    if (!order) return 0;
    return statusStepIndex[order.status] ?? 0;
  }, [order, workflow]);

  const timelineLabels = useMemo(() => {
    if (workflow?.steps?.length) {
      return [...workflow.steps].sort((a, b) => a.sequence - b.sequence).map((step) => step.display_name);
    }
    return [...timelineSteps];
  }, [workflow]);

  const sortedLines = useMemo(() => {
    const devices: OrderLine[] = [];
    const services: OrderLine[] = [];
    (order?.lines || []).forEach((line) => {
      if (line.line_type === 'SERVICE') services.push(line);
      else devices.push(line);
    });
    return [...devices, ...services];
  }, [order?.lines]);

  const onAdvanceWorkflow = async () => {
    if (!accessToken || !orderId) return;
    setAdvancingWorkflow(true);
    setError('');
    try {
      const updatedWorkflow = await commerceApi.advanceOrderWorkflow(accessToken, orderId);
      setWorkflow(updatedWorkflow);
      const refreshedOrder = await commerceApi.getOrder(accessToken, orderId);
      setOrder(refreshedOrder);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to advance workflow');
    } finally {
      setAdvancingWorkflow(false);
    }
  };

  return (
    <section className="content-wrap fade-in">
      <div className="content-head row-between">
        <h1>Order Details</h1>
        <Link to="/shop/orders" className="ghost-link">Back to Orders</Link>
      </div>

      {error && <div className="error-text">{error}</div>}

      {order && (
        <>
          <section className="order-status-card">
            <div className="row-between">
              <div>
                <h3>Order #{order.public_id}</h3>
                <p className="mini-note">
                  Status: {order.status}
                  {order.quote_public_id ? ` | Quote: ${order.quote_public_id}` : ''}
                  {workflow ? ` | Workflow: ${workflow.status}` : ''}
                </p>
              </div>
              <div className="row-between">
                {isAdmin && (
                  <button className="secondary-btn" onClick={onAdvanceWorkflow} disabled={advancingWorkflow || workflow?.status === 'COMPLETED'}>
                    {advancingWorkflow ? 'Advancing...' : 'Advance Workflow'}
                  </button>
                )}
                <span className="order-status-pill">{order.status}</span>
              </div>
            </div>
            <div className="status-track">
              {timelineLabels.map((step, index) => {
                const stateClass = index < activeStepIndex ? 'done' : index === activeStepIndex ? 'active' : '';
                return (
                  <div key={step} className={`track-step ${stateClass}`}>
                    <span className="dot" />
                    <span>{step}</span>
                  </div>
                );
              })}
            </div>
          </section>

          <div className="table-wrap">
            <table className="cart-table">
              <thead>
                <tr>
                  <th>Line</th>
                  <th>Type</th>
                  <th>Qty</th>
                  <th>Unit</th>
                  <th>Billing</th>
                </tr>
              </thead>
              <tbody>
                {sortedLines.map((line) => (
                  <tr key={line.id}>
                    <td>
                      {line.parent_line_id ? `↳ ${line.name} (attached to ${parentNameById.get(line.parent_line_id) || 'Device'})` : line.name}
                    </td>
                    <td>{line.line_type}</td>
                    <td>{line.qty}</td>
                    <td>${line.unit_price.toFixed(2)}</td>
                    <td>{line.billing === 'RECURRING' ? `Recurring ${line.interval || ''}`.trim() : 'One-time'}</td>
                  </tr>
                ))}
                {sortedLines.length === 0 && (
                  <tr>
                    <td colSpan={5} className="mini-note">No order lines found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
};
