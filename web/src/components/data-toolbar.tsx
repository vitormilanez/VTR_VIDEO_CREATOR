import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";

export function DataToolbar({
  search,
  onSearch,
  placeholder = "Buscar...",
  children,
  className,
}: {
  search?: string;
  onSearch?: (v: string) => void;
  placeholder?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-3 flex flex-wrap items-center gap-2 rounded-xl border bg-card p-2 shadow-sm",
        className,
      )}
    >
      {onSearch ? (
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search ?? ""}
            onChange={(e) => onSearch(e.target.value)}
            placeholder={placeholder}
            className="h-8 w-64 pl-8"
          />
        </div>
      ) : null}
      {children}
    </div>
  );
}
