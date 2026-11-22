import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/client';
import { Layout } from '../components/Layout';
import { parseUtcDate } from '../utils/datetime';
import {
  PaginatedTickets,
  Ticket,
  TicketPriority,
  TicketStatus,
} from '../types';

type Filter = 'all' | 'mine' | 'unassigned' | 'waiting' | 'late';

export const TicketListPage: React.FC = () => {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [filter, setFilter] = useState<Filter>('all');
  const [priority, setPriority] = useState<TicketPriority | ''>('');
  const [status, setStatus] = useState<TicketStatus | ''>('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [createError, setCreateError] = useState('');
  const [creating, setCreating] = useState(false);
  const [customerId, setCustomerId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [newPriority, setNewPriority] = useState<TicketPriority>('MEDIUM');

  const fetchTickets = async () => {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, string | boolean> = {};
      if (filter === 'mine') params.mine = true;
      if (filter === 'unassigned') params.unassigned = true;
      if (filter === 'waiting') params.waiting_on_customer = true;
      if (filter === 'late') params.late = true;
      if (priority) params.priority = priority;
      if (status) params.status = status;
      if (search.trim()) params.search = search.trim();
      const response = await api.get<PaginatedTickets>('/tickets', { params });
      setTickets(response.data.items);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tickets');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTickets();
  }, [filter, priority, status]);

  const deadline = (value?: string | null) =>
    value
      ? parseUtcDate(value).toLocaleString('en-IN', {
          timeZone: 'Asia/Kolkata',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        })
      : '—';

  const priorityBadge = (value: TicketPriority) => {
    const classes =
      value === 'CRITICAL'
        ? 'bg-red-100 text-red-800'
        : value === 'MEDIUM'
          ? 'bg-amber-100 text-amber-800'
          : 'bg-slate-100 text-slate-700';
    return (
      <span className={`rounded-full px-2 py-1 text-xs font-bold ${classes}`}>
        {value}
      </span>
    );
  };

  const statusBadge = (value: TicketStatus) => {
    const classes =
      value === 'OPEN'
        ? 'border-blue-200 bg-blue-50 text-blue-700'
        : value === 'WAITING_CUSTOMER'
          ? 'border-purple-200 bg-purple-50 text-purple-700'
          : value === 'RESOLVED'
            ? 'border-green-200 bg-green-50 text-green-700'
            : 'border-slate-200 bg-slate-100 text-slate-600';
    return (
      <span className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${classes}`}>
        {value === 'WAITING_CUSTOMER' ? 'Waiting on customer' : value}
      </span>
    );
  };

  const submitCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setCreating(true);
    setCreateError('');
    try {
      await api.post('/tickets', {
        customer_id: Number(customerId),
        title,
        description,
        priority: newPriority,
      });
      setShowCreate(false);
      setCustomerId('');
      setTitle('');
      setDescription('');
      setNewPriority('MEDIUM');
      await fetchTickets();
    } catch (err: any) {
      const statusCode = err.response?.status;
      const detail = err.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('; ')
        : detail;
      setCreateError(
        statusCode === 409
          ? message || 'The ticket conflicts with an existing update.'
          : message || 'Ticket creation failed. Check the customer ID and required fields.',
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Support Tickets</h1>
              <p className="text-sm text-slate-500">Monitor ownership, deadlines, and customer waits.</p>
            </div>
            <button
              onClick={() => {
                setCreateError('');
                setShowCreate(true);
              }}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
            >
              Create ticket
            </button>
          </div>
        </div>

        {showCreate && (
          <div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/40 p-4">
            <form
              onSubmit={submitCreate}
              className="w-full max-w-xl space-y-4 rounded-2xl bg-white p-6 shadow-xl"
            >
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-slate-900">Create ticket</h2>
                <button type="button" onClick={() => setShowCreate(false)} className="text-slate-500">
                  Close
                </button>
              </div>
              {createError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{createError}</p>}
              <label className="block text-sm font-medium text-slate-700">
                Customer ID
                <input
                  required
                  type="number"
                  min="1"
                  value={customerId}
                  onChange={(event) => setCustomerId(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 p-2"
                />
              </label>
              <label className="block text-sm font-medium text-slate-700">
                Title
                <input
                  required
                  maxLength={255}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 p-2"
                />
              </label>
              <label className="block text-sm font-medium text-slate-700">
                Description
                <textarea
                  required
                  maxLength={10000}
                  rows={5}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 p-2"
                />
              </label>
              <label className="block text-sm font-medium text-slate-700">
                Priority
                <select
                  value={newPriority}
                  onChange={(event) => setNewPriority(event.target.value as TicketPriority)}
                  className="mt-1 w-full rounded-lg border border-slate-200 p-2"
                >
                  <option value="CRITICAL">Critical</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="LOW">Low</option>
                </select>
              </label>
              <button
                type="submit"
                disabled={creating}
                className="w-full rounded-lg bg-blue-600 py-2 font-semibold text-white disabled:opacity-50"
              >
                {creating ? 'Creating…' : 'Create ticket'}
              </button>
            </form>
          </div>
        )}

        <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-3">
          {(['all', 'mine', 'unassigned', 'waiting', 'late'] as Filter[]).map((value) => (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={`rounded-lg px-3 py-2 text-sm font-semibold ${
                filter === value ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {value === 'waiting'
                ? 'Waiting on customer'
                : value === 'late'
                  ? 'Late'
                  : value === 'mine'
                    ? 'My tickets'
                    : value[0].toUpperCase() + value.slice(1)}
            </button>
          ))}

          <select
            value={priority}
            onChange={(event) => setPriority(event.target.value as TicketPriority | '')}
            className="ml-auto rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="">All priorities</option>
            <option value="CRITICAL">Critical</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as TicketStatus | '')}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="WAITING_CUSTOMER">Waiting on customer</option>
            <option value="RESOLVED">Resolved</option>
            <option value="CLOSED">Closed</option>
          </select>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              fetchTickets();
            }}
            className="flex"
          >
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search title or ref"
              className="rounded-l-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <button className="rounded-r-lg bg-slate-800 px-3 py-2 text-sm font-semibold text-white">
              Search
            </button>
          </form>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          {loading ? (
            <div className="p-8 text-center text-slate-500">Loading tickets...</div>
          ) : error ? (
            <div className="p-8 text-center text-red-600">{error}</div>
          ) : tickets.length === 0 ? (
            <div className="p-8 text-center text-slate-500">No tickets found.</div>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-600">
                <tr>
                  <th className="px-4 py-3">Ref</th>
                  <th className="px-4 py-3">Title / Customer</th>
                  <th className="px-4 py-3">Priority</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Assigned</th>
                  <th className="px-4 py-3">Response</th>
                  <th className="px-4 py-3">Resolution</th>
                  <th className="px-4 py-3 text-right">SLA</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {tickets.map((ticket) => (
                  <tr key={ticket.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-bold text-blue-600">
                      <Link to={`/tickets/${ticket.id}`}>{ticket.public_ref}</Link>
                    </td>
                    <td className="px-4 py-3">
                      <Link to={`/tickets/${ticket.id}`} className="font-semibold text-slate-800 hover:underline">
                        {ticket.title}
                      </Link>
                      <div className="mt-1 text-xs text-slate-500">
                        {(ticket as Ticket & { customer_name?: string }).customer_name || 'Customer'}
                      </div>
                    </td>
                    <td className="px-4 py-3">{priorityBadge(ticket.priority)}</td>
                    <td className="px-4 py-3">{statusBadge(ticket.status)}</td>
                    <td className="px-4 py-3 text-slate-600">
                      {ticket.assigned_agent_name || ticket.assigned_agent?.name || 'Unassigned'}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">{deadline(ticket.response_deadline)}</td>
                    <td className="px-4 py-3 text-xs text-slate-600">{deadline(ticket.resolution_deadline)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        {ticket.is_response_late || ticket.is_resolution_late ? (
                          <span className="rounded-full bg-red-600 px-2 py-1 text-xs font-bold text-white">LATE</span>
                        ) : (
                          <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">On track</span>
                        )}
                        {ticket.is_waiting_on_customer && (
                          <span className="rounded-full bg-purple-100 px-2 py-1 text-xs font-bold text-purple-700">WAITING</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </Layout>
  );
};
