const API_BASE = '/api'

async function handleResponse(res) {
  let data = null
  try {
    data = await res.json()
  } catch {
    // no JSON body
  }
  if (!res.ok) {
    const message = (data && data.detail) || `Request failed (${res.status})`
    throw new Error(message)
  }
  return data
}

export async function analyzeRepo(url, token, forceRefresh = false) {
  const res = await fetch(`${API_BASE}/repos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, token: token ? token : undefined, force_refresh: forceRefresh }),
  })
  return handleResponse(res)
}

export async function refreshRepo(id, token) {
  const res = await fetch(`${API_BASE}/repos/${id}/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: token ? token : undefined }),
  })
  return handleResponse(res)
}

export async function fetchRepos() {
  const res = await fetch(`${API_BASE}/repos`)
  return handleResponse(res)
}

export async function deleteRepo(id) {
  const res = await fetch(`${API_BASE}/repos/${id}`, { method: 'DELETE' })
  return handleResponse(res)
}

export async function fetchRepo(id) {
  const res = await fetch(`${API_BASE}/repos/${id}`)
  return handleResponse(res)
}

export async function fetchSimilarRepos(id, limit = 5) {
  const res = await fetch(`${API_BASE}/repos/${id}/similar?limit=${limit}`)
  return handleResponse(res)
}

export async function fetchAnomalyReport() {
  const res = await fetch(`${API_BASE}/anomalies`)
  return handleResponse(res)
}

export async function toggleFavorite(id) {
  const res = await fetch(`${API_BASE}/repos/${id}/favorite`, { method: 'POST' })
  return handleResponse(res)
}

export async function askAboutRepo(id, question) {
  const res = await fetch(`${API_BASE}/repos/${id}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  return handleResponse(res)
}

export async function rescoreRepo(id) {
  const res = await fetch(`${API_BASE}/repos/${id}/rescore`, { method: 'POST' })
  return handleResponse(res)
}

export async function fetchRepoHistory(id) {
  const res = await fetch(`${API_BASE}/repos/${id}/history`)
  return handleResponse(res)
}

export async function fetchPredictiveRisk(id) {
  const res = await fetch(`${API_BASE}/repos/${id}/predictive-risk`)
  return handleResponse(res)
}
