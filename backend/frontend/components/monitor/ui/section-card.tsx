// frontend/components/monitor/ui/section-card.tsx
interface SectionCardProps {
  title: string;
  children: React.ReactNode;
}

export function SectionCard({ title, children }: SectionCardProps) {
  return (
    <div className="border rounded-lg bg-card shadow-sm">
      <div className="border-b px-6 py-3">
        <h3 className="text-lg font-semibold">{title}</h3>
      </div>
      <div className="p-6">
        {children}
      </div>
    </div>
  );
}
