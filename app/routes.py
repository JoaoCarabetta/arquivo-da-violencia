from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, abort, current_app, make_response
from app.models import Incident, Source, ExtractedEvent
from app.services.extraction import extract_event
from app.extensions import db
from sqlalchemy import func, or_, and_, text
import csv
import io
import json

main = Blueprint('main', __name__)


def check_public_mode():
    """Check if route should be accessible in public mode."""
    if current_app.config.get('PUBLIC_MODE', False):
        abort(404)


def parse_datatables_params():
    """Parse DataTables server-side processing parameters from request."""
    params = {
        'draw': int(request.args.get('draw', 1)),
        'start': int(request.args.get('start', 0)),
        'length': int(request.args.get('length', 10)),
        'search': request.args.get('search[value]', ''),
        'order_column': int(request.args.get('order[0][column]', 0)),
        'order_dir': request.args.get('order[0][dir]', 'asc')
    }
    return params


def apply_search_filter(query, search_value, searchable_columns):
    """Apply global search filter to query."""
    if not search_value:
        return query
    
    search_value = f'%{search_value}%'
    conditions = []
    
    for column in searchable_columns:
        if hasattr(column, 'like'):
            conditions.append(column.like(search_value))
    
    if conditions:
        query = query.filter(or_(*conditions))
    
    return query

@main.route('/')
def index():
    # Incidents will be loaded via DataTables AJAX
    # Chart data will be loaded via AJAX from /api/data/deaths-by-day
    return render_template('index.html')

