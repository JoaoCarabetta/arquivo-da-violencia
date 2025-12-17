# Database Schema Discussion

The goal is to track murders in Rio de Janeiro by gathering data from various sources (news, social media), identifying relevant events, deduplicating them, and enriching the data.

## Proposed Data Flow
1.  **Ingestion**: Scrape/Fetch data from URLs (News articles, Tweets). Store as `RawSource`.
2.  **Identification & Extraction**: parse `RawSource` to find "murder" events. Extract entities (date, location, victim). Store as `PotentialIncident` or `Extraction`.
3.  **Deduplication & Resolution**: Compare `PotentialIncidents`. If they refer to the same real-world event, link them to a single canonical `Incident`.
4.  **Enrichment**: The `Incident` record is the "golden record" containing the best combined data.

## Proposed Models

### 1. Source (Raw Data)
Represents a raw input from the web.
*   `id`: PK
*   `url`: String (Unique)
*   `title`: String
*   `content`: Text (Raw HTML or Text)
*   `source_type`: String (Enum: 'news_article', 'tweet', 'police_report')
*   `fetched_at`: DateTime
*   `status`: Enum ('pending', 'processed', 'ignored')

### 2. ExtractedEvent (Intermediate)
Represents a single "event" found in a source. One Source might mention multiple events, or none.
*   `id`: PK
*   `source_id`: FK -> Source
*   `confidence_score`: Float (How sure are we this is a murder in Rio?)
*   `extracted_date`: DateTime
*   `extracted_location`: String
*   `extracted_victim_name`: String
*   `summary`: Text

### 3. Incident (Canonical)
The real-world event.
*   `id`: PK
*   `title`: String (Cleaned display title)
*   `date`: DateTime (Best estimated date)
*   `location`: String (Best estimated location)
*   `city`: String (e.g., 'Rio de Janeiro')
*   `neighborhood`: String
*   `description`: Text (Composite description)
*   `confirmed`: Boolean (Manual or high-confidence auto verification)

### Relationships
*   `Source` --(1:N)--> `ExtractedEvent`
*   `ExtractedEvent` --(N:1)--> `Incident`
    *   Multiple extractions (from different news reports) point to the same Incident.

## Deduplication Logic
*   When a new `ExtractedEvent` is created, we search suitable existing `Incident`s (matching date +/- 1 day, matching neighborhood/street).
*   If match found: Link `ExtractedEvent` to `Incident`.
*   If no match: Create new `Incident`.

## Questions to Resolve
*   Do we need a `Person` model for victims/perpetrators? (Maybe too complex for V1)
*   Do we keep `ExtractedEvent` separate or just merge directly? Separating allows re-evaluating merges later.
