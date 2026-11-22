export type TicketPriority = 'LOW' | 'MEDIUM' | 'CRITICAL';

export type TicketStatus =
  | 'OPEN'
  | 'WAITING_CUSTOMER'
  | 'RESOLVED'
  | 'CLOSED';

export interface Agent {
  id: number;
  name: string;
  email: string;
  role: 'ADMIN' | 'AGENT';
  is_active: boolean;
  created_at: string;
}

export interface CustomerBrief {
  id: number;
  name: string;
  email: string;
}

export interface TicketEvent {
  id: number;
  ticket_id: number;
  actor_type: 'AGENT' | 'CUSTOMER' | 'SYSTEM';
  actor_id?: number | null;
  actor_name?: string | null;
  event_type:
    | 'TICKET_CREATED'
    | 'TICKET_ASSIGNED'
    | 'AGENT_REPLY'
    | 'INTERNAL_NOTE_ADDED'
    | 'CUSTOMER_REPLY'
    | 'STATUS_CHANGED'
    | 'PRIORITY_CHANGED'
    | 'TICKET_RESOLVED'
    | 'TICKET_CLOSED'
    | 'TICKET_REOPENED'
    | 'NEW_TICKET_CREATED_FROM_CLOSED_TICKET'
    | 'AUTO_CLOSED_DUE_TO_CUSTOMER_INACTIVITY'
    | 'SLA_DEADLINE_RECALCULATED';
  payload?: any;
  occurred_at: string;
  created_at: string;
}

export interface Ticket {
  id: number;
  public_ref: string;
  title: string;
  description?: string | null;
  priority: TicketPriority;
  status: TicketStatus;
  customer_id: number;
  assigned_agent_id?: number | null;
  first_response_at?: string | null;
  resolved_at?: string | null;
  closed_at?: string | null;
  response_deadline?: string | null;
  resolution_deadline?: string | null;
  reopened_until?: string | null;
  reopened_from_ticket_id?: number | null;
  response_sla_met?: boolean | null;
  resolution_sla_met?: boolean | null;
  created_at: string;
  updated_at: string;
  customer?: CustomerBrief | null;
  assigned_agent?: { id: number; name: string; email: string } | null;
  events?: TicketEvent[];
  customer_name?: string;
  assigned_agent_name?: string | null;
  is_response_late?: boolean;
  is_resolution_late?: boolean;
  is_waiting_on_customer?: boolean;
  sla_state?: 'ON_TRACK' | 'DUE_SOON' | 'LATE' | 'NOT_APPLICABLE';
}

export interface PaginatedTickets {
  total: number;
  skip: number;
  limit: number;
  items: Ticket[];
}
