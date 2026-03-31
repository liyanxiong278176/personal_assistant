"use client";

import { useState } from "react";
import { Calendar, Clock, Users, MapPin, ChevronDown, ChevronUp, Sun, Cloud, Download } from "lucide-react";
import type { Itinerary } from "@/lib/types";
import { exportItinerary } from "@/lib/pdf-generator";

interface ChatItineraryProps {
  itinerary: Itinerary;
}

export function ChatItinerary({ itinerary }: ChatItineraryProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const totalDays = itinerary.days?.length || 0;
  const startDate = itinerary.days?.[0]?.date;

  const handleExportPDF = async () => {
    setIsExporting(true);
    try {
      await exportItinerary(itinerary);
    } catch (error) {
      console.error("Failed to export PDF:", error);
      alert("导出PDF失败，请稍后重试");
    } finally {
      setIsExporting(false);
    }
  };

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
        className="px-4 py-3 bg-gradient-to-r from-blue-500 to-cyan-500 text-white flex items-center justify-between"
      >
        <div
          className="flex items-center gap-3 flex-1 cursor-pointer"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <MapPin className="w-5 h-5" />
          <div>
            <div className="font-semibold">{itinerary.destination}</div>
            {startDate && (
              <div className="text-xs opacity-90">{startDate} · {totalDays}天</div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleExportPDF();
            }}
            disabled={isExporting}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-50"
            title="导出PDF"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="p-1 hover:bg-white/20 rounded-lg transition-colors"
          >
            {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </button>
        </div>
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
