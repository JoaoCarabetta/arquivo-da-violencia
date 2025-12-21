Here is the technical documentation derived from the analysis. It is structured as a standard API reference guide for software architects and developers.

---

# Google News RSS Interface: Technical Reference

**Version:** NFE/5.0  
**Protocol:** RSS 2.0 (XML)  
**Base URL:** `https://news.google.com/rss`

## 1. Overview
The Google News RSS feed is a dynamic, machine-readable interface to Google’s Knowledge Graph and news index. Unlike static RSS feeds, this interface functions as a real-time Search Engine Results Page (SERP) encapsulated in XML. It offers programmatic access to the same data available on `news.google.com` but requires precise parameterization to ensure deterministic results.

**Key Characteristics:**
*   **Dynamic Generation:** Feeds are generated at request time; no static cursors exist.
*   **Stateless:** No pagination support (page 2, 3, etc. are not accessible via standard offsets).
*   **Protocol:** RSS 2.0 extended with Yahoo Media (`media:`) and Google Content (`g:`) namespaces.

---

## 2. Global Localization Parameters (The Triad)
To prevent IP-based geolocation bias and ensure consistent data scraping, every request **must** include the following three parameters. Omitting these results in "IP-based localization," causing data contamination based on the server's physical location.

| Parameter | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| **`hl`** | String | **Host Language.** ISO-639-1 language code + optional ISO-3166-1 country code. Controls interface language and source weighting. | `en-US`, `fr-CA` |
| **`gl`** | String | **Geo Location.** ISO-3166-1 alpha-2 country code. Boosts sources from this region and adjusts "authority" ranking. | `US`, `GB`, `BR` |
| **`ceid`** | String | **Country:Language ID.** Explicitly selects the Google News "Edition" partition. Acts as a tie-breaker/enforcer for configuration. | `US:en`, `GB:en` |

### Canonical Configuration Matrix
Use these combinations to strictly emulate local users:

| Region | `hl` | `gl` | `ceid` |
| :--- | :--- | :--- | :--- |
| **USA** | `en-US` | `US` | `US:en` |
| **UK** | `en-GB` | `GB` | `GB:en` |
| **India (English)** | `en-IN` | `IN` | `IN:en` |
| **Brazil** | `pt-BR` | `BR` | `BR:pt` |
| **Germany** | `de` | `DE` | `DE:de` |

---

## 3. Endpoints

### 3.1 Search Endpoint
The primary endpoint for keyword-based extraction.
```http
GET /rss/search?q={QUERY}&hl={HL}&gl={GL}&ceid={CEID}
```

### 3.2 Topic Endpoint
Retrieves curated verticals (Business, Tech, Sports) based on algorithmic clustering.
```http
GET /rss/topics/{TOPIC_ID}?hl={HL}&gl={GL}&ceid={CEID}
```
*   **`{TOPIC_ID}`**: A Base64-encoded Protocol Buffer string (starting with `CAAq...`).
*   **Discovery**: IDs must be extracted from the URL of the topic in the web UI (e.g., clicking "Business" in the browser).

### 3.3 Geo-Spatial Endpoint
Generates a "Local News" feed for a specific location string.
```http
GET /rss/headlines/section/geo/{LOCATION}?hl={HL}&gl={GL}&ceid={CEID}
```
*   **`{LOCATION}`**: Accepts City (`Manchester`), State (`TX`), or Zip (`90210`).
*   **Behavior**: Often redirects (HTTP 302) to a `/topics/` endpoint representing that location entity.

### 3.4 Top Headlines
Retrieves the "Front Page" stories for the specified region.
```http
GET /rss?hl={HL}&gl={GL}&ceid={CEID}
```

---

## 4. Query Syntax (`q` parameter)
The `q` parameter supports boolean logic and advanced filtering operators. All values must be URL-encoded.

### Boolean & Logic
| Operator | Syntax | Description |
| :--- | :--- | :--- |
| **AND** | `Space` | Implicit. `Tesla Earnings` matches articles with both terms. |
| **OR** | `OR` | Broadens search. `Crypto OR Bitcoin`. |
| **NOT** | `-` | Exclusion. `Jaguar -car` removes automotive results. |
| **Grouping** | `()` | Enforces logic order. `(Apple OR Microsoft) AND "Revenue"`. |

