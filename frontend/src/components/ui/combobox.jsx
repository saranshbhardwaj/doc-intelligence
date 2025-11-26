/**
 * Combobox Component - Searchable Dropdown
 *
 * Built with shadcn Command component for filtering/search
 * ChatGPT-inspired design with smooth animations
 *
 * Input:
 *   - items: Array<{value: string, label: string, subtitle?: string}>
 *   - value: string (selected value)
 *   - onValueChange: (value: string) => void
 *   - placeholder?: string
 *   - emptyMessage?: string
 *   - searchPlaceholder?: string
 *
 * Usage:
 *   <Combobox
 *     items={collections.map(c => ({ value: c.id, label: c.name, subtitle: `${c.document_count} docs` }))}
 *     value={selectedId}
 *     onValueChange={setSelectedId}
 *     placeholder="Select collection..."
 *     searchPlaceholder="Search collections..."
 *   />
 */

import { useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "./button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "./command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./popover";

export function Combobox({
  items = [],
  value,
  onValueChange,
  placeholder = "Select item...",
  emptyMessage = "No items found.",
  searchPlaceholder = "Search...",
  className,
}) {
  const [open, setOpen] = useState(false);

  const selectedItem = items.find((item) => item.value === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "w-full justify-between h-11 font-normal",
            !value && "text-muted-foreground",
            className
          )}
        >
          {selectedItem ? (
            <div className="flex items-center justify-between w-full">
              <span className="font-medium">{selectedItem.label}</span>
              {selectedItem.subtitle && (
                <span className="text-xs text-muted-foreground ml-2">
                  {selectedItem.subtitle}
                </span>
              )}
            </div>
          ) : (
            placeholder
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-full p-0" align="start">
        <Command>
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList>
            <CommandEmpty>{emptyMessage}</CommandEmpty>
            <CommandGroup>
              {items.map((item) => (
                <CommandItem
                  key={item.value}
                  value={item.label}
                  keywords={[item.value, item.label, item.subtitle]}
                  onSelect={() => {
                    onValueChange(item.value === value ? "" : item.value);
                    setOpen(false);
                  }}
                  className="cursor-pointer"
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      value === item.value ? "opacity-100" : "opacity-0"
                    )}
                  />
                  <div className="flex items-center justify-between w-full">
                    <span>{item.label}</span>
                    {item.subtitle && (
                      <span className="text-xs text-muted-foreground ml-2">
                        {item.subtitle}
                      </span>
                    )}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
