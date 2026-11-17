"""Endgame: Singularity's original UI and simulation, with a bounded clock."""
import random
import sys
from pathlib import Path
import pygame
import gameworld.native_bridge as bridge
import singularity
from singularity.code import dirs, g
from gameworld_scenario import apply_fixture, goal_status

# Dialog imports this same module; retain one copy of initialized globals.
sys.modules['gameworld_adapter'] = sys.modules[__name__]
active = False
original_tick = None
original_player = None
violations = []


def isolated_directories(_force):
    root = Path(singularity.__file__).parent
    for name, relative in {'root': '', 'data': 'data', 'sounds': 'data/sounds',
                           'music': 'music', 'themes': 'data/themes', 'i18n': 'i18n'}.items():
        dirs.read_dirs[name] = [str(root / relative)]
    for name in ['pref', 'saves', 'log', 'i18n', 'themes']:
        path = bridge.private / name
        path.mkdir(exist_ok=True)
        dirs.write_dirs[name] = str(path)
        dirs.read_dirs.setdefault(name, []).insert(0, str(path))


def pump():
    if not active:
        return
    from singularity.code.graphics.dialog import Dialog
    if bridge.quota() and Dialog.current_dialog is g.map_screen:
        original_tick(g.map_screen, None)
    if g.pl is not original_player and 'player_replaced' not in violations:
        violations.append('player_replaced')
    bases = list(g.all_bases())
    techs = [key for key, value in g.pl.techs.items() if value.done]
    wanted = bridge.parameters.get('technologies', [])
    target_bases = bridge.parameters.get('built_bases', 1)
    built = sum(bool(b.done) for b in bases)
    success, progress = goal_status(bridge.parameters)
    bridge.publish(success=success, violations=violations, native_time=int(g.pl.raw_sec),
                   cash=int(g.pl.cash), researched=techs, built_bases=built,
                   cpu_usage={k:int(v) for k,v in g.pl.cpu_usage.items()},
                   available_cpus=[int(v) for v in g.pl.available_cpus],
                   bases=[{'name':b.name, 'type':b.spec.id, 'done':bool(b.done), 'location':b.location.id, 'cpu':int(b.cpu), 'items':{k:{'type':v.spec.id,'count':int(v.count),'done':bool(v.done)} for k,v in b.items.items() if v}} for b in bases],
                   lost=bool(g.pl.lost_game()),
                   progress=progress)


def start(menu):
    global active, original_tick, original_player
    from singularity.code.screens.map import MapScreen
    from singularity.code.graphics import dialog, constants
    random.seed(bridge.parameters['seed'])
    g.new_game('very-easy', initial_speed=0)
    apply_fixture(bridge.parameters)
    g.pl.intro_shown = True
    original_player = g.pl
    original_tick = MapScreen.on_tick
    menu.map_screen.remove_handler(constants.TICK, menu.map_screen.on_tick)
    # UI timers keep drawing, but only a quota issued by the evaluator advances game time.
    MapScreen.on_tick = lambda self, event: None
    g.map_screen = menu.map_screen
    g.map_screen.needs_warning = False
    active = True
    pump()
    dialog.call_dialog(menu.map_screen, menu)
    raise SystemExit


def forbidden(*args, **kwargs):
    violations.append('forbidden_reset_or_load')
    return None


if __name__ == '__main__':
    dirs.create_directories = isolated_directories
    from singularity.code.screens.main_menu import MainMenu
    from singularity.code.screens.map import GameMenuDialog
    MainMenu.show = start
    GameMenuDialog.load_game = forbidden
    g.debug = False
    sys.argv = [sys.argv[0], '--windowed', '--nosound', '--resolution', '1000x700', '--language', 'en_US']
    singularity.main()
