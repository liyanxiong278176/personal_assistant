"use client";

import { useState } from "react";
import { Calendar, Clock, Users, MapPin, ChevronDown, ChevronUp, Sun, Cloud } from "lucide-react";
import type { Itinerary } from "@/lib/types";

interface ChatItineraryProps {
  itinerary: Itinerary;
}

export function ChatItinerary({ itinerary }: ChatItineraryProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const totalDays = itinerary.days?.length || 0;
  const startDate = itinerary.days?.[0]?.date;

  const getWeatherIcon = (condition?: string) => {
    if (!condition) return <Sun className="w-4 h-4 text-amber-500" />;
    if (condition.includes("雨") || condition.includes("rain")) {
      return <Cloud className="w-4 h-4 text-blue-500" />;
    }
    return <Sun className="w-4 h-4 text-amber-500" />;
  };

  return (
    <div className="mt-3 rounded-xl border border-border/50 bg-card overflow-hidden">
      {/* Header */}
      <div
        className="px-4 py-3 bg-gradient-to-r from-blue-500 to-cyan-500 text-white cursor-pointer flex items-center justify-between"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <MapPin className="w-5 h-5" />
          <div>
            <div className="font-semibold">{itinerary.destination}</div>
            {startDate && (
              <div className="text-xs opacity-90">{startDate} · {totalDays}天</div>
            )}
          </div>
        </div>
        {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {itinerary.days?.map((day, idx) => (
            <div key={idx} className="border-l-2 border-blue-500 pl-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-medium text-muted-foreground">{day.date}</span>
                {day.weather && (
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    {getWeatherIcon(day.weather.condition)}
                    <span>{day.weather.temp_max}°/{day.weather.temp_min}°</span>
                  </div>
                )}
              </div>
              <div className="space-y-2">
                {day.activities?.map((activity, actIdx) => (
                  <div key={actIdx} className="text-sm">
                    <span className="font-medium text-blue-600">{activity.time}:</span>{" "}
                    <span>{activity.activity}</span>
                    <span className="text-muted-foreground"> · {activity.location}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