### Advanced Filters
| Operator | Syntax | Function | Use Case |
| :--- | :--- | :--- | :--- |
| **Site** | `site:domain.com` | Restrict to specific publisher domain. | Competitor monitoring. |
| **Intitle** | `intitle:"text"` | Keyword must appear in the headline. | High-relevance signals. |
| **When** | `when:1h` | Restricts to relative timeframe (h/d). | Real-time polling/deduplication. |
| **After** | `after:YYYY-MM-DD` | Inclusive lower bound date. | Historical scraping. |
| **Before** | `before:YYYY-MM-DD` | Exclusive upper bound date. | Historical scraping. |

---

## 5. Response Schema & Parsing
The response is standard RSS 2.0. Parsers must handle specific idiosyncrasies regarding HTML embedding and link obfuscation.

### Item Structure
```xml
<item>
  <title>Article Headline - Source Name</title>
  <link>https://news.google.com/rss/articles/CBMi...</link>
  <guid isPermaLink="false">CBMi...</guid>
  <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
  <description>&lt;a href="..."&gt;Link&lt;/a&gt;...</description>
  <source url="https://publisher.com">Source Name</source>
</item>
```

### Critical Field Notes
1.  **`<title>`**: Always formatted as `Headline - Source`. Split by the last hyphen to extract metadata.
2.  **`<link>`**: **Obfuscated.** Does not point to the publisher. See Section 6.
3.  **`<description>`**: Contains escaped HTML. Do not parse for clean text; use only for summary extraction if necessary.
4.  **`<media:content>`**: **Unreliable.** Frequently missing or points to low-res Google CDN thumbnails. Do not use for production image rendering; scrape Open Graph tags from the target article instead.

---

## 6. Handling Redirects & URL Obfuscation
The URLs provided in the `<link>` tag (e.g., `news.google.com/rss/articles/CBMi...`) are Base64-encoded Protocol Buffer messages. They redirect via Google servers, often triggering CAPTCHAs or 429s for bots.

### Strategy A: Offline Decoding (Legacy/Fast)
For IDs where the decoded Base64 payload reveals a URL immediately (typically older encoding styles):
1.  Base64 decode the string.
2.  Strip magic prefix bytes (`0x08, 0x13, 0x22`) and suffix bytes.
3.  Extract the length-prefixed ASCII string (the real URL).

### Strategy B: Batchexecute (New/July 2024+)
If the ID decodes to an opaque signature (e.g., starts with `AU_yqL`), offline decoding is impossible.
*   **Requirement:** Use Google's `/_/DotsSplashUi/data/batchexecute` endpoint.
*   **Method:** POST request with signature `garturlreq`.
*   **Mechanism:** Returns the resolved URL via RPC response.

---

## 7. Operational Limitations & Best Practices

### 7.1 Rate Limiting
*   **Limit:** Approx. 10-20 requests/minute per IP.
*   **Error:** HTTP 429 "Too Many Requests".
*   **Mitigation:**
    *   Implement exponential backoff.
    *   Use residential proxy rotation for high-volume ingress.

### 7.2 Result Volume & Pagination
*   **The 100-Item Cap:** The feed strictly limits results to ~100 items per request.
*   **No Pagination:** There is no `&page=2`.
*   **Workaround (Sliding Window):** To retrieve >100 results for a topic, iterate through time using `after:` and `before:`:
    1.  Query `q=Topic after:2024-01-01 before:2024-01-02`.
    2.  If count == 100, reduce window to 12 hours.
    3.  If count < 100, save and advance start date.

### 7.3 Caching
Always respect the `<lastBuildDate>` header. If the timestamp has not changed since the last fetch, the feed content is identical.

### 7.4 Real-Time Polling Architecture
For low-latency monitoring:
1.  Set frequency to 5-10 minutes.
2.  Append `when:1h` to query to minimize payload size.
3.  Store `guid` hashes in a Redis set to deduplicate overlapping results.