"use client"

import * as React from "react"

export interface SliderProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number[]
  onValueChange?: (value: number[]) => void
  min?: number
  max?: number
  step?: number
  className?: string
  disabled?: boolean
}

export function Slider({
  value = [0],
  onValueChange,
  min = 0,
  max = 100,
  step = 1,
  className = "",
  disabled = false,
}: SliderProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (disabled) return
    const newValue = Number(e.target.value)
    onValueChange?.([newValue])
  }

  const percentage = ((value[0] - min) / (max - min)) * 100

  return (
    <div className={`relative flex w-full touch-none select-none items-center ${className}`}>
      <div className="relative h-2 w-full grow overflow-hidden rounded-full bg-secondary">
        <div
          className="absolute h-full bg-primary"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value[0]}
        onChange={handleChange}
        disabled={disabled}
        className="absolute w-full cursor-pointer opacity-0"
      />
      <div
        className="absolute h-5 w-5 rounded-full border-2 border-primary bg-background ring-offset-background transition-transform"
        style={{ left: `calc(${percentage}% - 10px)` }}
      />
    </div>
  )
}
