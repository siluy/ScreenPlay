"""Pinned upstream native builds; modifications live only in prepared copies."""
import json
import os
from pathlib import Path
import shutil
import sys
from .build import ROOT, run, source_spec, replace_once


def fetch(package):
    spec = source_spec(package)
    source = ROOT / '.cache/sources' / package
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '--no-checkout', '--filter=blob:none', spec['repo'], str(source)])
        run(['git', '-C', str(source), 'checkout', '--detach', spec['base_commit']])
    actual = run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture_output=True).stdout.strip()
    if actual != spec['base_commit']:
        raise RuntimeError(f'{package}: source revision mismatch')
    if run(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], capture_output=True).stdout:
        raise RuntimeError(f'{package}: upstream checkout has modifications')
    if package == 'pysolfc':
        asset = spec['assets']
        cards = ROOT / '.cache/assets/pysolfc-cardsets'
        if not cards.exists():
            cards.parent.mkdir(parents=True, exist_ok=True)
            run(['git','clone','--filter=blob:none','--sparse',asset['repo'],str(cards)])
            run(['git','-C',str(cards),'checkout','--detach',asset['base_commit']])
        if run(['git','-C',str(cards),'rev-parse','HEAD'],capture_output=True).stdout.strip() != asset['base_commit']:
            raise RuntimeError('PySolFC cardset source revision mismatch')
        if run(['git','-C',str(cards),'status','--porcelain','--untracked-files=no'],capture_output=True).stdout:
            raise RuntimeError('PySolFC cardset checkout has modifications')
        if not (cards/'cardset-2000/config.txt').exists():
            run(['git','-C',str(cards),'sparse-checkout','set',*asset['directories']])
    return source


def patch(path, old, new):
    path.write_text(replace_once(path.read_text(), old, new))


def prepare(package, source):
    prepared = ROOT / '.cache/prepared' / package
    if prepared.exists():
        shutil.rmtree(prepared)
    shutil.copytree(source, prepared, ignore=shutil.ignore_patterns('.git', '__pycache__'))
    for item in (ROOT / 'game_packages' / package / 'native').iterdir():
        if item.is_file():
            shutil.copyfile(item, prepared / item.name)
    if package == 'singularity':
        p = prepared / 'singularity/code/graphics/dialog.py'
        patch(p, '            event = pygame.event.wait()',
              '            import screenplay_adapter\n            screenplay_adapter.pump()\n            event = pygame.event.wait(30)')
    if package == 'pysolfc':
        run([sys.executable, 'gen-html.py'], cwd=prepared/'html-src', env=dict(os.environ, PYTHONPATH=str(prepared)))
        shutil.copytree(prepared/'html-src/html', prepared/'data/html', dirs_exist_ok=True)
        shutil.copytree(prepared/'html-src/images', prepared/'data/html/images', dirs_exist_ok=True)
    return prepared


def build(package):
    source = fetch(package)
    prepared = prepare(package, source)
    output = ROOT / 'build' / package
    output.mkdir(parents=True, exist_ok=True)
    if package in {'singularity', 'pysolfc'}:
        command = [sys.executable, str(prepared / 'screenplay_adapter.py')]
    else:
        from .compiled_games import build_compiled
        command = build_compiled(package, prepared, output)
    receipt = {'source': source_spec(package), 'command': command, 'cwd': str(prepared),
               'adapter': 'original-native-game-with-private-telemetry', 'python': sys.version}
    (output / 'build_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
