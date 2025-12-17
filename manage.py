import click
from app import create_app
from app.services.ingestion import run_ingestion
from app.services.extraction import run_extraction
from app.services.enrichment import run_enrichment

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
def enrich(dry_run, no_create):
    """Stage 3: Deduplicate and Enrich."""
    with app_instance.app_context():
        run_enrichment(auto_create=not no_create, dry_run=dry_run)

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
        run_enrichment()

if __name__ == '__main__':
    cli()
