let apiToken: string | null = null

export function setApiToken(token: string | null) {
  apiToken = token
}

export function getApiToken(): string | null {
  return apiToken
}

export function getApiAuthorization(): Record<string, string> | undefined {
  return apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined
}
