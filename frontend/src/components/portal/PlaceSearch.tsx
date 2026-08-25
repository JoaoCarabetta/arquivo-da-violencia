import { useState, useRef, useEffect } from 'react';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface PlaceOption {
  name: string;
  type: 'country' | 'state' | 'municipality';
  uf?: string;
  state?: string;
  displayName: string;
}

interface PlaceSearchProps {
  places: PlaceOption[];
  selectedPlace: PlaceOption | null;
  onSelectPlace: (place: PlaceOption) => void;
  placeholder?: string;
}

export function PlaceSearch({
  places,
  selectedPlace,
  onSelectPlace,
  placeholder = 'Busque um município ou estado',
}: PlaceSearchProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const filteredPlaces = query.trim() === ''
    ? []
    : places.filter(place =>
        place.name.toLowerCase().includes(query.toLowerCase()) ||
        place.displayName.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 10);

  const handleSelectPlace = (place: PlaceOption) => {
    onSelectPlace(place);
    setQuery('');
    setIsOpen(false);
    inputRef.current?.blur();
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || filteredPlaces.length === 0) {
      if (e.key === 'ArrowDown' && query.trim() !== '') {
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev < filteredPlaces.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex(prev => (prev > 0 ? prev - 1 : 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredPlaces[highlightedIndex]) {
          handleSelectPlace(filteredPlaces[highlightedIndex]);
        }
        break;
      case 'Escape':
        setIsOpen(false);
        inputRef.current?.blur();
        break;
    }
  };

  useEffect(() => {
    setHighlightedIndex(0);
  }, [query]);

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-stone-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => {
            if (query.trim() !== '') {
              setIsOpen(true);
            }
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="w-full pl-10 pr-10 py-3 rounded-lg border border-stone-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {query && (
          <button
            onClick={() => {
              setQuery('');
              setIsOpen(false);
              inputRef.current?.focus();
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {isOpen && filteredPlaces.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-2 bg-white rounded-lg border border-stone-200 shadow-lg max-h-80 overflow-y-auto"
        >
          {filteredPlaces.map((place, index) => (
            <button
              key={`${place.type}-${place.displayName}`}
              onClick={() => handleSelectPlace(place)}
              className={cn(
                'w-full px-4 py-3 text-left hover:bg-stone-50 transition-colors',
                index === highlightedIndex && 'bg-stone-100',
                index === 0 && 'rounded-t-lg',
                index === filteredPlaces.length - 1 && 'rounded-b-lg'
              )}
            >
              <div className="font-medium text-stone-900">{place.displayName}</div>
              <div className="text-xs text-stone-500 mt-0.5">
                {place.type === 'country' && 'País'}
                {place.type === 'state' && 'Estado'}
                {place.type === 'municipality' && 'Município'}
              </div>
            </button>
          ))}
        </div>
      )}

      {isOpen && query.trim() !== '' && filteredPlaces.length === 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-2 bg-white rounded-lg border border-stone-200 shadow-lg p-4 text-center text-sm text-stone-500"
        >
          Nenhum município ou estado encontrado
        </div>
      )}
    </div>
  );
}
