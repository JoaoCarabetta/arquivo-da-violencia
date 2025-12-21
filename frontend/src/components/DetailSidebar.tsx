import type { ReactNode } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface DetailSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  children: ReactNode;
  width?: 'default' | 'wide';
}

export function DetailSidebar({
  open,
  onOpenChange,
  title,
  subtitle,
  badge,
  children,
  width = 'default',
}: DetailSidebarProps) {
  const widthClass = width === 'wide' 
    ? 'w-[900px] sm:max-w-[900px]' 
    : 'w-[520px] sm:max-w-[520px]';
  
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className={cn(widthClass, "p-0 flex flex-col bg-zinc-50 dark:bg-zinc-950 [&>button]:z-10 [&>button]:bg-white [&>button]:dark:bg-zinc-900 [&>button]:border [&>button]:border-zinc-200 [&>button]:dark:border-zinc-800 [&>button]:shadow-sm")}>
        <SheetHeader className="px-6 py-4 bg-white dark:bg-zinc-900 border-b shrink-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <SheetTitle className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                {title}
              </SheetTitle>
              {subtitle && (
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400 line-clamp-2">
                  {subtitle}
                </p>
              )}
            </div>
            {badge}
          </div>
        </SheetHeader>
        <ScrollArea className="flex-1 min-h-0">
          <div className="p-4 space-y-3">{children}</div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

interface DetailSectionProps {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
  columns?: 1 | 2;
}

export function DetailSection({ title, icon, children, columns = 2 }: DetailSectionProps) {
  return (
    <div className="bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-hidden">
      <div className="px-3 py-2 bg-zinc-100/50 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-800">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
          {icon}
          {title}
        </h4>
      </div>
      <div className={cn(
        "p-3 gap-3",
        columns === 2 ? "grid grid-cols-2" : "space-y-2"
      )}>
        {children}
      </div>
    </div>
  );
}

interface DetailFieldProps {
  label: string;
  value: ReactNode;
  className?: string;
  mono?: boolean;
}

export function DetailField({ label, value, className = '', mono = false }: DetailFieldProps) {
  const isEmpty = value === null || value === undefined || value === '' || value === '—';
  
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-0.5">
        {label}
      </dt>
      <dd className={cn(
        "text-xs text-zinc-900 dark:text-zinc-100",
        mono && "font-mono text-[10px]",
        isEmpty && "text-zinc-400 dark:text-zinc-600 italic"
      )}>
        {isEmpty ? 'Não informado' : value}
      </dd>
    </div>
  );
}

interface DetailTextBlockProps {
  label: string;
  value: string | null | undefined;
  className?: string;
}

export function DetailTextBlock({ label, value, className = '' }: DetailTextBlockProps) {
  if (!value) return null;
  
  return (
    <div className={cn("col-span-2", className)}>
      <dt className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-1.5">
        {label}
      </dt>
      <dd className="text-xs text-zinc-700 dark:text-zinc-300 leading-relaxed bg-zinc-50 dark:bg-zinc-800/50 rounded-md p-2.5 border border-zinc-100 dark:border-zinc-800">
        {value}
      </dd>
    </div>
  );
}

interface DetailLinkProps {
  label: string;
  url: string | null | undefined;
  className?: string;
}

export function DetailLink({ label, url, className = '' }: DetailLinkProps) {
  if (!url) {
    return (
      <div className={cn("col-span-2 min-w-0", className)}>
        <dt className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-0.5">
          {label}
        </dt>
        <dd className="text-xs text-zinc-400 dark:text-zinc-600 italic">Não informado</dd>
      </div>
    );
  }
  
  // Extract a readable label from URL
  const getUrlLabel = (url: string): string => {
    try {
      const urlObj = new URL(url);
      // For Google News URLs, use a simple label
      if (urlObj.hostname.includes('news.google.com')) {
        return 'Ver no Google News';
      }
      // For other URLs, use domain or a short phrase
      const hostname = urlObj.hostname.replace('www.', '');
      return `Ver em ${hostname}`;
    } catch {
      // If URL parsing fails, use a generic label
      return 'Abrir link';
    }
  };
  
  return (
    <div className={cn("col-span-2 min-w-0", className)}>
      <dt className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-0.5">
        {label}
      </dt>
      <dd>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1"
        >
          {getUrlLabel(url)}
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      </dd>
    </div>
  );
}

interface DetailBadgesProps {
  label: string;
  items: string[];
}

export function DetailBadges({ label, items }: DetailBadgesProps) {
  if (!items.length) return null;
  return (
    <DetailField
      label={label}
      value={
        <div className="flex flex-wrap gap-1.5 mt-1">
          {items.map((item, i) => (
            <Badge key={i} variant="secondary" className="text-xs font-normal">
              {item}
            </Badge>
          ))}
        </div>
      }
    />
  );
}

interface DetailJsonProps {
  label: string;
  data: unknown;
  defaultCollapsed?: boolean;
}

export function DetailJson({ label, data, defaultCollapsed = true }: DetailJsonProps) {
  if (!data || (typeof data === 'object' && Object.keys(data as object).length === 0)) return null;
  
  return (
    <div className="bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-hidden">
      <details open={!defaultCollapsed}>
        <summary className="px-3 py-2 bg-zinc-100/50 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-800 cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            {label}
          </span>
        </summary>
        <div className="p-3 overflow-auto max-h-[400px] bg-zinc-900 dark:bg-black">
          <pre className="text-[10px] font-mono text-emerald-400 whitespace-pre-wrap break-all leading-relaxed">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      </details>
    </div>
  );
}

interface DetailContentProps {
  label: string;
  content: string | null | undefined;
  maxHeight?: string;
}

export function DetailContent({ label, content, maxHeight = '300px' }: DetailContentProps) {
  if (!content) return null;
  
  return (
    <div className="bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-hidden">
      <div className="px-3 py-2 bg-zinc-100/50 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-800">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
          {label}
        </h4>
      </div>
      <div className="p-3 overflow-auto" style={{ maxHeight }}>
        <p className="text-xs text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
          {content}
        </p>
      </div>
    </div>
  );
}
