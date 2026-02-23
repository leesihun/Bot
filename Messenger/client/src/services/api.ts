import axios from 'axios';

let baseURL = 'http://10.198.112.203:3000';

export function setServerUrl(url: string) {
  baseURL = url.replace(/\/$/, '');
  api.defaults.baseURL = baseURL;
}

export function getServerUrl() {
  return baseURL;
}

const api = axios.create({
  baseURL,
  timeout: 30000,
});

export default api;
