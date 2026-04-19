// frontend/components/monitor/ui/loading-card.tsx
export function LoadingCard() {
  return (
    <div className="border rounded-lg p-6 bg-card">
      <div className="animate-pulse space-y-3">
        <div className="h-4 bg-muted rounded w-1/4" />
        <div className="space-y-2">
          <div className="h-3 bg-muted rounded" />
          <div className="h-3 bg-muted rounded w-5/6" />
        </div>
      </div>
    </div>
  );
}
