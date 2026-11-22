# Business decisions

This file records decisions where the requirements allowed more than one
reasonable interpretation.

## Implemented and intentionally skipped scope

- Implemented scope is the authenticated agent ticket workflow: ticket
  creation/list/detail, ownership claims, customer-visible replies, internal
  notes, priority/status actions, SLA tracking, and an audit timeline.
- Customer portal/authentication, email/WhatsApp notifications, attachments,
  manager dashboards, reports, an admin UI, holiday-management UI, advanced
  search, and bulk actions are intentionally excluded. They are separate
  product/security work and are not prerequisites for the core agent workflow.
- Auto-close and missed-response maintenance are exposed as admin-only manual
  triggers because this application does not include a scheduler. Production
  deployment must schedule those triggers.

## Time and SLA

- Store timestamps as UTC `DATETIME(6)`. A naive value read from MySQL means UTC;
  it is not interpreted as Asia/Kolkata wall time.
- Existing naive timestamps are assumed to already represent UTC; legacy rows
  are not shifted because their historical timezone cannot be inferred safely.
- Convert UTC to Asia/Kolkata before determining business dates or working
  minutes.
- A working day is Monday-Friday, 09:30 inclusive to 18:30 exclusive. An SLA
  expiring exactly at 18:30 is met at that instant; additional working time
  starts at 09:30 on the next working day.
- Weekends and calendar rows marked holiday/non-working consume no working SLA
  time. Holiday rows are maintained by administrators outside this app.
- Existing SLA allowances remain: CRITICAL 120 response / 540 resolution
  working minutes; MEDIUM 270 / 1,620; LOW 540 / 2,700.
- Priority changes consume elapsed working time against the new priority's
  allowance. Customer waits are subtracted before computing remaining
  resolution allowance.
- A priority change recalculates the response deadline only if no first
  customer-visible agent reply exists, and recalculates the remaining
  resolution allowance using the new priority. Waiting intervals are excluded.
- A resolved ticket's direct demo reopen starts a new resolution allowance at
  the current priority. If no first customer-visible reply was ever sent, it
  also starts a new response allowance.
- A response miss is recorded when the response deadline has passed and no
  agent customer-visible first response exists. Ticket reads update the flag;
  production should also schedule the admin SLA-check endpoint.

## Customer wait and lifecycle

- A ticket may have at most one active wait period. Further agent replies while
  already waiting do not create another one.
- A customer reply ends all currently active legacy wait rows, reopens a
  WAITING_CUSTOMER ticket to OPEN, and recalculates the remaining resolution
  deadline.
- Resolve and close may be performed from OPEN or WAITING_CUSTOMER. Leaving
  WAITING_CUSTOMER ends its wait before recalculating the deadline.
- Repeated terminal actions and all other invalid transitions return HTTP 409;
  no duplicate resolution/closure event is written.
- The five-day reopen window means five working days (2,700 working minutes).
  A customer reply within a resolved ticket's window reopens it; a reply after
  that window, or to a closed ticket, creates a new ticket linked through
  `reopened_from_ticket_id`.
- Agent-authenticated `/reopen` is retained only for demonstration. It records
  the actor as AGENT, not CUSTOMER. `/customer-reply` is likewise a demo
  simulation and records the simulated customer as actor.
- Auto-close is a manually invoked admin action after five working days of
  continuous customer wait, measured in 2,700 working minutes while excluding
  weekends and calendar holidays. It records SYSTEM as actor. A production
  scheduler must invoke it.

## Authorization and audit

- Any authenticated active agent may list and view tickets.
- Only the assigned agent or an admin may reply, add internal notes, change
  priority, resolve, close, reopen, or simulate a customer reply.
- Any active agent may claim an unassigned ticket. A race loser receives HTTP
  409. Admins may manage tickets, but claim remains for unassigned tickets.
- Admin maintenance endpoints use the explicit admin dependency.
- Ticket events are immutable through the application ORM and ordered by
  `(occurred_at, id)`. Ticket deletion is restricted while event or wait rows
  exist. Production database credentials should prevent direct audit-table
  updates/deletes because privileged SQL can bypass ORM guards.
- Ticket titles, descriptions, replies, and internal notes are plain text and
  rejected if they contain HTML tags. Internal notes are never included in
  customer-facing timelines.
- JWTs use a randomly generated, process-local development secret when no
  secret is configured; it is not stable across restarts. Production requires
  an explicitly configured strong `JWT_SECRET`. Demo passwords are for local
  development only.

## Identifiers and concurrency

- Public references are sequential `INC-` numbers allocated by a dedicated
  counter row locked in the same transaction as ticket creation. A transaction
  rollback also rolls back the counter increment.
- Ticket mutations lock the ticket row. Customer reply and auto-close use the
  same lock order so only one transition wins the race.

## Known limitations

- No customer authentication, external notifications, scheduler, deployment,
  monitoring, or holiday-management interface is included.
- Holiday calendar records require manual maintenance.
- The repository and live deployment URLs are not available in this workspace;
  documentation labels both as unconfigured rather than inventing URLs.
