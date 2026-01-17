/**
 * Vertical Dropdown Navigation
 * ChatGPT-inspired dropdown for switching between verticals
 * Uses only tokenized Tailwind classes
 */

import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Building2, Briefcase } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function VerticalDropdown({ currentVertical, className }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const verticals = [
    {
      name: 'Real Estate',
      slug: 're',
      path: '/app/re',
      icon: Building2,
      description: 'Property analysis and templates',
    },
    {
      name: 'Private Equity',
      slug: 'pe',
      path: '/app/pe',
      icon: Briefcase,
      description: 'Investment analysis',
    },
  ];

  const getCurrentLabel = () => {
    if (!currentVertical) return 'Verticals';
    const vertical = verticals.find(v => v.slug === currentVertical);
    return vertical ? vertical.name : 'Verticals';
  };

  const handleToggle = () => setIsOpen(!isOpen);

  return (
    <div className={cn('relative', className)} ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={handleToggle}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
          currentVertical
            ? 'bg-primary/10 text-primary'
            : 'text-muted-foreground hover:bg-popover'
        )}
      >
        <span>{getCurrentLabel()}</span>
        <ChevronDown
          className={cn(
            'w-4 h-4 transition-transform duration-200',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-64 bg-popover border border-border rounded-lg shadow-lg animate-fade-in z-50">
          <div className="py-2">
            {/* Header */}
            <div className="px-4 py-2 border-b border-border">
              <p className="text-xs font-medium text-muted-foreground">
                Select Vertical
              </p>
            </div>

            {/* Vertical Options */}
            <div className="py-1">
              {verticals.map((vertical) => {
                const Icon = vertical.icon;
                const isActive = currentVertical === vertical.slug;

                return (
                  <Link
                    key={vertical.slug}
                    to={vertical.path}
                    onClick={() => setIsOpen(false)}
                    className={cn(
                      'flex items-start gap-3 px-4 py-3 transition-colors',
                      isActive
                        ? 'bg-accent text-accent-foreground'
                        : 'hover:bg-accent/50'
                    )}
                  >
                    <div
                      className={cn(
                        'flex-shrink-0 p-2 rounded-md',
                        isActive ? 'bg-primary/10' : 'bg-muted'
                      )}
                    >
                      <Icon
                        className={cn(
                          'w-4 h-4',
                          isActive ? 'text-primary' : 'text-muted-foreground'
                        )}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div
                        className={cn(
                          'text-sm font-medium',
                          isActive ? 'text-foreground' : 'text-foreground'
                        )}
                      >
                        {vertical.name}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {vertical.description}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>

            {/* Back to Core (only show if in a vertical) */}
            {currentVertical && (
              <>
                <div className="border-t border-border my-1" />
                <Link
                  to="/app/library"
                  onClick={() => setIsOpen(false)}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
                >
                  <span>← Back to Core Features</span>
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
