import click
import os
from flask.cli import with_appcontext
from app import create_app
from app.services.ingestion import run_ingestion
from app.services.extraction import run_extraction, extract_event
from app.services.enrichment import run_enrichment, re_enrich_incident, deduplicate_incidents
from app.models import Incident
from app.models import ExtractedEvent
from app.extensions import db

app_instance = create_app()

@click.group()
def cli():
    """Arquivo da Violencia - Pipeline Manager"""
    pass

@cli.command()
@click.option('--start-date', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', help='End date (YYYY-MM-DD)')
@click.option('--query', help='Search query')
@click.option('--expand', is_flag=True, help='Expand query with related topics')
@click.option('--geo', is_flag=True, help='Expand query with specific Rio locations/neighborhoods')
@click.option('--force', is_flag=True, help='Force update')
def fetch(start_date, end_date, query, expand, geo, force):
    """Stage 1: Ingest RSS feeds and download content."""
    with app_instance.app_context():
        run_ingestion(start_date=start_date, end_date=end_date, query=query, force=force, expand_queries=expand, expand_geo=geo)

@cli.command()
@click.option('--force', is_flag=True, help='Force re-extraction of processed items.')
@click.option('--limit', type=int, help='Limit number of items to process')
@click.option('--workers', type=int, default=10, help='Number of parallel threads (default 10)')
def extract(force, limit, workers):
    """Stage 2: Extract content and identify events."""
    with app_instance.app_context():
        run_extraction(force=force, limit=limit, max_workers=workers)

@cli.command()
@click.option('--dry-run', is_flag=True, help='Preview changes without committing to database.')
@click.option('--no-create', is_flag=True, help='Do not auto-create new Incidents for unmatched events.')
@click.option('--max-workers', default=10, help='Number of parallel workers for enrichment.')
def enrich(dry_run, no_create, max_workers):
    """Stage 3: Deduplicate and Enrich."""
    with app_instance.app_context():
        run_enrichment(auto_create=not no_create, dry_run=dry_run, max_workers=max_workers)

@cli.command()
@click.option('--dry-run', is_flag=True, help='Preview changes without committing to database.')
def deduplicate(dry_run):
    """Deduplicate and merge duplicate incidents."""
    with app_instance.app_context():
        result = deduplicate_incidents(dry_run=dry_run)
        click.echo(f"✅ Deduplication complete. Merged {result['merged']} duplicate(s)")

@cli.command()
@click.option('--incident-id', type=int, help='Re-enrich a specific incident by ID')
@click.option('--all', is_flag=True, help='Re-enrich all incidents')
@click.option('--dry-run', is_flag=True, help='Preview changes without committing to database.')
def re_enrich(incident_id, all, dry_run):
    """Re-enrich incidents using LLM with all current related sources."""
    with app_instance.app_context():
        if incident_id:
            result = re_enrich_incident(incident_id, dry_run=dry_run)
            if result["success"]:
                click.echo(f"✅ {result['message']}")
                click.echo(f"   Title: {result['incident']['title']}")
                click.echo(f"   Location: {result['incident']['location']}")
            else:
                click.echo(f"❌ {result['message']}")
        elif all:
            incidents = Incident.query.all()
            total = len(incidents)
            click.echo(f"Re-enriching {total} incidents...")
            
            success_count = 0
            error_count = 0
            
            for i, incident in enumerate(incidents, 1):
                click.echo(f"\n[{i}/{total}] Processing Incident {incident.id}...")
                result = re_enrich_incident(incident.id, dry_run=dry_run)
                if result["success"]:
                    success_count += 1
                    click.echo(f"  ✅ {result['message']}")
                else:
                    error_count += 1
                    click.echo(f"  ❌ {result['message']}")
            
            click.echo(f"\n{'='*50}")
            click.echo(f"Re-enrichment complete {'(DRY RUN)' if dry_run else ''}")
            click.echo(f"  Total: {total}")
            click.echo(f"  Successful: {success_count}")
            click.echo(f"  Errors: {error_count}")
            click.echo(f"{'='*50}")
        else:
            click.echo("Please specify --incident-id <id> or --all")

@cli.command()
@click.option('--force', is_flag=True)
def run_all(force):
    """Run full pipeline (Fetch -> Extract -> Enrich)."""
    with app_instance.app_context():
        print("=== STAGE 1: FETCH ===")
        run_ingestion()
        print("\n=== STAGE 2: EXTRACT ===")
        run_extraction(force=force)
        print("\n=== STAGE 3: ENRICH ===")
        run_enrichment(max_workers=10)

@cli.command()
@click.argument('message')
def db_revision(message):
    """Create a new database migration revision."""
    os.system(f'alembic revision --autogenerate -m "{message}"')

@cli.command()
def db_upgrade():
    """Upgrade database to the latest revision."""
    os.system('alembic upgrade head')

@cli.command()
@click.argument('revision', default='head')
def db_downgrade(revision):
    """Downgrade database to a previous revision."""
    os.system(f'alembic downgrade {revision}')

@cli.command()
def db_current():
    """Show current database revision."""
    os.system('alembic current')

@cli.command()
def db_history():
    """Show migration history."""
    os.system('alembic history')

@cli.command()
@click.option('--workers', type=int, default=10, help='Number of parallel threads (default 10)')
@click.option('--limit', type=int, help='Limit number of extractions to re-process')
def reextract_all(workers, limit):
    """Re-extract all sources that have existing ExtractedEvent records."""
    with app_instance.app_context():
        # Get all unique source_ids that have extractions
        query = db.session.query(ExtractedEvent.source_id).distinct()
        if limit:
            query = query.limit(limit)
        
        source_ids = [row[0] for row in query.all()]
        total = len(source_ids)
        
        if total == 0:
            print("No extractions found to re-extract.")
            return
        
        print(f"Found {total} sources with extractions to re-extract.")
        print(f"Using {workers} parallel workers...")
        print("=" * 60)
        
        # Process in parallel using ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from app.services.extraction import process_single_source
        
        success_count = 0
        error_count = 0
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            futures = {executor.submit(process_single_source, app_instance, source_id, force=True): source_id 
                       for source_id in source_ids}
            
            # Process as they complete
            for i, future in enumerate(as_completed(futures)):
                source_id = futures[future]
                try:
                    if future.result():
                        success_count += 1
                        print(f"✓ [{i+1}/{total}] Re-extracted source {source_id}")
                    else:
                        error_count += 1
                        print(f"✗ [{i+1}/{total}] Failed to re-extract source {source_id}")
                except Exception as e:
                    error_count += 1
                    print(f"✗ [{i+1}/{total}] Error re-extracting source {source_id}: {e}")
                
                # Progress update every 10 items
                if (i + 1) % 10 == 0:
                    print(f"Progress: {i+1}/{total} (Success: {success_count}, Errors: {error_count})")
        
        print("=" * 60)
        print(f"Re-extraction complete!")
        print(f"  Total: {total}")
        print(f"  Successful: {success_count}")
        print(f"  Errors: {error_count}")

@cli.command()
@click.option('--dry-run', is_flag=True, help='Preview changes without committing to database.')
@click.option('--unlink-extractions', is_flag=True, help='Unlink ExtractedEvents from incidents (set incident_id to None) instead of deleting them.')
@click.option('--force', is_flag=True, help='Skip confirmation prompt.')
def clean_incidents(dry_run, unlink_extractions, force):
    """Delete all incidents from the database."""
    with app_instance.app_context():
        incidents = Incident.query.all()
        total = len(incidents)
        
        if total == 0:
            click.echo("No incidents found in the database.")
            return
        
        click.echo(f"Found {total} incident(s) to delete.")
        
        if unlink_extractions:
            # Count extractions that will be unlinked
            extraction_count = ExtractedEvent.query.filter(
                ExtractedEvent.incident_id.isnot(None)
            ).count()
            click.echo(f"Will unlink {extraction_count} extraction(s) from incidents.")
        
        if dry_run:
            click.echo("DRY RUN: No changes will be made.")
            return
        
        if not force:
            if not click.confirm('Are you sure you want to delete all incidents?'):
                click.echo("Cancelled.")
                return
        
        # Unlink extractions if requested
        if unlink_extractions:
            ExtractedEvent.query.filter(
                ExtractedEvent.incident_id.isnot(None)
            ).update({ExtractedEvent.incident_id: None}, synchronize_session=False)
            click.echo(f"✓ Unlinked extractions from incidents")
        
        # Delete all incidents
        deleted = Incident.query.delete()
        db.session.commit()
        
        click.echo(f"✅ Deleted {deleted} incident(s) from the database.")

if __name__ == '__main__':
    cli()
