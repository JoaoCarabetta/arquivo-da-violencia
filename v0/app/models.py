from datetime import datetime
from app.extensions import db

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2048), unique=True, nullable=False)
    resolved_url = db.Column(db.String(2048), nullable=True)
    title = db.Column(db.String(512))
    content = db.Column(db.Text)
    source_type = db.Column(db.String(50)) # 'news_article', 'tweet', etc.
    published_at = db.Column(db.DateTime, nullable=True)  # Article publication date from RSS
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending') # 'pending', 'processed', 'ignored'

    # Relationships
    extractions = db.relationship('ExtractedEvent', backref='source', lazy=True)

    def __repr__(self):
        return f'<Source {self.url}>'

class ExtractedEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('source.id'), nullable=False)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id'), nullable=True)
    
    confidence_score = db.Column(db.Float, default=0.0)
    extracted_date = db.Column(db.DateTime, nullable=True)
    extracted_location = db.Column(db.String(256), nullable=True)
    extracted_victim_name = db.Column(db.String(256), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    death_count = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f'<ExtractedEvent {self.id} from Source {self.source_id}>'

class EventsGroundTruth(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('source.id'), nullable=False)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id'), nullable=True)
    
    confidence_score = db.Column(db.Float, default=0.0)
    extracted_date = db.Column(db.DateTime, nullable=True)
    extracted_location = db.Column(db.String(256), nullable=True)
    extracted_victim_name = db.Column(db.String(256), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    death_count = db.Column(db.Integer, nullable=True)
    group_id = db.Column(db.Integer, nullable=True)  # Groups events that refer to the same real-world incident

    def __repr__(self):
        return f'<EventsGroundTruth {self.id} from Source {self.source_id}, group_id={self.group_id}>'

class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    date = db.Column(db.DateTime, nullable=True)
    victims = db.Column(db.Text, nullable=True)
    country = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), default="Rio de Janeiro")
    neighborhood = db.Column(db.String(100), nullable=True)
    street = db.Column(db.String(256), nullable=True)
    location_extra_info = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    confirmed = db.Column(db.Boolean, default=False)
    death_count = db.Column(db.Integer, nullable=True)
    
    # Geocoding fields
    latitude = db.Column(db.Numeric(10, 8), nullable=True)  # ~1.1mm precision
    longitude = db.Column(db.Numeric(11, 8), nullable=True)  # ~1.1mm precision
    location_precision = db.Column(db.String(50), nullable=True)  # 'exact', 'approximate', 'neighborhood_center', 'city_center'

    # Relationships
    extractions = db.relationship('ExtractedEvent', backref='incident', lazy=True)

    def __repr__(self):
        return f'<Incident {self.title}>'

class Keyword(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Keyword {self.word}>'
