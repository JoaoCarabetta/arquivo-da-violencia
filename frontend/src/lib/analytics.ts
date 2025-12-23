/**
 * Google Analytics (GA4) tracking utilities
 */

declare global {
  interface Window {
    dataLayer: unknown[];
    gtag: (...args: unknown[]) => void;
  }
}

let gaInitialized = false;

/**
 * Initialize Google Analytics
 */
export function initGA(): void {
  const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID;
  
  if (!measurementId || gaInitialized) {
    return;
  }

  // Initialize dataLayer
  window.dataLayer = window.dataLayer || [];
  function gtag(...args: unknown[]) {
    window.dataLayer.push(args);
  }
  window.gtag = gtag;
  
  gtag('js', new Date());
  gtag('config', measurementId);

  // Load gtag.js script
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
  document.head.appendChild(script);
  
  gaInitialized = true;
}

/**
 * Track a page view
 */
export function trackPageView(path: string, title?: string): void {
  const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID;
  
  if (!measurementId || typeof window.gtag !== 'function') {
    return;
  }

  window.gtag('config', measurementId, {
    page_path: path,
    page_title: title,
  });
}

/**
 * Track a custom event
 */
export function trackEvent(
  eventName: string,
  eventParams?: Record<string, unknown>
): void {
  const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID;
  
  if (!measurementId || typeof window.gtag !== 'function') {
    return;
  }

  window.gtag('event', eventName, eventParams);
}

