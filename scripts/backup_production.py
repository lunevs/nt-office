"""Export the linked Railway PostgreSQL service to ignored local backups/."""
import argparse
import base64
import os
from datetime import datetime
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--railway-cli', default='railway')
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent.parent / 'backups'
    folder.mkdir(exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    stamp = datetime.now(ZoneInfo('Europe/Belgrade')).strftime('%Y%m%d-%H%M%S')
    path = folder / f'railway-production-{stamp}.dump'
    result = subprocess.run([args.railway_cli, 'ssh', '--service', 'Postgres', '--', 'sh', '-c', 'pg_dump --format=custom --no-owner --no-acl | base64'], capture_output=True)
    if result.returncode:
        raise SystemExit('Remote backup command failed; output withheld.')
    try:
        archive = base64.b64decode(result.stdout)
    except ValueError:
        raise SystemExit('Backup stream decoding failed; output withheld.') from None
    if not archive.startswith(b'PGDMP'):
        raise SystemExit('Backup stream is not a PostgreSQL archive; output withheld.')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
        output.write(archive)
    with path.open('rb') as source:
        check = subprocess.run(['docker', 'run', '--rm', '-i', 'postgres:18-alpine', 'pg_restore', '--list'], stdin=source, capture_output=True)
    if check.returncode:
        raise SystemExit(f'Archive verification failed: {path}')
    print(f'Backup verified: {path} ({path.stat().st_size} bytes, mode 0600)')


if __name__ == '__main__':
    main()