@main.route('/incident/<int:incident_id>')
def incident_detail(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    
    # Count unique sources for this incident
    unique_sources_count = db.session.query(
        func.count(func.distinct(ExtractedEvent.source_id))
    ).filter(
        ExtractedEvent.incident_id == incident_id
    ).scalar() or 0
    
    return render_template('incident.html', 
                         incident=incident,
                         unique_sources_count=unique_sources_count)

@main.route('/sources')
def sources():
    check_public_mode()
    # Sources will be loaded via DataTables AJAX
    return render_template('sources.html')

@main.route('/api/extract/<int:source_id>', methods=['POST'])
def api_extract(source_id):
    """Trigger extraction for a single source."""
    check_public_mode()
    force = request.args.get('force', 'false').lower() == 'true'
    result = extract_event(source_id, force=force)
    return jsonify(result)

@main.route('/extractions')
def extractions():
    """Display all extracted events."""
    check_public_mode()
    # Extractions will be loaded via DataTables AJAX
    return render_template('extractions.html')

@main.route('/sobre')
def about():
    """Display the about page."""
    return render_template('about.html')

@main.route('/download')
def download():
    """Display the download page."""
    # Get total count of incidents for display
    # Use a simple count query that doesn't select columns
    # Filter for Rio de Janeiro state - exclude all other states/countries
    # Include: (state == 'Rio de Janeiro' OR (state IS NULL AND city == 'Rio de Janeiro'))
    # AND (country IS NULL OR country == 'Brasil')
    # AND exclude known non-RJ states/cities (handle NULLs properly)
    try:
        total_incidents = db.session.query(func.count(Incident.id)).filter(
            or_(
                Incident.state == 'Rio de Janeiro',
                and_(Incident.state.is_(None), Incident.city == 'Rio de Janeiro')
            ),
            or_(
                Incident.country.is_(None),
                Incident.country == 'Brasil'
            )
        ).scalar()
    except Exception:
        # Fallback if query fails
        total_incidents = 0
    return render_template('download.html', total_incidents=total_incidents)


@main.route('/api/data/deaths-by-day')
def api_data_deaths_by_day():
    """Data endpoint for deaths by day chart."""
    # Get number of days from query parameter, default to 30
    days = int(request.args.get('days', 30))
    
    # Calculate date range (start of day)
    end_date = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
    start_date = (end_date - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Query: get only date and death_count fields to avoid loading columns that may not exist
    # Filter permanently for Rio de Janeiro state - exclude all other states/countries
    # Include: (state == 'Rio de Janeiro' OR (state IS NULL AND city == 'Rio de Janeiro'))
    # AND (country IS NULL OR country == 'Brasil')
    # AND exclude known non-RJ states/cities (handle NULLs properly)
    results = db.session.query(
        func.date(Incident.date).label('incident_date'),
        func.sum(func.coalesce(Incident.death_count, 0)).label('total_deaths')
    ).filter(
        or_(
            Incident.state == 'Rio de Janeiro',
            and_(Incident.state.is_(None), Incident.city == 'Rio de Janeiro')
        ),
        or_(
            Incident.country.is_(None),
            Incident.country == 'Brasil'
        ),
        Incident.date.isnot(None),
        Incident.date >= start_date,
        Incident.date <= end_date
    ).group_by(
        func.date(Incident.date)
    ).all()
    
    # Create a dictionary with all dates in range (fill missing dates with 0)
    deaths_by_date = {}
    current_date = start_date.date()
    end_date_only = end_date.date()
    while current_date <= end_date_only:
        deaths_by_date[current_date.isoformat()] = 0
        current_date += timedelta(days=1)
    
    # Update with actual data from query results
    for row in results:
        date_str = row.incident_date
        deaths = int(row.total_deaths) if row.total_deaths else 0
        if date_str and date_str in deaths_by_date:
            deaths_by_date[date_str] = deaths
    
    # Convert to list format
    data = [{'date': date, 'deaths': deaths} for date, deaths in sorted(deaths_by_date.items())]
    
    return jsonify({'data': data})


@main.route('/api/data/incidents')
def api_data_incidents():
    """DataTables server-side processing endpoint for incidents."""
    params = parse_datatables_params()
    
    # Column mapping (index -> SQLAlchemy column)
    columns = [
        Incident.id,
        Incident.title,
        Incident.date,
        Incident.street,  # For location search
        Incident.neighborhood,
        Incident.city,
        Incident.description,
        None,  # Sources count (handled separately)
        Incident.death_count
    ]
    
    # Base query - use with_entities to load only needed columns to avoid errors with missing columns
    # Load only the columns we actually need
    # Filter permanently for Rio de Janeiro state - exclude all other states/countries
    # Include: (state == 'Rio de Janeiro' OR (state IS NULL AND city == 'Rio de Janeiro'))
    # AND (country IS NULL OR country == 'Brasil')
    # AND exclude known non-RJ states/cities (handle NULLs properly)
    query = db.session.query(
        Incident.id,
        Incident.title,
        Incident.date,
        Incident.street,
        Incident.neighborhood,
        Incident.city,
        Incident.description,
        Incident.death_count
    ).filter(
        # Must be Rio de Janeiro state or NULL state with Rio de Janeiro city
        or_(
            Incident.state == 'Rio de Janeiro',
            and_(Incident.state.is_(None), Incident.city == 'Rio de Janeiro')
        ),
        # Country must be NULL or Brasil
        or_(
            Incident.country.is_(None),
            Incident.country == 'Brasil'
        )
    )
    
    # Apply search filter
    searchable_columns = [
        Incident.id, Incident.title, Incident.description,
        Incident.street, Incident.neighborhood, Incident.city
    ]
    query = apply_search_filter(query, params['search'], searchable_columns)
    
    # Get total count before filtering (count doesn't load columns)
    # Filter for Rio de Janeiro state - exclude all other states/countries
    # Include: (state == 'Rio de Janeiro' OR (state IS NULL AND city == 'Rio de Janeiro'))
    # AND (country IS NULL OR country == 'Brasil')
    # AND exclude known non-RJ states/cities (handle NULLs properly)
    records_total = db.session.query(Incident.id).filter(
        or_(
            Incident.state == 'Rio de Janeiro',
            and_(Incident.state.is_(None), Incident.city == 'Rio de Janeiro')
        ),
            or_(
                Incident.country.is_(None),
                Incident.country == 'Brasil'
            )
        ).count()
    
    # Get filtered count
    records_filtered = query.count()
    
    # Apply sorting
    order_column_idx = params['order_column']
    if order_column_idx < len(columns) and columns[order_column_idx] is not None:
        order_column = columns[order_column_idx]
        if params['order_dir'] == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
    else:
        # Default sort by date descending
        query = query.order_by(Incident.date.desc())
    
    # Apply pagination
    incident_rows = query.offset(params['start']).limit(params['length']).all()
    
    # Count unique sources per incident (batch query for performance)
    incident_ids = [row.id for row in incident_rows]
    incident_source_counts = {}
    if incident_ids:
        source_counts = db.session.query(
            ExtractedEvent.incident_id,
            func.count(func.distinct(ExtractedEvent.source_id)).label('source_count')
        ).filter(
            ExtractedEvent.incident_id.in_(incident_ids)
        ).group_by(
            ExtractedEvent.incident_id
        ).all()
        incident_source_counts = {incident_id: count for incident_id, count in source_counts}
    
    # Serialize data - incident_rows is now a list of tuples/Row objects
    data = []
    for row in incident_rows:
        # row is a Row object with named attributes
        incident_id = row.id
        location_parts = []
        if row.street:
            location_parts.append(row.street)
        if row.neighborhood:
            location_parts.append(row.neighborhood)
        if row.city:
            location_parts.append(row.city)
        location_str = ', '.join(location_parts) if location_parts else '-'
        
        description_preview = row.description[:150] + '...' if row.description and len(row.description) > 150 else (row.description or '-')
        
        data.append({
            'id': incident_id,
            'title': row.title or '-',
            'date': row.date.strftime('%d/%m/%Y') if row.date else 'Desconhecida',
            'location': location_str,
            'description': description_preview,
            'source_count': incident_source_counts.get(incident_id, 0),
            'death_count': row.death_count if row.death_count is not None else 0
        })
    
    return jsonify({
        'draw': params['draw'],
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': data
    })


@main.route('/api/data/sources')
def api_data_sources():
    """DataTables server-side processing endpoint for sources."""
    check_public_mode()
    params = parse_datatables_params()
    
    # Column mapping
    columns = [
        Source.id,
        Source.title,
        Source.source_type,
        Source.status,
        Source.fetched_at,
        Source.url,
        None  # Actions column (not sortable)
    ]
    
    # Base query
    query = Source.query
    
    # Apply search filter
    searchable_columns = [
        Source.id, Source.title, Source.source_type, Source.status, Source.url
    ]
    query = apply_search_filter(query, params['search'], searchable_columns)
    
    # Get total count before filtering
    records_total = Source.query.count()
    
    # Get filtered count
    records_filtered = query.count()
    
    # Apply sorting
    order_column_idx = params['order_column']
    if order_column_idx < len(columns) and columns[order_column_idx] is not None:
        order_column = columns[order_column_idx]
        if params['order_dir'] == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
    else:
        # Default sort by fetched_at descending
        query = query.order_by(Source.fetched_at.desc())
    
    # Apply pagination
    sources = query.offset(params['start']).limit(params['length']).all()
    
    # Serialize data
    data = []
    for source in sources:
        url_display = source.resolved_url or source.url or 'N/A'
        url_link = url_display if url_display != 'N/A' else None
        
        data.append({
            'id': source.id,
            'title': source.title or 'No title',
            'source_type': source.source_type or 'unknown',
            'status': source.status or 'pending',
            'fetched_at': source.fetched_at.strftime('%Y-%m-%d %H:%M') if source.fetched_at else 'N/A',
            'url': url_display,
            'url_link': url_link
        })
    
    return jsonify({
        'draw': params['draw'],
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': data
    })


@main.route('/api/data/extractions')
def api_data_extractions():
    """DataTables server-side processing endpoint for extractions."""
    check_public_mode()
    params = parse_datatables_params()
    
    # Column mapping
    columns = [
        ExtractedEvent.id,
        ExtractedEvent.extracted_victim_name,
        ExtractedEvent.extracted_location,
        ExtractedEvent.extracted_date,
        ExtractedEvent.death_count,
        ExtractedEvent.confidence_score,
        ExtractedEvent.summary,
        None,  # Source (relationship)
        None   # Actions column (not sortable)
    ]
    
    # Base query
    query = ExtractedEvent.query
    
    # Apply search filter
    searchable_columns = [
        ExtractedEvent.id, ExtractedEvent.extracted_victim_name,
        ExtractedEvent.extracted_location, ExtractedEvent.summary
    ]
    query = apply_search_filter(query, params['search'], searchable_columns)
    
    # Get total count before filtering
    records_total = ExtractedEvent.query.count()
    
    # Get filtered count
    records_filtered = query.count()
    
    # Apply sorting
    order_column_idx = params['order_column']
    if order_column_idx < len(columns) and columns[order_column_idx] is not None:
        order_column = columns[order_column_idx]
        if params['order_dir'] == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
    else:
        # Default sort by confidence_score descending
        query = query.order_by(ExtractedEvent.confidence_score.desc())
    
    # Apply pagination
    extractions = query.offset(params['start']).limit(params['length']).all()
    
    # Serialize data (include full data for modal functionality)
    data = []
    for extraction in extractions:
        source_data = None
        if extraction.source:
            source_data = {
                'id': extraction.source.id,
                'title': extraction.source.title,
                'url': extraction.source.url,
                'resolved_url': extraction.source.resolved_url,
                'content': extraction.source.content,
                'source_type': extraction.source.source_type,
                'published_at': extraction.source.published_at.strftime('%Y-%m-%d %H:%M') if extraction.source.published_at else None,
                'fetched_at': extraction.source.fetched_at.strftime('%Y-%m-%d %H:%M') if extraction.source.fetched_at else None,
                'status': extraction.source.status
            }
        
        summary_preview = extraction.summary[:150] if extraction.summary else None
        if summary_preview and extraction.summary and len(extraction.summary) > 150:
            summary_preview += '...'
        
        data.append({
            'id': extraction.id,
            'victim_name': extraction.extracted_victim_name,
            'location': extraction.extracted_location,
            'date': extraction.extracted_date.strftime('%Y-%m-%d') if extraction.extracted_date else None,
            'death_count': extraction.death_count,
            'confidence_score': extraction.confidence_score,
            'summary': summary_preview,
            'summary_full': extraction.summary,  # Full summary for modal
            'source': source_data,
            'incident_id': extraction.incident_id,
            'source_title': source_data.get('title') if source_data else None,
            'source_url': (source_data.get('resolved_url') or source_data.get('url')) if source_data else None,
            'source_id': source_data.get('id') if source_data else None
        })
    
    return jsonify({
        'draw': params['draw'],
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': data
    })


@main.route('/api/download/incidents')
def api_download_incidents():
    """Download all incidents as CSV or JSON."""
    format_type = request.args.get('format', 'csv').lower()
    
    # Check if geocoding columns exist in the database
    has_geocoding = False
    try:
        # For SQLite, use PRAGMA to check if columns exist
        result = db.session.execute(text("PRAGMA table_info(incident)"))
        columns = [row[1] for row in result]  # Column name is at index 1
        has_geocoding = 'latitude' in columns and 'longitude' in columns and 'location_precision' in columns
    except Exception:
        # If check fails, assume columns don't exist
        has_geocoding = False
    
    # Get all incidents - query only fields that exist
    # Filter permanently for Rio de Janeiro state - exclude all other states/countries
    # Include: (state == 'Rio de Janeiro' OR (state IS NULL AND city == 'Rio de Janeiro'))
    # AND (country IS NULL OR country == 'Brasil')
    # AND exclude known non-RJ states/cities (handle NULLs properly)
    if has_geocoding:
        incidents = Incident.query.filter(
            or_(
                Incident.state == 'Rio de Janeiro',
                and_(Incident.state.is_(None), Incident.city == 'Rio de Janeiro')
            ),
            or_(
                Incident.country.is_(None),
                Incident.country == 'Brasil'
            )
        ).order_by(Incident.date.desc()).all()
    else:
        # Query without geocoding fields to avoid errors
        # Filter permanently for Rio de Janeiro state - exclude all other states/countries
        # Include: (state == 'Rio de Janeiro' OR (state IS NULL AND city == 'Rio de Janeiro'))
        # AND (country IS NULL OR country == 'Brasil')
        # AND exclude known non-RJ states/cities (handle NULLs properly)
        results = db.session.query(
            Incident.id, Incident.title, Incident.date, Incident.victims,
            Incident.country, Incident.state, Incident.city, Incident.neighborhood,
            Incident.street, Incident.location_extra_info, Incident.description,
            Incident.confirmed, Incident.death_count
        ).filter(
            or_(
                Incident.state == 'Rio de Janeiro',
                and_(Incident.state.is_(None), Incident.city == 'Rio de Janeiro')
            ),
            or_(
                Incident.country.is_(None),
                Incident.country == 'Brasil'
            )
        ).order_by(Incident.date.desc()).all()
        
        # Create a simple class to hold the data
        class SimpleIncident:
            def __init__(self, row):
                self.id = row.id
                self.title = row.title
                self.date = row.date
                self.victims = row.victims
                self.country = row.country
                self.state = row.state
                self.city = row.city
                self.neighborhood = row.neighborhood
                self.street = row.street
                self.location_extra_info = row.location_extra_info
                self.description = row.description
                self.confirmed = row.confirmed
                self.death_count = row.death_count
                self.latitude = None
                self.longitude = None
                self.location_precision = None
        
        incidents = [SimpleIncident(row) for row in results]
    
    # Count unique sources per incident (batch query for performance)
    incident_ids = [inc.id for inc in incidents]
    incident_source_counts = {}
    if incident_ids:
        source_counts = db.session.query(
            ExtractedEvent.incident_id,
            func.count(func.distinct(ExtractedEvent.source_id)).label('source_count')
        ).filter(
            ExtractedEvent.incident_id.in_(incident_ids)
        ).group_by(
            ExtractedEvent.incident_id
        ).all()
        incident_source_counts = {incident_id: count for incident_id, count in source_counts}
    
    # Helper functions to safely get geocoding fields
    def get_latitude(incident):
        if has_geocoding:
            return getattr(incident, 'latitude', None)
        return None
    
    def get_longitude(incident):
        if has_geocoding:
            return getattr(incident, 'longitude', None)
        return None
    
    def get_location_precision(incident):
        if has_geocoding:
            return getattr(incident, 'location_precision', None)
        return None
    
    if format_type == 'json':
        # Generate JSON
        data = []
        for incident in incidents:
            location_parts = []
            if incident.street:
                location_parts.append(incident.street)
            if incident.neighborhood:
                location_parts.append(incident.neighborhood)
            if incident.city:
                location_parts.append(incident.city)
            location_str = ', '.join(location_parts) if location_parts else None
            
            latitude = get_latitude(incident)
            longitude = get_longitude(incident)
            location_precision = get_location_precision(incident)
            
            data.append({
                'id': incident.id,
                'title': incident.title,
                'date': incident.date.isoformat() if incident.date else None,
                'victims': incident.victims,
                'country': incident.country,
                'state': incident.state,
                'city': incident.city,
                'neighborhood': incident.neighborhood,
                'street': incident.street,
                'location_extra_info': incident.location_extra_info,
                'location_full': location_str,
                'latitude': float(latitude) if latitude else None,
                'longitude': float(longitude) if longitude else None,
                'location_precision': location_precision,
                'description': incident.description,
                'confirmed': incident.confirmed,
                'death_count': incident.death_count,
                'source_count': incident_source_counts.get(incident.id, 0)
            })
        
        response = make_response(json.dumps(data, ensure_ascii=False, indent=2))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=incidentes_{datetime.now().strftime("%Y%m%d")}.json'
        return response
    
    else:  # CSV
        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Título', 'Data', 'Vítimas', 'País', 'Estado', 'Cidade', 
            'Bairro', 'Rua', 'Informações Extras de Localização', 'Localização Completa',
            'Latitude', 'Longitude', 'Precisão da Localização', 'Descrição', 
            'Confirmado', 'Número de Mortes', 'Número de Fontes'
        ])
        
        # Write data
        for incident in incidents:
            location_parts = []
            if incident.street:
                location_parts.append(incident.street)
            if incident.neighborhood:
                location_parts.append(incident.neighborhood)
            if incident.city:
                location_parts.append(incident.city)
            location_str = ', '.join(location_parts) if location_parts else ''
            
            latitude = get_latitude(incident)
            longitude = get_longitude(incident)
            location_precision = get_location_precision(incident)
            
            writer.writerow([
                incident.id,
                incident.title or '',
                incident.date.strftime('%Y-%m-%d %H:%M:%S') if incident.date else '',
                incident.victims or '',
                incident.country or '',
                incident.state or '',
                incident.city or '',
                incident.neighborhood or '',
                incident.street or '',
                incident.location_extra_info or '',
                location_str,
                float(latitude) if latitude else '',
                float(longitude) if longitude else '',
                location_precision or '',
                incident.description or '',
                'Sim' if incident.confirmed else 'Não',
                incident.death_count if incident.death_count is not None else '',
                incident_source_counts.get(incident.id, 0)
            ])
        
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=incidentes_{datetime.now().strftime("%Y%m%d")}.csv'
        return response

