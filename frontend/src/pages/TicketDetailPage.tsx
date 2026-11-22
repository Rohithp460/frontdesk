import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import api from '../api/client';
import { Layout } from '../components/Layout';
import { Ticket, TicketEvent, TicketPriority } from '../types';
import { useAuth } from '../context/AuthContext';
import { parseUtcDate } from '../utils/datetime';

export const TicketDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { agent } = useAuth();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reply, setReply] = useState('');
  const [note, setNote] = useState('');
  const [working, setWorking] = useState(false);
  const [showPriority, setShowPriority] = useState(false);
  const [actionError, setActionError] = useState('');

  const fetchTicket = async () => {
    try {
      const response = await api.get<Ticket>(`/tickets/${id}`);
      setTicket(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load ticket');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTicket();
  }, [id]);

  const runAction = async (
    action: () => Promise<unknown>,
    clear?: () => void,
  ) => {
    setWorking(true);
    setActionError('');
    try {
      const result: any = await action();
      const returnedTicket = result?.data as Ticket | undefined;
      if (
        returnedTicket?.reopened_from_ticket_id &&
        returnedTicket.id !== Number(id)
      ) {
        navigate(`/tickets/${returnedTicket.id}`);
      }
      clear?.();
      await fetchTicket();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('; ')
        : detail;
      setActionError(
        err.response?.status === 409
          ? message || 'This ticket changed. Refresh and try again.'
          : message || 'Action failed. Check the input and try again.',
      );
    } finally {
      setWorking(false);
    }
  };

  const formatDeadline = (value?: string | null) =>
    value
      ? parseUtcDate(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })
      : '—';

  if (loading) {
    return <Layout><div className="p-8 text-center text-slate-500">Loading ticket...</div></Layout>;
  }
  if (error || !ticket) {
    return <Layout><div className="p-8 text-center text-red-600">{error || 'Ticket not found'}</div></Layout>;
  }

  const canManage =
    agent?.role === 'ADMIN' || ticket.assigned_agent_id === agent?.id;
  const canAct =
    canManage && ticket.status !== 'RESOLVED' && ticket.status !== 'CLOSED';
  const isLate =
    ticket.status !== 'RESOLVED' &&
    ticket.status !== 'CLOSED' &&
    ((ticket.first_response_at == null &&
      !!ticket.response_deadline &&
      parseUtcDate(ticket.response_deadline).getTime() < Date.now()) ||
      (!!ticket.resolution_deadline &&
        parseUtcDate(ticket.resolution_deadline).getTime() < Date.now()));

  const timelineEvent = (event: TicketEvent) => {
    const isNote = event.event_type === 'INTERNAL_NOTE_ADDED';
    const isAgentReply = event.event_type === 'AGENT_REPLY';
    const isCustomerReply = event.event_type === 'CUSTOMER_REPLY';
    return (
      <div
        key={event.id}
        className={`rounded-xl border p-4 text-sm ${
          isNote
            ? 'border-amber-200 bg-amber-50'
            : isAgentReply
              ? 'border-blue-200 bg-blue-50'
              : isCustomerReply
                ? 'border-green-200 bg-green-50'
                : 'border-slate-200 bg-white'
        }`}
      >
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-800">
              {event.actor_name || event.actor_type}
            </span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-mono text-slate-600">
              {event.event_type}
            </span>
          </div>
          <span className="text-xs text-slate-400">
            {formatDeadline(event.occurred_at)}
          </span>
        </div>
        {isNote && (
          <>
            <div className="mb-1 text-xs font-semibold text-amber-800">
              🔒 Visible to Arvo team only.
            </div>
            <div className="whitespace-pre-wrap text-slate-800">{event.payload?.note}</div>
          </>
        )}
        {(isAgentReply || isCustomerReply) && (
          <div className="whitespace-pre-wrap text-slate-800">{event.payload?.message}</div>
        )}
        {!isNote && !isAgentReply && !isCustomerReply && event.payload && (
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-slate-500">
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        )}
      </div>
    );
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Link to="/" className="text-sm text-blue-600 hover:underline">← All tickets</Link>
          {canManage && (
            <button
              disabled={working}
              onClick={() =>
                runAction(() =>
                  api.post(`/tickets/${id}/customer-reply`, {
                    message: 'Demo customer reply: Thank you, here are the requested details.',
                  }),
                )
              }
              className="rounded-lg border border-purple-200 bg-purple-50 px-3 py-2 text-xs font-bold text-purple-700"
            >
              Simulate customer reply (demo only)
            </button>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col justify-between gap-4 md:flex-row">
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="font-mono font-bold text-blue-600">{ticket.public_ref}</span>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold">
                  {ticket.status}
                </span>
                <span className="rounded-full bg-amber-100 px-2 py-1 text-xs font-bold text-amber-800">
                  {ticket.priority}
                </span>
                {isLate && (
                  <span className="rounded-full bg-red-600 px-2 py-1 text-xs font-bold text-white">LATE</span>
                )}
                {ticket.status === 'WAITING_CUSTOMER' && (
                  <span className="rounded-full bg-purple-100 px-2 py-1 text-xs font-bold text-purple-700">
                    Waiting on customer
                  </span>
                )}
              </div>
              <h1 className="text-xl font-bold text-slate-900">{ticket.title}</h1>
            </div>
            <div className="flex flex-wrap gap-2">
              {ticket.assigned_agent_id == null && (
                <button
                  disabled={working}
                  onClick={() => runAction(() => api.post(`/tickets/${id}/claim`))}
                  className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700"
                >
                  Claim
                </button>
              )}
              {canAct && (
                <>
                  <button
                    disabled={working}
                    onClick={() => runAction(() => api.post(`/tickets/${id}/resolve`))}
                    className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs font-semibold text-green-700"
                  >
                    Resolve
                  </button>
                  <button
                    disabled={working}
                    onClick={() => runAction(() => api.post(`/tickets/${id}/close`))}
                    className="rounded-lg border border-slate-300 bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700"
                  >
                    Close
                  </button>
                </>
              )}
              {canManage && ticket.status === 'RESOLVED' && (
                <button
                  disabled={working}
                  onClick={() => runAction(() => api.post(`/tickets/${id}/reopen`))}
                  className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700"
                >
                  Reopen
                </button>
              )}
              {canAct && <div className="relative">
                <button
                  disabled={ticket.status === 'RESOLVED' || ticket.status === 'CLOSED'}
                  onClick={() => setShowPriority(!showPriority)}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50"
                >
                  Change priority ▾
                </button>
                {showPriority && (
                  <div className="absolute right-0 z-20 mt-1 w-36 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                    {(['CRITICAL', 'MEDIUM', 'LOW'] as TicketPriority[]).map((priority) => (
                      <button
                        key={priority}
                        onClick={() =>
                          runAction(
                            () => api.patch(`/tickets/${id}/priority`, { priority }),
                            () => setShowPriority(false),
                          )
                        }
                        className="block w-full rounded px-3 py-2 text-left text-xs font-semibold hover:bg-slate-50"
                      >
                        {priority}
                      </button>
                    ))}
                  </div>
                )}
              </div>}
            </div>
          </div>

          {actionError && (
            <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {actionError}
            </p>
          )}

          <div className="mt-5 grid gap-4 border-t border-slate-100 pt-4 text-xs md:grid-cols-4">
            <div>
              <div className="text-slate-400">Customer</div>
              <div className="font-semibold text-slate-800">
                {ticket.customer?.name || `Customer #${ticket.customer_id}`}
              </div>
            </div>
            <div>
              <div className="text-slate-400">Assigned agent</div>
              <div className="font-semibold text-slate-800">
                {ticket.assigned_agent?.name || 'Unassigned'}
              </div>
            </div>
            <div>
              <div className="text-slate-400">Response deadline</div>
              <div className="font-semibold text-slate-800">{formatDeadline(ticket.response_deadline)}</div>
            </div>
            <div>
              <div className="text-slate-400">Resolution deadline</div>
              <div className="font-semibold text-slate-800">{formatDeadline(ticket.resolution_deadline)}</div>
            </div>
          </div>
          <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
            {ticket.description}
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {canAct && <div className="rounded-2xl border border-blue-200 bg-white p-5">
            <h2 className="mb-1 text-sm font-bold text-slate-800">Reply to customer</h2>
            <p className="mb-3 text-xs text-slate-500">
              Sends a customer-visible reply and starts the customer wait period.
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                runAction(
                  () => api.post(`/tickets/${id}/replies`, { message: reply }),
                  () => setReply(''),
                );
              }}
              className="space-y-3"
            >
              <textarea
                required
                maxLength={10000}
                rows={5}
                value={reply}
                onChange={(event) => setReply(event.target.value)}
                placeholder="Write a customer-visible response"
                className="w-full rounded-lg border border-slate-200 p-3 text-sm"
              />
              <button
                disabled={working || !canAct}
                className="w-full rounded-lg bg-blue-600 py-2 text-xs font-semibold text-white disabled:opacity-50"
              >
                Send customer reply
              </button>
            </form>
          </div>}

          {canManage && <div className="rounded-2xl border border-amber-200 bg-white p-5">
            <h2 className="mb-1 text-sm font-bold text-slate-800">Internal note</h2>
            <p className="mb-3 text-xs font-semibold text-amber-800">
              Visible to Arvo team only. Never visible to the customer.
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                runAction(
                  () => api.post(`/tickets/${id}/internal-notes`, { note }),
                  () => setNote(''),
                );
              }}
              className="space-y-3"
            >
              <textarea
                required
                maxLength={10000}
                rows={5}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Write an internal team note"
                className="w-full rounded-lg border border-amber-200 bg-amber-50/30 p-3 text-sm"
              />
              <button
                disabled={working}
                className="w-full rounded-lg bg-amber-600 py-2 text-xs font-semibold text-white disabled:opacity-50"
              >
                Add internal note
              </button>
            </form>
          </div>}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="mb-4 font-bold text-slate-900">Ticket timeline</h2>
          <div className="space-y-3">
            {ticket.events?.map(timelineEvent) || <p className="text-sm text-slate-400">No timeline events.</p>}
          </div>
        </div>
      </div>
    </Layout>
  );
};
