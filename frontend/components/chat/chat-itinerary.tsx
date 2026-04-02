"use client";

import { useState } from "react";
import { Calendar, Clock, Users, MapPin, ChevronDown, ChevronUp, Sun, Cloud, Download, Lightbulb, Info, Plane, Utensils, Camera, Mountain } from "lucide-react";
import type { Itinerary } from "@/lib/types";
import { exportItinerary } from "@/lib/pdf-generator";

interface ChatItineraryProps {
  itinerary: Itinerary;
}

const ACTIVITY_ICONS: Record<string, React.ReactNode> = {
  "美食": <Utensils className="w-3.5 h-3.5" />,
  "景点": <Camera className="w-3.5 h-3.5" />,
  "自然": <Mountain className="w-3.5 h-3.5" />,
  "活动": <Plane className="w-3.5 h-3.5" />,
  "默认": <MapPin className="w-3.5 h-3.5" />,
};

const getActivityIcon = (activity: string) => {
  const lower = activity.toLowerCase();
  if (lower.includes("美食") || lower.includes("餐厅") || lower.includes("吃")) return ACTIVITY_ICONS["美食"];
  if (lower.includes("景点") || lower.includes("参观") || lower.includes("游览")) return ACTIVITY_ICONS["景点"];
  if (lower.includes("自然") || lower.includes("公园") || lower.includes("山")) return ACTIVITY_ICONS["自然"];
  if (lower.includes("活动") || lower.includes("体验")) return ACTIVITY_ICONS["活动"];
  return ACTIVITY_ICONS["默认"];
};

const getWeatherIcon = (condition?: string) => {
  if (!condition) return <Sun className="w-3.5 h-3.5 text-amber-500" />;
  if (condition.includes("雨") || condition.includes("雪") || condition.includes("cloud")) {
    return <Cloud className="w-3.5 h-3.5 text-blue-500" />;
  }
  return <Sun className="w-3.5 h-3.5 text-amber-500" />;
};

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

  return (
    <div className="mt-4 rounded-2xl overflow-hidden border border-border/40 bg-card/80 backdrop-blur-md shadow-soft-lg animate-slide-in-up">
      {/* Card Header */}
      <div
        className="px-5 py-4 gradient-twilight-header flex items-center justify-between cursor-pointer select-none"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-4">
          {/* Destination Pin */}
          <div className="w-10 h-10 rounded-xl bg-white/15 backdrop-blur-sm flex items-center justify-center">
            <MapPin className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-display text-xl font-semibold text-white">
              {itinerary.destination}
            </div>
            {startDate && (
              <div className="flex items-center gap-2 mt-0.5">
                <Calendar className="w-3 h-3 text-white/70" />
                <span className="text-xs text-white/80">{startDate}</span>
                <span className="text-white/50">·</span>
                <span className="text-xs text-white/80">{totalDays} 天行程</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Export Button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleExportPDF();
            }}
            disabled={isExporting}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 backdrop-blur-sm transition-all disabled:opacity-50"
            title="导出PDF"
          >
            {isExporting ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Download className="w-4 h-4 text-white" />
            )}
          </button>

          {/* Expand/Collapse */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 backdrop-blur-sm transition-all"
          >
            {isExpanded ? (
              <ChevronUp className="w-4 h-4 text-white" />
            ) : (
              <ChevronDown className="w-4 h-4 text-white" />
            )}
          </button>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="p-5 space-y-5">
          {/* Overview */}
          {itinerary.overview && (
            <div className="bg-muted/40 rounded-xl p-4 border border-border/30">
              <div className="flex items-start gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-blue-500/10 flex items-center justify-center mt-0.5 flex-shrink-0">
                  <Info className="w-3.5 h-3.5 text-blue-500" />
                </div>
                <p className="text-sm text-foreground/80 leading-relaxed">{itinerary.overview}</p>
              </div>
            </div>
          )}

          {/* Tips */}
          {itinerary.tips && itinerary.tips.length > 0 && (
            <div className="bg-amber-50/60 dark:bg-amber-900/10 rounded-xl p-4 border border-amber-200/30 dark:border-amber-700/20">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-6 h-6 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                  <Lightbulb className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                </div>
                <span className="text-sm font-semibold text-amber-700 dark:text-amber-300">实用提示</span>
              </div>
              <ul className="space-y-2 ml-2">
                {itinerary.tips.map((tip, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-amber-600/80 dark:text-amber-400/80">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-400/60 flex-shrink-0" />
                    {tip}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Days */}
          <div className="space-y-4">
            {itinerary.days?.map((day, idx) => (
              <div key={idx} className="relative">
                {/* Timeline line */}
                {idx < (itinerary.days?.length ?? 0) - 1 && (
                  <div className="absolute left-[23px] top-12 bottom-0 w-px bg-gradient-to-b from-primary/30 to-transparent" />
                )}

                {/* Day Card */}
                <div className="relative flex gap-4">
                  {/* Timeline dot */}
                  <div className="flex-shrink-0 w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-sm">
                    <span className="text-xs font-bold text-white">
                      {idx + 1}
                    </span>
                  </div>

                  <div className="flex-1 bg-card/60 rounded-xl border border-border/40 p-4">
                    {/* Date header */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
                        <span className="text-sm font-medium text-foreground/80">{day.date}</span>
                        {day.weather && (
                          <div className="flex items-center gap-1 ml-1">
                            {getWeatherIcon(day.weather.condition)}
                            <span className="text-xs text-muted-foreground">
                              {day.weather.temp_max}°/{day.weather.temp_min}°
                            </span>
                          </div>
                        )}
                      </div>
                      {day.theme && (
                        <span className="text-xs px-2.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                          {day.theme}
                        </span>
                      )}
                    </div>

                    {day.summary && (
                      <p className="text-xs text-muted-foreground mb-3 leading-relaxed">{day.summary}</p>
                    )}

                    {/* Activities */}
                    <div className="space-y-2.5">
                      {day.activities?.map((activity, actIdx) => (
                        <div
                          key={actIdx}
                          className="flex items-start gap-3 p-3 rounded-lg bg-muted/30 border border-border/20 hover:bg-muted/50 transition-colors"
                        >
                          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center mt-0.5 flex-shrink-0 text-primary">
                            {getActivityIcon(activity.activity)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <Clock className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                              <span className="text-xs font-semibold text-primary">{activity.time}</span>
                              {activity.period && (
                                <span className="text-xs text-muted-foreground">· {activity.period}</span>
                              )}
                            </div>
                            <div className="font-medium text-sm text-foreground">{activity.activity}</div>
                            <div className="flex items-center gap-1 mt-0.5 text-xs text-muted-foreground">
                              <MapPin className="w-3 h-3 flex-shrink-0" />
                              <span className="truncate">{activity.location}</span>
                            </div>
                            {activity.description && (
                              <p className="text-xs text-muted-foreground/80 mt-1.5 leading-relaxed line-clamp-2">
                                {activity.description}
                              </p>
                            )}
                            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                              {activity.duration && (
                                <span className="flex items-center gap-1">
                                  <Clock className="w-3 h-3" />
                                  {activity.duration}
                                </span>
                              )}
                              {activity.cost && (
                                <span className="flex items-center gap-1">
                                  <span className="text-accent">¥</span>
                                  {activity.cost}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
