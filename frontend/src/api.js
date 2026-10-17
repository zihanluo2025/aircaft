// Thin wrapper around fetch for the Turnaround API. All paths live under /api.

const TOKEN_KEY = 'turnaround.token'
let onUnauthorized = () => {}

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function messageFrom(data) {
  if (!data || !data.detail) return ''
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join('; ')
  return ''
}

async function request(method, path, { params, body, form } = {}) {
  const query = params
    ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null)).toString()
    : ''
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  // form (FormData, for a file upload) sets its own multipart Content-Type with boundary; a plain
  // body is sent as JSON.
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response
  try {
    response = await fetch(`/api${path}${query ? `?${query}` : ''}`, {
      method,
      headers,
      body: form !== undefined ? form : body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw Object.assign(new Error('Cannot reach the server. Check your connection.'), { status: 0 })
  }

  if (response.status === 204) return null
  let data = null
  try {
    data = await response.json()
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') onUnauthorized()
    throw Object.assign(new Error(messageFrom(data) || `Request failed (${response.status})`), {
      status: response.status,
    })
  }
  return data
}

const get = (path, params) => request('GET', path, { params })
const post = (path, body, params) => request('POST', path, { body, params })
const patch = (path, body, params) => request('PATCH', path, { body, params })
const put = (path, body, params) => request('PUT', path, { body, params })
const del = (path) => request('DELETE', path)
const postFile = (path, form) => request('POST', path, { form })

/** For file downloads (the response isn't JSON) -- same auth header as everything else, but
 * returns the raw blob and the filename the server suggested, instead of parsing a body. */
async function getBlob(path, params) {
  const query = params
    ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null)).toString()
    : ''
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let response
  try {
    response = await fetch(`/api${path}${query ? `?${query}` : ''}`, { headers })
  } catch {
    throw Object.assign(new Error('Cannot reach the server. Check your connection.'), { status: 0 })
  }
  if (!response.ok) {
    if (response.status === 401) onUnauthorized()
    throw Object.assign(new Error(`Could not export (${response.status})`), { status: response.status })
  }
  const filename = /filename="?([^"]+)"?/.exec(response.headers.get('Content-Disposition') || '')?.[1]
  return { blob: await response.blob(), filename }
}
function fileForm(shift, file) {
  const form = new FormData()
  form.append('shift', shift)
  form.append('file', file)
  return form
}

export const api = {
  login: (username, password) => post('/auth/login', { username, password }),
  me: () => get('/auth/me'),
  staff: {
    list: (team) => get('/staff', { team }),
    create: (body) => post('/staff', body),
    patch: (id, body) => patch(`/staff/${id}`, body),
    remove: (id) => del(`/staff/${id}`),
  },
  roster: {
    get: (date, shift) => get('/roster', { date, shift }),
    patch: (staffId, date, shift, body) => patch(`/roster/${staffId}`, body, { date, shift }),
    importPreview: (shift, text) => post('/roster/import/preview', { shift, text }),
    importApply: (shift, text) => post('/roster/import', { shift, text }),
    importPreviewFile: (shift, file) => postFile('/roster/import/preview/file', fileForm(shift, file)),
    importApplyFile: (shift, file) => postFile('/roster/import/file', fileForm(shift, file)),
  },
  flights: {
    list: (date, shift) => get('/flights', { date, shift }),
    get: (id) => get(`/flights/${id}`),
    patch: (id, body) => patch(`/flights/${id}`, body),
    remove: (id) => del(`/flights/${id}`),
    setAssignments: (id, rows) => put(`/flights/${id}/assignments`, rows),
    start: (id) => post(`/flights/${id}/start`),
    finish: (id) => post(`/flights/${id}/finish`),
    reopen: (id) => post(`/flights/${id}/reopen`),
    setTimes: (id, body) => patch(`/flights/${id}/times`, body),
    sign: (id, name, image) => put(`/flights/${id}/signature`, { name, image }),
    unsign: (id) => del(`/flights/${id}/signature`),
    photos: {
      list: (flightId) => get(`/flights/${flightId}/photos`),
      add: (flightId, body) => post(`/flights/${flightId}/photos`, body),
      rename: (flightId, photoId, name) => patch(`/flights/${flightId}/photos/${photoId}`, { name }),
      remove: (flightId, photoId) => del(`/flights/${flightId}/photos/${photoId}`),
    },
  },
  flightData: {
    status: () => get('/flight-data/status'),
    sync: (date, shift) => post('/flight-data/sync', { date, shift }),
  },
  report: (date, shift) => get('/report', { date, shift }),
  reportExport: (date, shift) => getBlob('/report/export', { date, shift }),
}
