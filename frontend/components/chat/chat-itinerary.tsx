"use client";

import { useState } from "react";
import { Calendar, Clock, Users, MapPin, ChevronDown, ChevronUp, Sun, Cloud, Download, Lightbulb, Info } from "lucide-react";
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
          {/* Overview */}
          {itinerary.overview && (
            <div className="bg-muted/50 rounded-lg p-3 text-sm">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                <span>{itinerary.overview}</span>
              </div>
            </div>
          )}

          {/* Tips */}
          {itinerary.tips && itinerary.tips.length > 0 && (
            <div className="bg-amber-50 dark:bg-amber-950/20 rounded-lg p-3 text-sm">
              <div className="flex items-center gap-2 mb-2 font-medium text-amber-700 dark:text-amber-300">
                <Lightbulb className="w-4 h-4" />
                <span>实用提示</span>
              </div>
              <ul className="space-y-1 ml-6">
                {itinerary.tips.map((tip, idx) => (
                  <li key={idx} className="text-amber-600 dark:text-amber-400 text-xs">
                    • {tip}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Days */}
          {itinerary.days?.map((day, idx) => (
            <div key={idx} className="border-l-2 border-blue-500 pl-4">
              {/* Date header with theme */}
              <div className="mb-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-muted-foreground">{day.date}</span>
                  {day.weather && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      {getWeatherIcon(day.weather.condition)}
                      <span>{day.weather.temp_max}°/{day.weather.temp_min}°</span>
                    </div>
                  )}
                </div>
                {day.theme && (
                  <div className="text-sm font-semibold text-blue-600">{day.theme}</div>
                )}
                {day.summary && (
                  <div className="text-xs text-muted-foreground">{day.summary}</div>
                )}
              </div>

              {/* Activities */}
              <div className="space-y-3">
                {day.activities?.map((activity, actIdx) => (
                  <div key={actIdx} className="bg-muted/30 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-3 h-3 text-muted-foreground" />
                      <span className="text-xs font-medium text-blue-600">{activity.time}</span>
                      {activity.period && (
                        <span className="text-xs text-muted-foreground">· {activity.period}</span>
                      )}
                    </div>
                    <div className="font-medium text-sm">{activity.activity}</div>
                    <div className="text-xs text-muted-foreground mb-1">📍 {activity.location}</div>
                    {activity.description && (
                      <div className="text-xs text-muted-foreground leading-relaxed">{activity.description}</div>
                    )}
                    <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                      <span>⏱ {activity.duration}</span>
                      <span>💰 {activity.cost}</span>
                    </div>
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
