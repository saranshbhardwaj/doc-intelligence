/**
 * Vertical Dropdown Navigation
 * ChatGPT-inspired dropdown for switching between verticals
 * Uses only tokenized Tailwind classes
 */

import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Building2, Briefcase } from 'lucide-react';
import { cn } from '@/lib/utils';

// Maps URL slug to backend vertical slug
const SLUG_TO_VERTICAL = { re: 'real_estate', pe: 'private_equity' };

export default function VerticalDropdown({ currentVertical, allowedVerticals, className }) {
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

  const allVerticals = [
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

  const allowed = allowedVerticals || ['real_estate'];
  const verticals = allVerticals.filter(v => allowed.includes(SLUG_TO_VERTICAL[v.slug]));

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
        aria-expanded={isOpen}
        className={cn(
          'topbar-nav-button',
          currentVertical && 'topbar-nav-button-active'
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
        <div className="topbar-nav-popover animate-fade-in">
          <div className="py-2">
            {/* Header */}
            <div className="topbar-nav-popover-header">
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
                      'topbar-nav-popover-item',
                      isActive && 'topbar-nav-popover-item-active'
                    )}
                  >
                    <div
                      className={cn(
                        'topbar-nav-popover-icon',
                        isActive && 'topbar-nav-popover-icon-active'
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
                  className="topbar-nav-popover-back"
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
