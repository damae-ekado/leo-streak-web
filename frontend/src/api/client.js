import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 600_000,  // 10분 — 대용량 FITS + plate solving 여유
})

export const uploadFits = (file, onProgress) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
}

export const processFits = (jobId, params = null, apiKey = null) =>
  api.post('/process', { job_id: jobId, params, api_key: apiKey })

export const calibrate = (jobId, x1, y1, x2, y2, binning = 2) =>
  api.post('/calibrate', { job_id: jobId, x1, y1, x2, y2, binning })

export const getResult   = (jobId)   => api.get(`/results/${jobId}`)
export const previewUrl  = (jobId, binning = 2) => `${BASE_URL}/image/${jobId}?binning=${binning}`
export const matchFrames = (jobIds)  => api.post('/match', jobIds)
export const healthCheck = ()        => api.get('/health')