import { memo } from 'react';
import { LayoutGrid, List, Download, Info, Globe, MapPin } from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import type { PortalMode } from './types';

interface LeftRailProps {
  mode: PortalMode;
  onMode: (mode: PortalMode) => void;
  onAbout: () => void;
}

interface RailButtonProps {
  active: boolean;
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}

function RailButton({ active, title, onClick, children }: RailButtonProps) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="relative flex h-[46px] w-[46px] items-center justify-center rounded-xl transition-colors"
      style={{
        background: active ? 'rgba(47,102,207,.16)' : 'transparent',
        color: active ? '#fff' : 'rgba(255,255,255,.62)',
      }}
      onMouseEnter={(e) => {
        if (!active) {
          e.currentTarget.style.background = 'rgba(255,255,255,.08)';
          e.currentTarget.style.color = '#fff';
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          e.currentTarget.style.background = 'transparent';
          e.currentTarget.style.color = 'rgba(255,255,255,.62)';
        }
      }}
    >
      <span
        className="absolute left-[-13px] top-[11px] bottom-[11px] w-[3px] rounded-r"
        style={{ background: 'var(--blue-400)', opacity: active ? 1 : 0 }}
      />
      {children}
    </button>
  );
}

export const LeftRail = memo(function LeftRail({ mode, onMode, onAbout }: LeftRailProps) {
  const { t, lang, toggleLang } = useI18n();

  return (
    <nav
      className="z-[1300] flex w-[72px] flex-none flex-col items-center py-4"
      style={{ background: 'var(--ink-900)', borderRight: '1px solid rgba(255,255,255,.06)' }}
    >
      <div
        className="mb-1.5 flex h-10 w-10 items-center justify-center rounded-[11px]"
        style={{ background: 'var(--blue-500)', boxShadow: '0 4px 14px rgba(47,102,207,.4)' }}
      >
        <MapPin className="h-[22px] w-[22px]" strokeWidth={2.1} color="#fff" />
      </div>
      <div
        className="mb-[22px] uppercase"
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 8,
          letterSpacing: '.16em',
          color: 'rgba(255,255,255,.4)',
        }}
      >
        Arquivo
      </div>

      <div className="flex w-full flex-col items-center gap-1.5">
        <RailButton active={mode === 'stats'} title={t.navMap} onClick={() => onMode('stats')}>
          <LayoutGrid className="h-[21px] w-[21px]" strokeWidth={1.9} />
        </RailButton>
        <RailButton active={mode === 'feed'} title={t.navFeed} onClick={() => onMode('feed')}>
          <List className="h-[21px] w-[21px]" strokeWidth={1.9} />
        </RailButton>
        <RailButton active={mode === 'data'} title={t.navData} onClick={() => onMode('data')}>
          <Download className="h-[21px] w-[21px]" strokeWidth={1.9} />
        </RailButton>
        <RailButton active={false} title={t.navAbout} onClick={onAbout}>
          <Info className="h-[21px] w-[21px]" strokeWidth={1.9} />
        </RailButton>
      </div>

      <div className="mt-auto flex flex-col items-center gap-1.5">
        <button
          onClick={toggleLang}
          title={t.langSwitch}
          className="flex h-[46px] w-[46px] flex-col items-center justify-center gap-px rounded-xl transition-colors"
          style={{ border: '1px solid rgba(255,255,255,.14)', color: 'rgba(255,255,255,.78)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(255,255,255,.08)';
            e.currentTarget.style.color = '#fff';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.color = 'rgba(255,255,255,.78)';
          }}
        >
          <Globe className="h-[17px] w-[17px]" strokeWidth={1.8} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, fontWeight: 600, letterSpacing: '.04em' }}>
            {lang.toUpperCase()}
          </span>
        </button>
      </div>
    </nav>
  );
});
