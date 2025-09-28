export function formatTimestamp(value: string | null): string {
  if (!value) {
    return '--';
  }
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
}
