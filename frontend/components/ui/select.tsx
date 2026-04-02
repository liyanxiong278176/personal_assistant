"use client"

import * as React from "react"

export interface SelectProps {
  value?: string
  onValueChange?: (value: string) => void
  children: React.ReactNode
}

const SelectContext = React.createContext<{
  value: string
  onValueChange: (value: string) => void
  open: boolean
  setOpen: (open: boolean) => void
}>({
  value: "",
  onValueChange: () => {},
  open: false,
  setOpen: () => {},
})

export function Select({ value = "", onValueChange, children }: SelectProps) {
  const [open, setOpen] = React.useState(false)

  return (
    <SelectContext.Provider value={{ value, onValueChange: onValueChange || (() => {}), open, setOpen }}>
      <div className="relative">{children}</div>
    </SelectContext.Provider>
  )
}

export function SelectTrigger({ className = "", children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen } = React.useContext(SelectContext)

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className={`flex h-10 w-full items-center justify-between rounded-xl border border-border/60 bg-card/60 px-4 py-2 text-sm ring-offset-background placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/30 focus:border-ring/40 disabled:cursor-not-allowed disabled:opacity-50 transition-all ${className}`}
      {...props}
    >
      {children}
      <svg className="h-4 w-4 opacity-50 flex-shrink-0 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    </button>
  )
}

export function SelectValue({ placeholder = "" }: { placeholder?: string }) {
  const { value } = React.useContext(SelectContext)

  return <span className={value ? "text-foreground" : "text-muted-foreground/50"}>{value || placeholder}</span>
}

export function SelectContent({ children }: { children: React.ReactNode }) {
  const { open, setOpen } = React.useContext(SelectContext)
  const ref = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    if (open) {
      document.addEventListener("mousedown", handleClickOutside)
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [open, setOpen])

  if (!open) return null

  return (
    <div
      ref={ref}
      className="absolute z-50 min-w-[8rem] overflow-hidden rounded-xl border border-border/60 bg-card/95 backdrop-blur-md shadow-soft-lg mt-1 animate-scale-in"
    >
      <div className="max-h-72 overflow-auto scrollbar-elegant p-1">{children}</div>
    </div>
  )
}

export function SelectItem({ value, children }: { value: string; children: React.ReactNode }) {
  const { onValueChange, setOpen } = React.useContext(SelectContext)

  return (
    <div
      onClick={() => {
        onValueChange(value)
        setOpen(false)
      }}
      className="relative flex cursor-pointer select-none items-center rounded-lg px-3 py-2.5 text-sm text-foreground/80 outline-none hover:bg-primary/8 hover:text-foreground transition-colors"
    >
      {children}
    </div>
  )
}
