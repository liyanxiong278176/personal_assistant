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
  { value: 'history', label: 'History & Culture' },
  { value: 'food', label: 'Food & Dining' },
  { value: 'nature', label: 'Nature & Scenery' },
  { value: 'shopping', label: 'Shopping' },
  { value: 'art', label: 'Art & Museums' },
  { value: 'entertainment', label: 'Entertainment' },
  { value: 'sports', label: 'Outdoor Sports' },
  { value: 'photography', label: 'Photography' },
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
        <Label htmlFor="budget">Budget Level</Label>
        <Select value={budget} onValueChange={(v) => setBudget(v as any)}>
          <SelectTrigger id="budget">
            <SelectValue placeholder="Select budget level" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="low">Budget (Hostels, Public Transport)</SelectItem>
            <SelectItem value="medium">Comfortable (3-star Hotels, Mixed Transport)</SelectItem>
            <SelectItem value="high">Luxury (5-star Hotels, Private Car)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Travel Style */}
      <div className="space-y-3">
        <Label htmlFor="style">Travel Style</Label>
        <Select value={style} onValueChange={(v) => setStyle(v as any)}>
          <SelectTrigger id="style">
            <SelectValue placeholder="Select travel style" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="relaxed">Relaxed (Fewer attractions, slow pace)</SelectItem>
            <SelectItem value="compact">Compact (Many attractions, efficient)</SelectItem>
            <SelectItem value="adventure">Adventure (New experiences, outdoor activities)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Travelers */}
      <div className="space-y-3">
        <Label htmlFor="travelers">
          Number of Travelers: {travelers}
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
        <Label>Interests (Select all that apply)</Label>
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
          {saving ? 'Saving...' : 'Save Preferences'}
        </Button>
      </div>
    </form>
  );
}
