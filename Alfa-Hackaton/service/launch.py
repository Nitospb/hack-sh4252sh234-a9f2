"""Container startup. Never starts collectors or training."""
import os
import sys
from pathlib import Path
from .seed import create

path=Path(os.getenv('ALFA_CATALOG','/catalog/catalog.sqlite'))
if not path.exists():
    if os.getenv('ALFA_REQUIRE_FULL')=='1':raise SystemExit('Mount the prepared catalog and service-assets; full data required')
    path=Path('/state/seed/catalog.sqlite')
    if not path.exists():create(path.parent)
    os.environ['ALFA_CATALOG']=str(path)
    os.environ['ALFA_ASSETS']=str(path.parent/'service-assets.sqlite')
    print('SYNTHETIC SMOKE DATA: mount the complete catalog for real analysis.',flush=True)
if os.getenv('ALFA_REQUIRE_FULL')=='1' and not Path(os.environ.get('ALFA_ASSETS','/catalog/service-assets.sqlite')).is_file():
    raise SystemExit('Full mode requires prepared service-assets.sqlite')
os.execv(sys.executable,[sys.executable,'recommendations/server.py','--host','0.0.0.0','--port','8091',
 '--state',os.getenv('ALFA_FEEDBACK','/state/feedback.sqlite')])
