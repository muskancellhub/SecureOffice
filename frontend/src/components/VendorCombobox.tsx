import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, X } from 'lucide-react';

interface VendorComboboxProps {
  value: string;
  onChange: (value: string) => void;
  vendors: string[];
  id?: string;
  invalid?: boolean;
  placeholder?: string;
}

/**
 * BUG-PRODUCT-UI-005: a searchable vendor combobox that replaces the native
 * <input list=datalist>. The datalist filtered options by the input's current
 * value, so after a vendor was picked, reopening showed ONLY that vendor.
 *
 * Here the list filters ONLY while the user is actively typing (`filter` is a
 * live query string); opening via click / arrow shows ALL vendors regardless of
 * the current selection. Free text is allowed (typing a brand-new vendor name),
 * with a clear button and full keyboard navigation.
 */
export const VendorCombobox = ({ value, onChange, vendors, id, invalid, placeholder }: VendorComboboxProps) => {
  const [open, setOpen] = useState(false);
  // null → not typing (show ALL); a string → active query (filter by it).
  const [filter, setFilter] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const options = useMemo(() => {
    if (filter == null || filter.trim() === '') return vendors;
    const q = filter.toLowerCase();
    return vendors.filter((v) => v.toLowerCase().includes(q));
  }, [vendors, filter]);

  // Close when clicking outside.
  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setFilter(null);
      }
    };
    document.addEventListener('mousedown', onDocMouseDown);
    return () => document.removeEventListener('mousedown', onDocMouseDown);
  }, [open]);

  useEffect(() => { setHighlight(0); }, [filter, open]);

  const openAll = () => { setFilter(null); setOpen(true); };

  const select = (vendor: string) => {
    onChange(vendor);
    setFilter(null);
    setOpen(false);
    inputRef.current?.focus();
  };

  const clear = () => {
    onChange('');
    setFilter(null);
    setOpen(true);
    inputRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) { openAll(); return; }
      setHighlight((h) => Math.min(h + 1, options.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      if (open && options[highlight]) { e.preventDefault(); select(options[highlight]); }
    } else if (e.key === 'Escape') {
      if (open) { e.preventDefault(); setOpen(false); setFilter(null); }
    }
  };

  return (
    <div className={`apx7-combo ${invalid ? 'apx7-invalid' : ''}`} ref={rootRef}>
      <div className="apx7-combo-input-wrap">
        <input
          id={id}
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          placeholder={placeholder || 'Select or type a vendor'}
          value={value}
          onChange={(e) => { onChange(e.target.value); setFilter(e.target.value); setOpen(true); }}
          onFocus={openAll}
          onClick={openAll}
          onKeyDown={onKeyDown}
        />
        {value && (
          <button type="button" className="apx7-combo-clear" aria-label="Clear vendor" tabIndex={-1}
                  onMouseDown={(e) => { e.preventDefault(); clear(); }}>
            <X size={14} />
          </button>
        )}
        <button type="button" className="apx7-combo-toggle" aria-label="Toggle vendor list" tabIndex={-1}
                onMouseDown={(e) => { e.preventDefault(); open ? (setOpen(false), setFilter(null)) : openAll(); }}>
          <ChevronDown size={15} />
        </button>
      </div>

      {open && (
        <ul className="apx7-combo-menu" role="listbox">
          {options.length === 0 ? (
            <li className="apx7-combo-empty">
              {filter && filter.trim() ? `No match — “${filter.trim()}” will be created as a new vendor` : 'No vendors yet'}
            </li>
          ) : (
            options.map((vendor, idx) => (
              <li
                key={vendor}
                role="option"
                aria-selected={vendor === value}
                className={`apx7-combo-option ${idx === highlight ? 'active' : ''} ${vendor === value ? 'selected' : ''}`}
                onMouseEnter={() => setHighlight(idx)}
                onMouseDown={(e) => { e.preventDefault(); select(vendor); }}
              >
                <span>{vendor}</span>
                {vendor === value && <Check size={14} />}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
};
