from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request
from app.models import Incident, Source, ExtractedEvent
from app.services.extraction import extract_event
from app.extensions import db
from sqlalchemy import func, or_, and_

main = Blueprint('main', __name__)


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
    # Calculate death statistics
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)
    
    deaths_24h = Incident.query.filter(Incident.date >= last_24h).count()
    deaths_7d = Incident.query.filter(Incident.date >= last_7d).count()
    deaths_30d = Incident.query.filter(Incident.date >= last_30d).count()
    
    # Incidents will be loaded via DataTables AJAX
    return render_template('index.html', 
                           deaths_24h=deaths_24h,
                           deaths_7d=deaths_7d,
                           deaths_30d=deaths_30d)

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
    # Sources will be loaded via DataTables AJAX
    return render_template('sources.html')

@main.route('/api/extract/<int:source_id>', methods=['POST'])
def api_extract(source_id):
    """Trigger extraction for a single source."""
    force = request.args.get('force', 'false').lower() == 'true'
    result = extract_event(source_id, force=force)
    return jsonify(result)

@main.route('/extractions')
def extractions():
    """Display all extracted events."""
    # Extractions will be loaded via DataTables AJAX
    return render_template('extractions.html')

@main.route('/sobre')
def about():
    """Display the about page."""
    return render_template('about.html')


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
    
    # Base query
    query = Incident.query
    
    # Apply search filter
    searchable_columns = [
        Incident.id, Incident.title, Incident.description,
        Incident.street, Incident.neighborhood, Incident.city
    ]
    query = apply_search_filter(query, params['search'], searchable_columns)
    
    # Get total count before filtering
    records_total = Incident.query.count()
    
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
    incidents = query.offset(params['start']).limit(params['length']).all()
    
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
    
    # Serialize data
    data = []
    for incident in incidents:
        location_parts = []
        if incident.street:
            location_parts.append(incident.street)
        if incident.neighborhood:
            location_parts.append(incident.neighborhood)
        if incident.city:
            location_parts.append(incident.city)
        location_str = ', '.join(location_parts) if location_parts else '-'
        
        description_preview = incident.description[:150] + '...' if incident.description and len(incident.description) > 150 else (incident.description or '-')
        
        data.append({
            'id': incident.id,
            'title': incident.title or '-',
            'date': incident.date.strftime('%d/%m/%Y') if incident.date else 'Desconhecida',
            'location': location_str,
            'description': description_preview,
            'source_count': incident_source_counts.get(incident.id, 0),
            'death_count': incident.death_count if incident.death_count is not None else (len(incident.extractions) if incident.extractions else 0)
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

