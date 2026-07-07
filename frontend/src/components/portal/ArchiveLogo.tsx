import { memo } from 'react';
import { cn } from '@/lib/utils';

export type ArchiveLogoMark = 'record' | 'monogram' | 'grid' | 'signal';

interface ArchiveLogoProps {
  className?: string;
  size?: number;
  /** White record on dark/colored backgrounds (rail). Light paper on search card. */
  variant?: 'onDark' | 'onLight';
  /** Logo style — switch to compare visibility on the dark rail. */
  mark?: ArchiveLogoMark;
}

const GRID_OPACITIES = [
  [0.55, 0.82, 0.68, 0.5],
  [0.72, 0.95, 0.62, 0.76],
  [0.6, 0.88, 1, 0.7],
  [0.48, 0.65, 0.8, 0.58],
] as const;

const HOT_CELL = { row: 2, col: 2 } as const;

function RecordMark({ variant }: { variant: 'onDark' | 'onLight' }) {
  const paperFill = variant === 'onDark' ? '#ffffff' : 'var(--color-surface)';
  const paperStroke = variant === 'onDark' ? 'rgba(255,255,255,0.5)' : 'var(--stone-300)';
  const lineFill = variant === 'onDark' ? 'var(--stone-500)' : 'var(--stone-400)';

  return (
    <>
      <rect x="3.5" y="2.5" width="17" height="18.5" rx="2.25" fill={paperFill} stroke={paperStroke} strokeWidth="1" />
      <rect x="6.5" y="6.5" width="11" height="1.6" rx="0.8" fill={lineFill} />
      <rect x="6.5" y="10" width="8" height="1.6" rx="0.8" fill={lineFill} fillOpacity={0.75} />
      <circle cx="12" cy="17" r="3.6" fill="var(--red-600)" />
      <circle cx="12" cy="17" r="1.35" fill={paperFill} />
      <path d="M12 20.1 L8.9 23.6 H15.1 Z" fill="var(--red-600)" />
    </>
  );
}

function MonogramMark({ variant }: { variant: 'onDark' | 'onLight' }) {
  const fill = variant === 'onDark' ? '#ffffff' : 'var(--stone-900)';
  return (
    <>
      <text
        x="12"
        y="15.5"
        textAnchor="middle"
        fill={fill}
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 11.5,
          fontWeight: 700,
          letterSpacing: '-0.04em',
        }}
      >
        AV
      </text>
      <circle cx="17.25" cy="6.75" r="2.1" fill="var(--red-600)" />
    </>
  );
}

function GridMark({ variant }: { variant: 'onDark' | 'onLight' }) {
  const cellSize = 4;
  const gap = 0.9;
  const origin = 1.6;
  const baseFill = variant === 'onDark' ? '#ffffff' : 'var(--stone-500)';
  const cells: React.ReactNode[] = [];

  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      const x = origin + col * (cellSize + gap);
      const y = origin + row * (cellSize + gap);
      const isHot = row === HOT_CELL.row && col === HOT_CELL.col;
      cells.push(
        <rect
          key={`${row}-${col}`}
          x={x}
          y={y}
          width={cellSize}
          height={cellSize}
          rx={0.75}
          fill={isHot ? 'var(--red-600)' : baseFill}
          fillOpacity={isHot ? 1 : GRID_OPACITIES[row][col]}
        />
      );
    }
  }

  return <>{cells}</>;
}

function SignalMark() {
  return (
    <>
      <circle cx="12" cy="12" r="8.25" fill="rgba(255,255,255,0.14)" />
      <circle cx="12" cy="12" r="7.25" fill="var(--red-600)" />
      <circle cx="12" cy="12" r="4.75" fill="#ffffff" fillOpacity={0.95} />
      <circle cx="12" cy="12" r="2.35" fill="var(--red-600)" />
    </>
  );
}

export const ArchiveLogo = memo(function ArchiveLogo({
  className,
  size = 22,
  variant = 'onDark',
  mark = 'signal',
}: ArchiveLogoProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={cn('shrink-0', className)}
      aria-hidden
    >
      {mark === 'record' && <RecordMark variant={variant} />}
      {mark === 'monogram' && <MonogramMark variant={variant} />}
      {mark === 'grid' && <GridMark variant={variant} />}
      {mark === 'signal' && <SignalMark />}
    </svg>
  );
});
