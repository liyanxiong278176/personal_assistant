"use client"

import * as React from "react"

export interface CheckboxProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'checked' | 'onChange'> {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  disabled?: boolean
  className?: string
}

export function Checkbox({
  checked = false,
  onCheckedChange,
  disabled = false,
  className = "",
}: CheckboxProps) {
  const handleChange = () => {
    if (disabled) return
    onCheckedChange?.(!checked)
  }

  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={handleChange}
      disabled={disabled}
      className={`peer h-4 w-4 shrink-0 rounded-sm border border-primary ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-primary text-primary-foreground" : "bg-background"
      } ${className}`}
    >
      {checked && (
        <svg
          className="h-4 w-4 text-primary-foreground"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      )}
    </button>
  )
}
