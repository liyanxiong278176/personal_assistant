// frontend/components/monitor/ui/stat-card.tsx
interface StatCardProps {
  label: string;
  value: string | number;
  ratio?: number;
}

export function StatCard({ label, value, ratio }: StatCardProps) {
  return (
    <div className="border rounded-lg p-4 bg-card">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {ratio !== undefined && (
        <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-colors ${
              ratio > 80 ? 'bg-destructive' :
              ratio > 60 ? 'bg-orange-500' :
              'bg-green-500'
            }`}
            style={{ width: `${Math.min(ratio, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
