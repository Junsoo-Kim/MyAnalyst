const API_BASE_URL = (process.env.REACT_APP_API_BASE_URL || 'http://localhost:8080').replace(/\/$/, '');

export const apiUrl = (path) => `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;

// 인증은 HttpOnly 쿠키(access_token, refresh_token)로 한다. 스크립트는 토큰을 볼 수 없고, 브라우저가 붙여 보낸다.
// access token은 짧게(15분) 살기 때문에 401을 받으면 refresh token으로 한 번 갱신하고 원래 요청을 다시 보낸다.
const AUTH_PATHS = ['/sessions', '/auth/', '/users'];

let refreshInFlight = null;

const refreshTokens = () => {
  // 동시에 여러 요청이 401을 받아도 갱신은 한 번만 한다(refresh token은 한 번 쓰면 바뀐다).
  if (!refreshInFlight) {
    refreshInFlight = fetch(apiUrl('/auth/refresh'), { method: 'POST', credentials: 'include' })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
};

export const apiFetch = async (path, options = {}) => {
  const send = () => fetch(apiUrl(path), {
    credentials: 'include',
    ...options,
  });

  const response = await send();
  if (response.status !== 401 || AUTH_PATHS.some((prefix) => path.startsWith(prefix))) {
    return response;
  }
  return (await refreshTokens()) ? send() : response;
};
