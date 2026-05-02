/**
 * NexusHire API Client
 * Handles all HTTP communication with backend
 * 
 * SECURITY: This client is ready but frontend needs:
 * 1. Move tokens from localStorage to httpOnly cookies (backend must set via Set-Cookie header)
 * 2. Implement CSRF protection
 * 3. Add request/response interceptors for auth
 */

class APIClient {
  constructor(baseURL = 'http://localhost:8000') {
    this.baseURL = baseURL;
    this.token = this.getToken();
  }

  /**
   * Get stored JWT token
   * TODO: Switch to httpOnly cookies when backend implements Set-Cookie headers
   */
  getToken() {
    return localStorage.getItem('token');
  }

  /**
   * Store JWT token
   * TODO: Remove when using httpOnly cookies
   */
  setToken(token) {
    localStorage.setItem('token', token);
    this.token = token;
  }

  /**
   * Clear authentication
   */
  clearToken() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    this.token = null;
  }

  /**
   * Make authenticated request
   */
  async request(method, endpoint, data = null, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    // Add authorization header if token exists
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const config = {
      method,
      headers,
      ...options,
    };

    if (data && (method === 'POST' || method === 'PUT')) {
      config.body = JSON.stringify(data);
    }

    try {
      const response = await fetch(`${this.baseURL}${endpoint}`, config);

      // Handle 401 - token expired
      if (response.status === 401) {
        this.clearToken();
        window.location.href = '/login.html';
        throw new Error('Session expired');
      }

      const json = await response.json();

      if (!response.ok) {
        throw new Error(json.detail || `HTTP ${response.status}`);
      }

      return json;
    } catch (error) {
      console.error(`API Error [${method} ${endpoint}]:`, error);
      throw error;
    }
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Authentication
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  async register(email, password, name, role) {
    const response = await this.request('POST', '/auth/register', {
      email,
      password,
      name,
      role,
    });
    this.setToken(response.access_token);
    localStorage.setItem('user', JSON.stringify(response.user));
    return response;
  }

  async login(email, password) {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    const response = await fetch(`${this.baseURL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();
    this.setToken(data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    return data;
  }

  async getMe() {
    return this.request('GET', '/auth/me');
  }

  logout() {
    this.clearToken();
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Jobs
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  async searchJobs(query, area = 160, perPage = 10) {
    return this.request('GET', `/jobs/search?query=${encodeURIComponent(query)}&area=${area}&per_page=${perPage}`);
  }

  async searchLocalJobs(query, limit = 20) {
    return this.request('GET', `/jobs/dataset?query=${encodeURIComponent(query)}&limit=${limit}`);
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // CV/Transcripts
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  async uploadCV(file) {
    const formData = new FormData();
    formData.append('file', file);

    const config = {
      headers: {},
    };
    if (this.token) {
      config.headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseURL}/cv/upload`, {
      method: 'POST',
      headers: config.headers,
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Upload failed');
    }

    return response.json();
  }

  async getCVHistory() {
    return this.request('GET', '/cv/history');
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Analytics
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  async getDashboard() {
    return this.request('GET', '/analytics/dashboard');
  }

  async getMarketSkills(query) {
    return this.request('GET', `/analytics/market-skills?query=${encodeURIComponent(query)}`);
  }

  async getDatasetStats() {
    return this.request('GET', '/analytics/dataset-stats');
  }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = APIClient;
}
