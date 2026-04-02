/**
 * Preference form component.
 *
 * References:
 * - PERS-01: Budget, interests, style, travelers preferences
 * - D-05: Preference categories
 */

'use client';

import { useState } from 'react';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Checkbox } from '@/components/ui/checkbox';
import type { UserPreferences } from '@/lib/user-manager';
import { Wallet, Compass, Users, Sparkles, Check } from 'lucide-react';

interface PreferenceFormProps {
  preferences: UserPreferences;
  onSave: (updates: Partial<UserPreferences>) => Promise<void>;
  saving: boolean;
}

const INTEREST_OPTIONS = [
  { value: 'history', label: '历史文化', icon: '🏛️' },
  { value: 'food', label: '美食体验', icon: '🍜' },
  { value: 'nature', label: '自然风光', icon: '🏔️' },
  { value: 'shopping', label: '购物', icon: '🛍️' },
  { value: 'art', label: '艺术展览', icon: '🎨' },
  { value: 'entertainment', label: '娱乐休闲', icon: '🎭' },
  { value: 'sports', label: '户外运动', icon: '⛷️' },
  { value: 'photography', label: '摄影打卡', icon: '📷' },
];

const SECTION_STYLES = [
  { value: 'relaxed', label: '悠闲放松', desc: '少景点、慢节奏', icon: '☕' },
  { value: 'compact', label: '紧凑充实', desc: '多景点、高效率', icon: '⚡' },
  { value: 'adventure', label: '探索冒险', desc: '新鲜体验、户外活动', icon: '🧭' },
];

export default function PreferenceForm({ preferences, onSave, saving }: PreferenceFormProps) {
  const [budget, setBudget] = useState<string>(preferences.budget || '');
  const [style, setStyle] = useState<string>(preferences.style || '');
  const [travelers, setTravelers] = useState(preferences.travelers || 1);
  const [interests, setInterests] = useState<string[]>(preferences.interests || []);

  const handleInterestToggle = (value: string) => {
    setInterests(prev =>
      prev.includes(value) ? prev.filter(i => i !== value) : [...prev, value]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const updates: Partial<UserPreferences> = {};
    if (budget) updates.budget = budget as 'low' | 'medium' | 'high';
    if (style) updates.style = style as 'relaxed' | 'compact' | 'adventure';
    if (travelers !== 1) updates.travelers = travelers;
    if (interests.length > 0) updates.interests = interests;

    await onSave(updates);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* Budget */}
      <div className="space-y-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center">
            <Wallet className="w-4 h-4 text-primary" />
          </div>
          <Label htmlFor="budget" className="text-sm font-semibold text-foreground">预算水平</Label>
        </div>
        <Select value={budget} onValueChange={(v) => setBudget(v as any)}>
          <SelectTrigger id="budget" className="h-11 bg-card/60 border-border/60 rounded-xl focus:ring-primary/30">
            <SelectValue placeholder="选择你的预算水平" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="low">
              <div className="flex items-center gap-2">
                <span>💰</span>
                <span>经济型（青年旅舍、公共交通）</span>
              </div>
            </SelectItem>
            <SelectItem value="medium">
              <div className="flex items-center gap-2">
                <span>💵</span>
                <span>舒适型（三星酒店、混合交通）</span>
              </div>
            </SelectItem>
            <SelectItem value="high">
              <div className="flex items-center gap-2">
                <span>💎</span>
                <span>豪华型（五星酒店、专车接送）</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Travel Style */}
      <div className="space-y-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center">
            <Compass className="w-4 h-4 text-primary" />
          </div>
          <Label htmlFor="style" className="text-sm font-semibold text-foreground">旅行风格</Label>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {SECTION_STYLES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setStyle(option.value)}
              className={`
                relative p-3.5 rounded-xl border text-left transition-all
                ${style === option.value
                  ? "bg-gradient-to-br from-primary/10 to-accent/5 border-primary/30 shadow-soft"
                  : "bg-card/40 border-border/40 hover:border-border/60 hover:bg-card/60"
                }
              `}
            >
              {style === option.value && (
                <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                  <Check className="w-3 h-3 text-white" />
                </div>
              )}
              <div className="text-xl mb-1.5">{option.icon}</div>
              <div className="text-sm font-medium text-foreground">{option.label}</div>
              <div className="text-[11px] text-muted-foreground mt-0.5 leading-tight">{option.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Travelers */}
      <div className="space-y-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center">
            <Users className="w-4 h-4 text-primary" />
          </div>
          <Label htmlFor="travelers" className="text-sm font-semibold text-foreground">
            出行人数
          </Label>
          <span className="ml-auto text-sm font-semibold text-gradient-warm">
            {travelers} {travelers === 1 ? '人' : '人'}
          </span>
        </div>
        <div className="px-2">
          <Slider
            id="travelers"
            min={1}
            max={10}
            step={1}
            value={[travelers]}
            onValueChange={(v) => setTravelers(v[0])}
            className="w-full"
          />
          <div className="flex justify-between mt-1 text-[11px] text-muted-foreground/60">
            <span>1人</span>
            <span>10人</span>
          </div>
        </div>
      </div>

      {/* Interests */}
      <div className="space-y-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
          <Label className="text-sm font-semibold text-foreground">兴趣偏好</Label>
          {interests.length > 0 && (
            <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-accent/10 text-accent font-medium">
              已选 {interests.length}
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {INTEREST_OPTIONS.map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => handleInterestToggle(option.value)}
              className={`
                flex items-center gap-3 px-4 py-3 rounded-xl border transition-all text-left
                ${interests.includes(option.value)
                  ? "bg-gradient-to-r from-primary/10 to-accent/5 border-primary/30"
                  : "bg-card/40 border-border/40 hover:border-border/60 hover:bg-card/60"
                }
              `}
            >
              <span className="text-lg">{option.icon}</span>
              <span className={`text-sm flex-1 ${interests.includes(option.value) ? "font-medium text-foreground" : "text-foreground/70"}`}>
                {option.label}
              </span>
              {interests.includes(option.value) && (
                <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                  <Check className="w-3 h-3 text-white" />
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Submit */}
      <div className="flex justify-end pt-2">
        <button
          type="submit"
          disabled={saving || (!budget && !style && interests.length === 0 && travelers === 1)}
          className={`
            px-8 py-3 rounded-xl font-semibold text-sm transition-all
            ${saving
              ? "bg-muted/60 text-muted-foreground cursor-not-allowed"
              : (budget || style || interests.length > 0 || travelers !== 1)
                ? "bg-gradient-to-r from-primary to-[hsl(220,38%,32%)] text-white shadow-glow-primary hover:shadow-glow active:scale-[0.98]"
                : "bg-muted/60 text-muted-foreground cursor-not-allowed"
            }
          `}
        >
          {saving ? (
            <span className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
              保存中...
            </span>
          ) : '保存偏好设置'}
        </button>
      </div>
    </form>
  );
}
