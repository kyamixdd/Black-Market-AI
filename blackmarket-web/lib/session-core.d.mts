export function createSession(secret: string, nowMs?: number): string;
export function verifySession(value: string | undefined, secret: string, nowMs?: number): boolean;
export function revokeSession(value: string | undefined, secret: string, nowMs?: number): boolean;
export function hashPassword(password: string): string;
export function verifyPassword(password: string, encoded: string): boolean;
