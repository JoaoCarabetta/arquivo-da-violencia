/**
 * Umami product analytics (self-hosted, cookieless).
 * No-ops when VITE_UMAMI_WEBSITE_ID is unset (local/dev default).
 */

type UmamiTrackData = Record<string, string | number | boolean>;

type UmamiTracker = {
  track: {
    (eventName: string, data?: UmamiTrackData): void;
    (payload: (props: Record<string, unknown>) => Record<string, unknown>): void;
  };
};

declare global {
  interface Window {
    umami?: UmamiTracker;
  }
}

let analyticsInitialized = false;
let flushTimer: number | null = null;
const pending: Array<() => boolean> = [];

function websiteId(): string {
  return (import.meta.env.VITE_UMAMI_WEBSITE_ID as string | undefined)?.trim() ?? '';
}

function umamiBaseUrl(): string {
  const raw = (import.meta.env.VITE_UMAMI_URL as string | undefined)?.trim() || 'https://analytics.carabetta.xyz';
  return raw.replace(/\/$/, '');
}

function trackerReady(): boolean {
  return typeof window.umami?.track === 'function';
}

function flushPending(): void {
  while (pending.length > 0 && trackerReady()) {
    const next = pending.shift()!;
    next();
  }
  if (pending.length === 0 && flushTimer != null) {
    window.clearInterval(flushTimer);
    flushTimer = null;
  }
}

/** Queue sends until umami is ready; single shared poller (no stacked intervals). */
function enqueue(send: () => boolean): void {
  if (send()) return;
  pending.push(send);
  if (flushTimer != null) return;

  let attempts = 0;
  flushTimer = window.setInterval(() => {
    attempts += 1;
    flushPending();
    // Keep polling longer for slow networks; drop only after ~10s
    if (pending.length === 0 || attempts >= 100) {
      pending.length = 0;
      if (flushTimer != null) {
        window.clearInterval(flushTimer);
        flushTimer = null;
      }
    }
  }, 100);
}

/**
 * Load the Umami tracker once. Auto pageviews are disabled so SPA
 * navigations are reported via trackPageView.
 */
export function initAnalytics(): void {
  const id = websiteId();
  if (!id || analyticsInitialized || typeof document === 'undefined') {
    return;
  }

  if (document.querySelector(`script[data-website-id="${CSS.escape(id)}"]`)) {
    analyticsInitialized = true;
    return;
  }

  const script = document.createElement('script');
  script.defer = true;
  script.src = `${umamiBaseUrl()}/metrics.js`;
  script.dataset.websiteId = id;
  script.dataset.autoTrack = 'false';
  script.addEventListener('load', () => flushPending());
  script.addEventListener('error', () => {
    pending.length = 0;
    if (flushTimer != null) {
      window.clearInterval(flushTimer);
      flushTimer = null;
    }
  });
  document.head.appendChild(script);
  analyticsInitialized = true;
}

/** Track an SPA page view (path only; Umami fills referrer/title). */
export function trackPageView(path: string): void {
  if (!websiteId()) return;

  const url = path.startsWith('/') ? path : `/${path}`;
  enqueue(() => {
    if (!trackerReady()) return false;
    window.umami!.track((props) => ({ ...props, url }));
    return true;
  });
}

/** Track a custom event. Values must be string | number | boolean. */
export function trackEvent(eventName: string, eventParams?: UmamiTrackData): void {
  if (!websiteId()) return;

  enqueue(() => {
    if (!trackerReady()) return false;
    window.umami!.track(eventName, eventParams);
    return true;
  });
}
