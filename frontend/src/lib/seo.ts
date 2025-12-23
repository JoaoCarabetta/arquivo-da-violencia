/**
 * SEO utility functions
 */

const siteUrl = import.meta.env.VITE_SITE_URL || 'https://arquivodaviolencia.com.br';
const siteName = 'Arquivo da Violência';
const defaultDescription = 'Monitoramento em tempo real de mortes violentas no Brasil. Dados abertos para pesquisa, jornalismo e sociedade civil.';

export interface SEOConfig {
  title: string;
  description?: string;
  image?: string;
  path?: string;
  type?: 'website' | 'article';
  publishedTime?: string;
  modifiedTime?: string;
}

/**
 * Get full URL for a path
 */
export function getFullUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${siteUrl}${cleanPath}`;
}

/**
 * Get default Open Graph image URL
 */
export function getDefaultImage(): string {
  return `${siteUrl}/og-image.png`; // Can be added later
}

/**
 * Generate Organization structured data
 */
export function generateOrganizationSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: siteName,
    url: siteUrl,
    description: defaultDescription,
    sameAs: [
      'https://github.com/JoaoCarabetta/arquivo-da-violencia',
    ],
  };
}

/**
 * Generate WebSite structured data with search action
 */
export function generateWebSiteSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: siteName,
    url: siteUrl,
    description: defaultDescription,
    potentialAction: {
      '@type': 'SearchAction',
      target: {
        '@type': 'EntryPoint',
        urlTemplate: `${siteUrl}/eventos?search={search_term_string}`,
      },
      'query-input': 'required name=search_term_string',
    },
  };
}

/**
 * Generate Article/NewsArticle structured data
 */
export function generateArticleSchema(config: {
  title: string;
  description: string;
  url: string;
  publishedTime?: string;
  modifiedTime?: string;
  author?: string;
  image?: string;
}) {
  const {
    title,
    description,
    url,
    publishedTime,
    modifiedTime,
    author = siteName,
    image = getDefaultImage(),
  } = config;

  return {
    '@context': 'https://schema.org',
    '@type': 'NewsArticle',
    headline: title,
    description: description,
    url: url,
    datePublished: publishedTime,
    dateModified: modifiedTime || publishedTime,
    author: {
      '@type': 'Organization',
      name: author,
    },
    publisher: {
      '@type': 'Organization',
      name: siteName,
      url: siteUrl,
    },
    image: image,
    mainEntityOfPage: {
      '@type': 'WebPage',
      '@id': url,
    },
  };
}

/**
 * Generate BreadcrumbList structured data
 */
export function generateBreadcrumbSchema(items: Array<{ name: string; url: string }>) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

/**
 * Generate SEO meta tags configuration for @unhead/react
 */
export function generateSEOTags(config: SEOConfig) {
  const {
    title,
    description = defaultDescription,
    image = getDefaultImage(),
    path = '/',
    type = 'website',
    publishedTime,
    modifiedTime,
  } = config;

  const fullUrl = getFullUrl(path);
  const fullTitle = title.includes(siteName) ? title : `${title} | ${siteName}`;

  const metaTags: Array<Record<string, string>> = [
    // Basic meta tags
    { name: 'description', content: description },
    
    // Open Graph
    { property: 'og:title', content: fullTitle },
    { property: 'og:description', content: description },
    { property: 'og:image', content: image },
    { property: 'og:url', content: fullUrl },
    { property: 'og:type', content: type },
    { property: 'og:site_name', content: siteName },
    { property: 'og:locale', content: 'pt_BR' },
    
    // Twitter Card
    { name: 'twitter:card', content: 'summary_large_image' },
    { name: 'twitter:title', content: fullTitle },
    { name: 'twitter:description', content: description },
    { name: 'twitter:image', content: image },
    
    // Additional
    { name: 'robots', content: 'index, follow' },
  ];

  if (publishedTime) {
    metaTags.push({ property: 'article:published_time', content: publishedTime });
  }
  if (modifiedTime) {
    metaTags.push({ property: 'article:modified_time', content: modifiedTime });
  }

  return {
    title: fullTitle,
    meta: metaTags,
    link: [
      { rel: 'canonical', href: fullUrl },
    ],
  };
}

