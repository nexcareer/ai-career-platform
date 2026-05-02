/**
 * NexusHire Authentication Manager
 * Handles login, registration, session validation
 * 
 * SECURITY NOTE: This module uses localStorage for tokens (development).
 * For production, migrate to httpOnly cookies with Secure + SameSite flags.
 */

class AuthManager {
  constructor(apiClient) {
    this.api = apiClient;
    this.user = this.getStoredUser();
    this.checkSessionOnInit();
  }

  /**
   * Retrieve stored user data from localStorage
   */
  getStoredUser() {
    try {
      const user = localStorage.getItem('user');
      return user ? JSON.parse(user) : null;
    } catch (e) {
      console.error('Failed to parse stored user:', e);
      return null;
    }
  }

  /**
   * Check if user is logged in
   */
  isLoggedIn() {
    return !!this.api.getToken() && !!this.user;
  }

  /**
   * Get current user
   */
  getUser() {
    return this.user;
  }

  /**
   * Validate current session on page load
   */
  async checkSessionOnInit() {
    if (!this.api.getToken()) {
      this.redirectToLogin();
      return;
    }

    try {
      this.user = await this.api.getMe();
      localStorage.setItem('user', JSON.stringify(this.user));
    } catch (error) {
      console.error('Session validation failed:', error);
      this.logout();
    }
  }

  /**
   * Handle user registration
   */
  async register(formData) {
    try {
      const response = await this.api.register(
        formData.email,
        formData.password,
        formData.name,
        formData.role
      );
      this.user = response.user;
      return { success: true, data: response };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }

  /**
   * Handle user login
   */
  async login(email, password) {
    try {
      const response = await this.api.login(email, password);
      this.user = response.user;
      return { success: true, data: response };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }

  /**
   * Handle logout
   */
  logout() {
    this.api.logout();
    this.user = null;
    this.redirectToLogin();
  }

  /**
   * Redirect to login page
   */
  redirectToLogin() {
    if (!window.location.pathname.includes('login')) {
      window.location.href = '/login.html';
    }
  }

  /**
   * Redirect to dashboard
   */
  redirectToDashboard() {
    window.location.href = '/dashboard.html';
  }

  /**
   * Check if user has specific role
   */
  hasRole(role) {
    return this.user && this.user.role === role;
  }

  /**
   * Require authentication (redirect to login if not authenticated)
   */
  requireAuth() {
    if (!this.isLoggedIn()) {
      this.redirectToLogin();
      return false;
    }
    return true;
  }
}

/**
 * Form Validation Utilities
 */
const FormValidator = {
  /**
   * Validate email format
   */
  isValidEmail(email) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  },

  /**
   * Validate password strength
   */
  isValidPassword(password) {
    // At least 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special
    const regex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;
    return regex.test(password);
  },

  /**
   * Validate name (at least 2 characters)
   */
  isValidName(name) {
    return name.trim().length >= 2;
  },

  /**
   * Get password strength feedback
   */
  getPasswordFeedback(password) {
    const feedback = [];
    if (password.length < 8) feedback.push('At least 8 characters');
    if (!/[a-z]/.test(password)) feedback.push('Lowercase letter');
    if (!/[A-Z]/.test(password)) feedback.push('Uppercase letter');
    if (!/\d/.test(password)) feedback.push('Number');
    if (!/[@$!%*?&]/.test(password)) feedback.push('Special character');
    return feedback;
  },

  /**
   * Validate registration form
   */
  validateRegister(formData) {
    const errors = {};

    if (!this.isValidName(formData.name)) {
      errors.name = 'Name must be at least 2 characters';
    }

    if (!this.isValidEmail(formData.email)) {
      errors.email = 'Invalid email format';
    }

    if (!this.isValidPassword(formData.password)) {
      const feedback = this.getPasswordFeedback(formData.password);
      errors.password = `Password must have: ${feedback.join(', ')}`;
    }

    if (formData.password !== formData.confirmPassword) {
      errors.confirmPassword = 'Passwords do not match';
    }

    if (!formData.role) {
      errors.role = 'Please select a role';
    }

    return {
      isValid: Object.keys(errors).length === 0,
      errors,
    };
  },

  /**
   * Validate login form
   */
  validateLogin(formData) {
    const errors = {};

    if (!this.isValidEmail(formData.email)) {
      errors.email = 'Invalid email format';
    }

    if (!formData.password || formData.password.length < 6) {
      errors.password = 'Please enter a valid password';
    }

    return {
      isValid: Object.keys(errors).length === 0,
      errors,
    };
  },
};

/**
 * UI Helper Functions
 */
const UIHelper = {
  /**
   * Show error message
   */
  showError(message, containerId = 'error-message') {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML = `<div class="error-alert">${this.escapeHtml(message)}</div>`;
      container.style.display = 'block';
      setTimeout(() => {
        container.style.display = 'none';
      }, 5000);
    }
  },

  /**
   * Show success message
   */
  showSuccess(message, containerId = 'success-message') {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML = `<div class="success-alert">${this.escapeHtml(message)}</div>`;
      container.style.display = 'block';
      setTimeout(() => {
        container.style.display = 'none';
      }, 3000);
    }
  },

  /**
   * Show field validation errors
   */
  showFieldErrors(errors) {
    // Clear previous errors
    document.querySelectorAll('.field-error').forEach((el) => {
      el.remove();
    });

    // Show new errors
    Object.keys(errors).forEach((field) => {
      const input = document.querySelector(`[name="${field}"]`);
      if (input) {
        input.classList.add('error');
        const errorEl = document.createElement('span');
        errorEl.className = 'field-error';
        errorEl.textContent = errors[field];
        input.parentNode.appendChild(errorEl);
      }
    });
  },

  /**
   * Clear field errors
   */
  clearFieldErrors() {
    document.querySelectorAll('input').forEach((input) => {
      input.classList.remove('error');
    });
    document.querySelectorAll('.field-error').forEach((el) => {
      el.remove();
    });
  },

  /**
   * Show loading state
   */
  setLoading(buttonId, isLoading = true) {
    const button = document.getElementById(buttonId);
    if (button) {
      button.disabled = isLoading;
      button.style.opacity = isLoading ? '0.6' : '1';
      button.textContent = isLoading ? 'Loading...' : button.textContent;
    }
  },

  /**
   * Escape HTML to prevent XSS
   */
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  /**
   * Redirect after delay
   */
  redirectAfterDelay(url, delay = 2000) {
    setTimeout(() => {
      window.location.href = url;
    }, delay);
  },
};

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { AuthManager, FormValidator, UIHelper };
}
