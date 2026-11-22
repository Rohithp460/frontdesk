const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i;

export const parseUtcDate = (value: string): Date =>
  new Date(hasTimezone.test(value) ? value : `${value}Z`);
