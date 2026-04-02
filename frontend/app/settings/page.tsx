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
import { Settings, Compass, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function SettingsPage() {
  const [preferences, setPreferences] = useState<UserPreferences>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    async function loadUser() {
      try {
        await userManager.initialize();
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
      setMessage({ type: 'success', text: '偏好设置已保存' });
    } catch (error) {
      console.error('Failed to save preferences:', error);
      setMessage({ type: 'error', text: '保存偏好失败，请稍后重试' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-atmosphere flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-glow animate-pulse">
            <Compass className="w-5 h-5 text-white" />
          </div>
          <p className="text-sm text-muted-foreground">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-atmosphere">
      {/* Decorative background */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px]">
          <div className="absolute inset-0 bg-gradient-radial from-primary/5 via-transparent to-transparent" />
        </div>
      </div>

      <div className="relative max-w-2xl mx-auto px-4 py-10">
        {/* Back link */}
        <Link
          href="/chat"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-8 transition-colors group"
        >
          <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
          返回聊天
        </Link>

        {/* Header Card */}
        <div className="relative mb-10">
          <div className="absolute -inset-1 bg-gradient-to-br from-primary/10 to-accent/10 rounded-3xl blur-xl" />
          <div className="relative bg-card/80 border border-border/50 rounded-2xl p-8 backdrop-blur-md shadow-soft">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-glow">
                <Settings className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="font-display text-3xl font-bold text-gradient-display">
                  旅行偏好设置
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                  优化你的旅行体验，获得更精准的个性化推荐
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Message */}
        {message && (
          <div
            className={`mb-6 p-4 rounded-xl border backdrop-blur-sm animate-slide-in-up ${
              message.type === 'success'
                ? 'bg-emerald-50/80 border-emerald-200/50 text-emerald-700 dark:bg-emerald-900/20 dark:border-emerald-700/30 dark:text-emerald-300'
                : 'bg-red-50/80 border-red-200/50 text-red-700 dark:bg-red-900/20 dark:border-red-700/30 dark:text-red-300'
            }`}
          >
            <div className="flex items-center gap-2">
              {message.type === 'success' ? (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
              )}
              {message.text}
            </div>
          </div>
        )}

        {/* Form Card */}
        <div className="relative">
          <div className="absolute -inset-1 bg-gradient-to-br from-primary/5 to-accent/5 rounded-3xl blur-xl opacity-50" />
          <div className="relative bg-card/80 border border-border/50 rounded-2xl p-8 backdrop-blur-md shadow-soft">
            <PreferenceForm
              preferences={preferences}
              onSave={handleSavePreferences}
              saving={saving}
            />
          </div>
        </div>

        {/* Footer tip */}
        <div className="mt-6 text-center">
          <p className="text-xs text-muted-foreground/60">
            这些设置将帮助 AI 更好地理解你的旅行风格，提供更精准的行程建议
          </p>
        </div>
      </div>
    </div>
  );
}
