/**
 * Client-side user and preference management.
 *
 * References:
 * - D-01, D-02: UUID-based user identification without password
 * - D-03: Cross-device preference sync via user_id
 * - PERS-04: Cross-session preference persistence
 *
 * Uses localStorage for user_id persistence (per D-02).
 */

const USER_ID_KEY = 'travel_assistant_user_id';
const PREFS_KEY = 'travel_assistant_preferences';

export interface UserPreferences {
  budget?: 'low' | 'medium' | 'high';
  interests?: string[];
  style?: 'relaxed' | 'compact' | 'adventure' | '??' | '??' | '??';
  travelers?: number;
}

export interface User {
  id: string;
  preferences?: UserPreferences;
}

class UserManager {
  private userId: string | null = null;
  private preferences: UserPreferences = {};
  private prefsCache: UserPreferences = {};

  /**
   * Initialize user manager.
   * Creates or retrieves user ID from localStorage (per D-02).
   */
  async initialize(): Promise<string> {
    // Check existing user ID in localStorage
    let userId = localStorage.getItem(USER_ID_KEY);

    if (!userId) {
      // Create new user via API (per D-01)
      const response = await fetch('/api/users', {
        method: 'POST',
      });
      const data = await response.json();
      userId = data.id;

      if (userId) {
        // Store in localStorage
        localStorage.setItem(USER_ID_KEY, userId);
      }
    }

    this.userId = userId;
    await this.loadPreferences();

    return userId ?? '';
  }

  /**
   * Get current user ID.
   */
  getUserId(): string {
    if (!this.userId) {
      throw new Error('UserManager not initialized. Call initialize() first.');
    }
    return this.userId;
  }

  /**
   * Get current preferences from cache.
   */
  getPreferences(): UserPreferences {
    return { ...this.prefsCache };
  }

  /**
   * Load preferences from server.
   */
  private async loadPreferences(): Promise<void> {
    if (!this.userId) return;

    try {
      const response = await fetch(`/api/users/${this.userId}/preferences`);
      if (response.ok) {
        const data = await response.json();
        this.preferences = data;
        this.prefsCache = { ...data };
        localStorage.setItem(PREFS_KEY, JSON.stringify(data));
      }
    } catch (error) {
      console.error('Failed to load preferences:', error);
    }
  }

  /**
   * Update preferences on server.
   */
  async updatePreferences(updates: Partial<UserPreferences>): Promise<UserPreferences> {
    if (!this.userId) {
      throw new Error('UserManager not initialized');
    }

    try {
      const response = await fetch(`/api/users/${this.userId}/preferences`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });

      if (!response.ok) {
        throw new Error('Failed to update preferences');
      }

      const data = await response.json();
      this.preferences = data.preferences || data;
      this.prefsCache = { ...this.preferences };
      localStorage.setItem(PREFS_KEY, JSON.stringify(this.preferences));

      return this.preferences;
    } catch (error) {
      console.error('Failed to update preferences:', error);
      throw error;
    }
  }

  /**
   * Extract preferences from conversation and sync.
   */
  async extractFromConversation(conversationText: string): Promise<any> {
    if (!this.userId) {
      throw new Error('UserManager not initialized');
    }

    try {
      const response = await fetch(`/api/users/${this.userId}/preferences/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_text: conversationText,
          auto_confirm: false,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to extract preferences');
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to extract preferences:', error);
      throw error;
    }
  }

  /**
   * Clear local storage (for logout/debug).
   */
  clear(): void {
    localStorage.removeItem(USER_ID_KEY);
    localStorage.removeItem(PREFS_KEY);
    this.userId = null;
    this.preferences = {};
    this.prefsCache = {};
  }
}

// Export singleton instance
export const userManager = new UserManager();
