export function rateLimited(key: string, limit: number, now?: number): boolean;
export function requestClientKey(request: { headers: { get(name: string): string | null } }): string;
