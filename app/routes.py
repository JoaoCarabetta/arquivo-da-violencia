from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request
from app.models import Incident, Source, ExtractedEvent
from app.services.extraction import extract_event

main = Blueprint('main', __name__)

@main.route('/')
def index():
    incidents = Incident.query.order_by(Incident.date.desc()).all()
    
    # Calculate death statistics
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)
    
    deaths_24h = Incident.query.filter(Incident.date >= last_24h).count()
    deaths_7d = Incident.query.filter(Incident.date >= last_7d).count()
    deaths_30d = Incident.query.filter(Incident.date >= last_30d).count()
    
    return render_template('index.html', 
                           incidents=incidents,
                           deaths_24h=deaths_24h,
                           deaths_7d=deaths_7d,
                           deaths_30d=deaths_30d)

@main.route('/incident/<int:incident_id>')
def incident_detail(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    return render_template('incident.html', incident=incident)

@main.route('/sources')
def sources():
    all_sources = Source.query.order_by(Source.fetched_at.desc()).all()
    return render_template('sources.html', sources=all_sources)

@main.route('/api/extract/<int:source_id>', methods=['POST'])
def api_extract(source_id):
    """Trigger extraction for a single source."""
    force = request.args.get('force', 'false').lower() == 'true'
    result = extract_event(source_id, force=force)
    return jsonify(result)

@main.route('/extractions')
def extractions():
    """Display all extracted events."""
    all_extractions = ExtractedEvent.query.order_by(ExtractedEvent.confidence_score.desc()).all()
    return render_template('extractions.html', extractions=all_extractions)

@main.route('/sobre')
def about():
    """Display the about page."""
    return render_template('about.html')

