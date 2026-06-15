import { Search } from "lucide-react";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

export type Scope = "all" | "near";

interface ScopeToggleProps {
  value: Scope;
  onChange: (scope: Scope) => void;
}

const ITEM_CLASS =
  "h-8 gap-1.5 rounded-md px-3 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground";

export function ScopeToggle({ value, onChange }: ScopeToggleProps) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(next) => {
        if (next === "all" || next === "near") onChange(next);
      }}
      className="rounded-lg border bg-card p-1"
    >
      <ToggleGroupItem value="all" aria-label="Show all strikes" className={ITEM_CLASS}>
        <Search className="h-3.5 w-3.5" />
        All
      </ToggleGroupItem>
      <ToggleGroupItem
        value="near"
        aria-label="Show near-the-money strikes"
        className={ITEM_CLASS}
      >
        <Search className="h-3.5 w-3.5" />
        Near
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
