const API_BASE_URL = (process.env.REACT_APP_API_BASE_URL || 'http://localhost:8080').replace(/\/$/, '');

export const apiUrl = (path) => `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;

export const apiFetch = (path, options = {}) => fetch(apiUrl(path), {
  credentials: 'include',
  ...options,
});
