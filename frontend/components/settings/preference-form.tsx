/**
 * Preference form component.
 *
 * References:
 * - PERS-01: Budget, interests, style, travelers preferences
 * - D-05: Preference categories
 */

'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
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

interface PreferenceFormProps {
  preferences: UserPreferences;
  onSave: (updates: Partial<UserPreferences>) => Promise<void>;
  saving: boolean;
}

const INTEREST_OPTIONS = [
  { value: 'history', label: '历史文化' },
  { value: 'food', label: '美食体验' },
  { value: 'nature', label: '自然风光' },
  { value: 'shopping', label: '购物' },
  { value: 'art', label: '艺术展览' },
  { value: 'entertainment', label: '娱乐休闲' },
  { value: 'sports', label: '户外运动' },
  { value: 'photography', label: '摄影打卡' },
];

export default function PreferenceForm({ preferences, onSave, saving }: PreferenceFormProps) {
  const [budget, setBudget] = useState<UserPreferences['budget']>(preferences.budget || '');
  const [style, setStyle] = useState<UserPreferences['style']>(preferences.style || '');
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
    if (budget) updates.budget = budget;
    if (style) updates.style = style as any;
    if (travelers !== 1) updates.travelers = travelers;
    if (interests.length > 0) updates.interests = interests;

    await onSave(updates);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* Budget */}
      <div className="space-y-3">
        <Label htmlFor="budget">预算水平</Label>
        <Select value={budget} onValueChange={(v) => setBudget(v as any)}>
          <SelectTrigger id="budget">
            <SelectValue placeholder="选择预算水平" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="low">经济型（青年旅舍、公共交通）</SelectItem>
            <SelectItem value="medium">舒适型（三星酒店、混合交通）</SelectItem>
            <SelectItem value="high">豪华型（五星酒店、专车接送）</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Travel Style */}
      <div className="space-y-3">
        <Label htmlFor="style">旅行风格</Label>
        <Select value={style} onValueChange={(v) => setStyle(v as any)}>
          <SelectTrigger id="style">
            <SelectValue placeholder="选择旅行风格" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="relaxed">悠闲放松（少景点、慢节奏）</SelectItem>
            <SelectItem value="compact">紧凑充实（多景点、高效率）</SelectItem>
            <SelectItem value="adventure">探索冒险（新鲜体验、户外活动）</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Travelers */}
      <div className="space-y-3">
        <Label htmlFor="travelers">
          出行人数：{travelers} 人
        </Label>
        <Slider
          id="travelers"
          min={1}
          max={10}
          step={1}
          value={[travelers]}
          onValueChange={(v) => setTravelers(v[0])}
          className="w-full"
        />
      </div>

      {/* Interests */}
      <div className="space-y-3">
        <Label>兴趣偏好（可多选）</Label>
        <div className="grid grid-cols-2 gap-3">
          {INTEREST_OPTIONS.map(option => (
            <div key={option.value} className="flex items-center space-x-2">
              <Checkbox
                id={`interest-${option.value}`}
                checked={interests.includes(option.value)}
                onCheckedChange={() => handleInterestToggle(option.value)}
              />
              <Label
                htmlFor={`interest-${option.value}`}
                className="cursor-pointer"
              >
                {option.label}
              </Label>
            </div>
          ))}
        </div>
      </div>

      {/* Submit */}
      <div className="flex justify-end">
        <Button type="submit" disabled={saving}>
          {saving ? '保存中...' : '保存偏好'}
        </Button>
      </div>
    </form>
  );
}
