let apiToken = null

export function setApiToken(token) {
  apiToken = token
}

export function getApiToken() {
  return apiToken
}

export function getApiAuthorization() {
  return apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined
}
