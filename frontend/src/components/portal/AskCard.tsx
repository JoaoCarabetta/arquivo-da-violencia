import { useState } from 'react';
import { Loader2, MessageCircleQuestion } from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import { askArchive, type AskResponse } from '@/lib/api';
import { trackEvent } from '@/lib/analytics';

export interface AskApplyPayload {
  map?: { lat: number; lng: number; zoom: number; label: string };
  filters?: { states: string[]; types: string[] };
  eventId?: number;
}

interface AskCardProps {
  onApply: (payload: AskApplyPayload) => void;
}

export function AskCard({ onApply }: AskCardProps) {
  const { t } = useI18n();
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);

  async function submit(text: string) {
    const q = text.trim();
    if (q.length < 3) return;
    setLoading(true);
    setError(false);
    try {
      const data = await askArchive(q);
      setResult(data);
      trackEvent('ask', { intent: String(data.query.intent ?? '') });
      const payload: AskApplyPayload = {};
      if (data.map?.lat != null && data.map?.lng != null) {
        payload.map = {
          lat: data.map.lat,
          lng: data.map.lng,
          zoom: data.map.zoom ?? 13,
          label: data.map.label ?? q,
        };
      }
      if (data.filters && (data.filters.states?.length || data.filters.types?.length)) {
        payload.filters = {
          states: data.filters.states ?? [],
          types: data.filters.types ?? [],
        };
      }
      if (payload.map || payload.filters) onApply(payload);
    } catch {
      setError(true);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    submit(question);
  }

  const examples = [t.askExamplePlace, t.askExampleTrend];

  return (
    <div
      data-testid="ask-card"
      className="overflow-hidden rounded-[14px]"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        boxShadow: '0 6px 26px rgba(20,23,28,.13)',
      }}
    >
      <div className="px-[15px] pb-2 pt-[12px]">
        <div className="flex items-center gap-2" style={{ color: 'var(--stone-900)' }}>
          <MessageCircleQuestion className="h-4 w-4" style={{ color: 'var(--blue-600)' }} />
          <div
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 15,
              fontWeight: 600,
              letterSpacing: '-.01em',
            }}
          >
            {t.askTitle}
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="px-[13px] pb-[10px]">
        <div
          className="flex items-center gap-2 rounded-[10px] px-3 py-[8px]"
          style={{ background: 'var(--stone-100)', border: '1px solid var(--stone-200)' }}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" style={{ color: 'var(--stone-500)' }} />
          ) : null}
          <input
            data-testid="ask-input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t.askPlaceholder}
            className="min-w-0 flex-1 border-none bg-transparent text-base outline-none md:text-sm"
            style={{ fontFamily: 'var(--font-sans)', color: 'var(--stone-900)' }}
          />
          <button
            type="submit"
            data-testid="ask-submit"
            disabled={loading || question.trim().length < 3}
            className="shrink-0 rounded-md border-none px-2.5 py-1"
            style={{
              background: 'var(--blue-500)',
              color: '#fff',
              fontSize: 12,
              fontWeight: 500,
              opacity: loading || question.trim().length < 3 ? 0.55 : 1,
            }}
          >
            {t.askSubmit}
          </button>
        </div>
      </form>

      <div className="flex flex-wrap gap-1.5 px-[13px] pb-[11px]">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            data-testid={`ask-example-${example.slice(0, 12)}`}
            onClick={() => {
              setQuestion(example);
              submit(example);
            }}
            className="rounded-full border-none px-2.5 py-1"
            style={{
              background: 'var(--stone-100)',
              color: 'var(--stone-700)',
              fontSize: 11,
            }}
          >
            {example}
          </button>
        ))}
      </div>

      {error && (
        <p className="px-[15px] pb-3" style={{ fontSize: 12, color: 'var(--red-700)' }}>
          {t.askFailed}
        </p>
      )}

      {result && (
        <div
          data-testid="ask-result"
          className="px-[15px] pb-[13px]"
          style={{ borderTop: '1px solid var(--stone-100)' }}
        >
          <p
            className="pt-2.5 text-pretty"
            style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--stone-800)' }}
          >
            {result.answer}
          </p>
          {result.caveats.length > 0 && (
            <div className="mt-2">
              <div
                className="mb-1 font-mono uppercase"
                style={{ fontSize: 9.5, letterSpacing: '.08em', color: 'var(--stone-500)' }}
              >
                {t.askCaveats}
              </div>
              <ul className="m-0 list-disc space-y-1 pl-4" style={{ fontSize: 11.5, color: 'var(--stone-600)' }}>
                {result.caveats.map((caveat) => (
                  <li key={caveat}>{caveat}</li>
                ))}
              </ul>
            </div>
          )}
          {result.citations.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
              {result.citations.slice(0, 6).map((citation) => (
                <a
                  key={citation.url}
                  href={citation.url.replace('https://arquivodaviolencia.com.br', '') || '/'}
                  className="underline-offset-2 hover:underline"
                  style={{ fontSize: 11.5, color: 'var(--blue-600)' }}
                >
                  {citation.label}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
