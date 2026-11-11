"""Entrada de avaliação; a distribuição Windows inicia server.py diretamente."""
import os, sys
from pathlib import Path
local_deps=Path(__file__).resolve().parent.parent/'dev-deps'
if local_deps.exists():sys.path.insert(0,str(local_deps))
os.environ.setdefault('VF_DATA_DIR',str(Path(__file__).parent.parent/'qa-simple-016'))
import server
sys.argv += ['--preview','--no-browser']
raise SystemExit(server.main())
