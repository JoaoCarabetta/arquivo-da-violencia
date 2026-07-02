import { memo } from 'react';
import { LayoutGrid, List, Download, Info, Globe, MapPin, BookOpen } from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import { cn } from '@/lib/utils';
import type { PortalMode } from './types';

interface LeftRailProps {
  mode: PortalMode;
  onMode: (mode: PortalMode) => void;
  onAbout: () => void;
  onMethodology: () => void;
}

interface RailButtonProps {
  active: boolean;
  title: string;
  onClick: () => void;
  children: React.ReactNode;
  variant?: 'desktop' | 'mobile';
}

function RailButton({ active, title, onClick, children, variant = 'desktop' }: RailButtonProps) {
  const isMobile = variant === 'mobile';

  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      className={cn(
        'relative flex items-center justify-center rounded-xl transition-colors',
        isMobile ? 'h-11 min-w-0 flex-1 flex-col gap-0.5 px-1 py-1.5' : 'h-[46px] w-[46px]'
      )}
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
      {!isMobile && (
        <span
          className="absolute left-[-13px] top-[11px] bottom-[11px] w-[3px] rounded-r"
          style={{ background: 'var(--blue-400)', opacity: active ? 1 : 0 }}
        />
      )}
      {children}
      {isMobile && (
        <span
          className="max-w-full truncate text-center"
          style={{ fontFamily: 'var(--font-mono)', fontSize: 7.5, letterSpacing: '.02em' }}
        >
          {title.split(' ')[0]}
        </span>
      )}
    </button>
  );
}

function DesktopRail({ mode, onMode, onAbout, onMethodology }: LeftRailProps) {
  const { t, lang, toggleLang } = useI18n();

  return (
    <nav
      className="z-[1300] hidden w-[72px] flex-none flex-col items-center py-4 md:flex"
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
        <RailButton active={false} title={t.navMethodology} onClick={onMethodology}>
          <BookOpen className="h-[21px] w-[21px]" strokeWidth={1.9} />
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
}

function MobileRail({ mode, onMode, onAbout, onMethodology }: LeftRailProps) {
  const { t, lang, toggleLang } = useI18n();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-[1300] flex md:hidden"
      style={{
        background: 'var(--ink-900)',
        borderTop: '1px solid rgba(255,255,255,.06)',
        paddingBottom: 'env(safe-area-inset-bottom, 0px)',
      }}
    >
      <div className="flex w-full items-stretch gap-0.5 px-1 py-1.5">
        <RailButton active={mode === 'stats'} title={t.navMap} variant="mobile" onClick={() => onMode('stats')}>
          <LayoutGrid className="h-[18px] w-[18px]" strokeWidth={1.9} />
        </RailButton>
        <RailButton active={mode === 'feed'} title={t.navFeed} variant="mobile" onClick={() => onMode('feed')}>
          <List className="h-[18px] w-[18px]" strokeWidth={1.9} />
        </RailButton>
        <RailButton active={mode === 'data'} title={t.navData} variant="mobile" onClick={() => onMode('data')}>
          <Download className="h-[18px] w-[18px]" strokeWidth={1.9} />
        </RailButton>
        <RailButton active={false} title={t.navMethodology} variant="mobile" onClick={onMethodology}>
          <BookOpen className="h-[18px] w-[18px]" strokeWidth={1.9} />
        </RailButton>
        <RailButton active={false} title={t.navAbout} variant="mobile" onClick={onAbout}>
          <Info className="h-[18px] w-[18px]" strokeWidth={1.9} />
        </RailButton>
        <button
          onClick={toggleLang}
          title={t.langSwitch}
          aria-label={t.langSwitch}
          className="flex min-w-[44px] flex-none flex-col items-center justify-center gap-0.5 rounded-xl px-1 py-1.5"
          style={{ border: '1px solid rgba(255,255,255,.14)', color: 'rgba(255,255,255,.78)' }}
        >
          <Globe className="h-[16px] w-[16px]" strokeWidth={1.8} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 7.5, fontWeight: 600 }}>
            {lang.toUpperCase()}
          </span>
        </button>
      </div>
    </nav>
  );
}

export const LeftRail = memo(function LeftRail(props: LeftRailProps) {
  return (
    <>
      <DesktopRail {...props} />
      <MobileRail {...props} />
    </>
  );
});
