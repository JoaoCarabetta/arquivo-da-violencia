import sys
import os
import click
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import Source, Incident, ExtractedEvent

app = create_app()

@click.group()
def cli():
    pass

@cli.command()
@click.option('--url', prompt='Source URL', help='URL of the news article or post')
@click.option('--title', prompt='Title', help='Title of the source')
@click.option('--content', prompt='Content', help='Content/Body of the source')
@click.option('--source-type', default='news_article', help='Type of source')
def add_source(url, title, content, source_type):
    """Add a raw source to the database."""
    with app.app_context():
        source = Source(url=url, title=title, content=content, source_type=source_type)
        db.session.add(source)
        try:
            db.session.commit()
            click.echo(f"Source added with ID {source.id}")
        except Exception as e:
            db.session.rollback()
            click.echo(f"Error adding source: {e}")

@cli.command()
@click.option('--title', prompt='Incident Title', help='Title of the incident')
@click.option('--description', prompt='Description', help='Description')
@click.option('--victims', help='Information about victims')
@click.option('--country', default='Brasil', help='Country')
@click.option('--state', default='Rio de Janeiro', help='State')
@click.option('--city', default='Rio de Janeiro', help='City')
@click.option('--neighborhood', help='Neighborhood')
@click.option('--street', help='Street name or address')
@click.option('--location-extra-info', help='Additional location information')
@click.option('--date_str', prompt='Date (YYYY-MM-DD)', help='Date of incident')
def add_incident(title, description, victims, country, state, city, neighborhood, street, location_extra_info, date_str):
    """Manually add a confirmed incident."""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        click.echo("Invalid date format. Use YYYY-MM-DD.")
        return

    with app.app_context():
        incident = Incident(
            title=title,
            description=description,
            victims=victims,
            country=country,
            state=state,
            city=city,
            neighborhood=neighborhood,
            street=street,
            location_extra_info=location_extra_info,
            date=date_obj,
            confirmed=True
        )
        db.session.add(incident)
        db.session.commit()
        click.echo(f"Incident added with ID {incident.id}")

@cli.command()
@click.option('--source_id', type=int, prompt='Source ID', help='ID of the source')
@click.option('--incident_id', type=int, prompt='Incident ID', help='ID of the incident to link to')
def link_source(source_id, incident_id):
    """Link a source to an incident via ExtractedEvent."""
    with app.app_context():
        # Create a dummy extraction to link them
        extraction = ExtractedEvent(
            source_id=source_id,
            incident_id=incident_id,
            confidence_score=1.0,
            summary="Manually linked"
        )
        db.session.add(extraction)
        db.session.commit()
        click.echo(f"Linked Source {source_id} to Incident {incident_id}")

if __name__ == '__main__':
    cli()
