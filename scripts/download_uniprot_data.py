"""Script to download and process UniProt data dump."""

import asyncio
import aiohttp
import gzip
import json
import logging
from rich.logging import RichHandler
import os
from pathlib import Path
from rich.progress import Progress, DownloadColumn, TransferSpeedColumn
from rich.progress import TextColumn, BarColumn, TimeRemainingColumn
from rich.console import Console

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%H:%M:%S",  # 24h format with hours, minutes, seconds
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger(__name__)
console = Console()

async def download_file(url: str, dest_path: Path, progress: Progress) -> None:
    """Download file with progress bar."""
    task_id = progress.add_task(
        "Downloading UniProt data...", 
        total=None,
        start=True
    )
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise RuntimeError(f"Failed to download: {response.status}")
                
            total_size = int(response.headers.get('content-length', 0))
            progress.update(task_id, total=total_size)
            
            with open(dest_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)
                    progress.update(task_id, advance=len(chunk))

def process_dat_file(dat_path: Path, json_path: Path, progress: Progress) -> None:
    """Process UniProt DAT file into JSON."""
    processed_data = {}
    current_entry = {}
    entries_processed = 0
    
    task_id = progress.add_task("Processing UniProt entries...", total=None)
    
    try:
        with gzip.open(dat_path, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.startswith('ID '):
                    if current_entry and 'gene_symbol' in current_entry:
                        processed_data[current_entry.get('gene_symbol')] = current_entry
                        entries_processed += 1
                        if entries_processed % 1000 == 0:
                            progress.update(task_id, description=f"Processed {entries_processed} entries...")
                    current_entry = {}
                elif line.startswith('GN '):
                    gene_info = line[5:].strip()
                    if 'Name=' in gene_info:
                        gene_symbol = gene_info.split('Name=')[1].split()[0].rstrip(';')
                        current_entry['gene_symbol'] = gene_symbol
                elif line.startswith('DR '):
                    if 'GO;' in line:
                        go_info = line.split('GO;')[1].strip()
                        go_id = go_info.split(';')[0].strip()
                        go_term = go_info.split(';')[1].strip() if len(go_info.split(';')) > 1 else ""
                        if 'go_terms' not in current_entry:
                            current_entry['go_terms'] = []
                        current_entry.get('go_terms', []).append({
                            'id': go_id,
                            'term': go_term
                        })
                elif line.startswith('FT '):
                    feature_line = line[5:].strip()
                    if any(t in feature_line for t in ['DOMAIN', 'DNA_BIND', 'BINDING', 'ACTIVE']):
                        if 'features' not in current_entry:
                            current_entry['features'] = []
                        current_entry.get('features', []).append(feature_line)
                elif line.startswith('KW '):
                    keywords = line[5:].strip().split(';')
                    if 'keywords' not in current_entry:
                        current_entry['keywords'] = []
                    current_entry.get('keywords', []).extend([k.strip() for k in keywords if k.strip()])
                elif line.startswith('CC   -!- FUNCTION:'):
                    if 'functions' not in current_entry:
                        current_entry['functions'] = []
                    current_entry.get('functions', []).append(line[17:].strip())

            # Don't forget the last entry
            if current_entry and 'gene_symbol' in current_entry:
                processed_data[current_entry.get('gene_symbol')] = current_entry
                entries_processed += 1

    except gzip.BadGzipFile:
        logger.error(f"File {dat_path} is not a valid gzip file")
        raise
    except Exception as e:
        logger.error(f"Error processing DAT file: {e}")
        raise

    logger.info(f"Successfully processed {entries_processed} entries")
    
    with gzip.open(json_path, 'wt') as f:
        json.dump(processed_data, f)

async def main():
    """Main function."""
    uniprot_url = os.getenv('MB_UNIPROT_DATA_URL', 
        'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.dat.gz')
    cache_dir = Path(os.getenv('MB_CACHE_DIR', '/tmp/mediabase/cache'))
    uniprot_dir = cache_dir / 'uniprot'
    uniprot_dir.mkdir(parents=True, exist_ok=True)
    
    dat_path = uniprot_dir / "uniprot_sprot.dat.gz"
    json_path = uniprot_dir / "uniprot_processed.json.gz"
    
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        if not dat_path.exists():
            logger.info(f"Downloading UniProt data from {uniprot_url}")
            try:
                await download_file(uniprot_url, dat_path, progress)
            except Exception as e:
                logger.error(f"Download failed: {e}")
                return
        else:
            logger.info(f"Using cached UniProt data from {dat_path}")
        
        if not json_path.exists():
            logger.info("Processing UniProt data...")
            try:
                process_dat_file(dat_path, json_path, progress)
            except Exception as e:
                logger.error(f"Processing failed: {e}")
                return
        else:
            logger.info(f"Using cached processed data from {json_path}")
            
        logger.info(f"UniProt data available at {json_path}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Process failed: {e}")
