/**
 * User settings page for preference management.
 *
 * References:
 * - PERS-01: Store user preferences (budget, interests, style, travelers)
 * - D-07: Settings page for explicit preference setting
 */

'use client';

import { useEffect, useState } from 'react';
import { userManager, type UserPreferences } from '@/lib/user-manager';
import PreferenceForm from '@/components/settings/preference-form';

export default function SettingsPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<UserPreferences>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    async function loadUser() {
      try {
        const id = await userManager.initialize();
        setUserId(id);
        setPreferences(userManager.getPreferences());
      } catch (error) {
        console.error('Failed to load user:', error);
        setMessage({ type: 'error', text: '加载用户数据失败' });
      } finally {
        setLoading(false);
      }
    }
    loadUser();
  }, []);

  const handleSavePreferences = async (updates: Partial<UserPreferences>) => {
    setSaving(true);
    setMessage(null);

    try {
      const updated = await userManager.updatePreferences(updates);
      setPreferences(updated);
      setMessage({ type: 'success', text: '偏好保存成功' });
    } catch (error) {
      console.error('Failed to save preferences:', error);
      setMessage({ type: 'error', text: '保存偏好失败' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-muted-foreground">加载中...</div>
      </div>
    );
  }

  return (
    <div className="container max-w-2xl mx-auto py-8 px-4">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">设置</h1>
        <p className="text-muted-foreground">
          管理您的旅行偏好，以获得个性化推荐
        </p>
      </div>

      {message && (
        <div
          className={`mb-6 p-4 rounded-lg ${
            message.type === 'success'
              ? 'bg-green-50 text-green-800 dark:bg-green-900/20 dark:text-green-400'
              : 'bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-400'
          }`}
        >
          {message.text}
        </div>
      )}

      <PreferenceForm
        preferences={preferences}
        onSave={handleSavePreferences}
        saving={saving}
      />
    </div>
  );
}
