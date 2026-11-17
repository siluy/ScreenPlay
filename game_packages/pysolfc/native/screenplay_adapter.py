"""Original PySolFC FreeCell UI, legal moves, and win predicate."""
import os
import sys
from pathlib import Path
import screenplay.native_bridge as bridge

source = Path(__file__).parent
os.environ['PYSOL_CARDSETS'] = str(source.parents[1] / 'assets/pysolfc-cardsets')
# This is the upstream's initialization order.
sys.argv = [str(source / 'pysol.py'), '--gameid=8', '--deal=1', '--nosound', '--noplugins']
from pysollib.init import init
init()
from pysollib import mfxutil
mfxutil.getprefdir = lambda package: str(bridge.private / 'preferences')
from pysollib.options import Options
from pysollib.game import Game
from pysollib.games.freecell import FreeCell
from pysollib.actions import PysolMenubar
from pysollib.resource import CardsetManager
from pysollib.main import main

violations = []
current = None
original_new = Game.newGame
original_defaults = Options.setDefaults


def defaults(self, *args, **kwargs):
    original_defaults(self, *args, **kwargs)
    self.splashscreen = self.autodrop = self.autodeal = self.autofaceup = False
    self.hint = self.free_hint = self.quickplay = False
    self.animations = 1
    self.win_animation = False
    self.redeal_animation = False
    self.confirm = False
    self.toolbar = 0
    self.mouse_type = 'drag-n-drop'
    self.wm_maximized = self.wm_fullscreen = False
    self.player = 'ScreenPlay'
    self.cardset = {0: {0: ('2000', '')}, 1: {0: ('2000', ''), 1: ('2000', '')}}
    self.scale_x = self.scale_y = 1.8
    self.auto_scale = False


def forbidden(*args, **kwargs):
    violations.append('solver_hint_or_game_switch')
    return None


def deal_fixture(game):
    # Trusted fixture only. Native objects, move predicates and win logic stay intact.
    params = bridge.parameters
    if 'rows' in params:
        cutoffs = params['foundation_counts']
        rows = params['rows']
        reserves = params['reserves']
    else:
        cutoff = params['foundation_cards']
        cutoffs = [cutoff] * 4
        ranks = [11, 10, 12] if cutoff == 10 else [11, 10, 9, 12]
        rows = [[[suit, rank] for rank in ranks] for suit in range(4)] + [[] for _ in range(4)]
        reserves = [[] for _ in range(4)]
    assert len(cutoffs) == 4 and all(isinstance(n, int) and 0 <= n <= 13 for n in cutoffs)
    assert len(rows) == 8 and len(reserves) == 4 and all(len(r) <= 1 for r in reserves)
    foundations = [[[suit, rank] for rank in range(n)] for suit, n in enumerate(cutoffs)]
    layout = foundations + rows + reserves
    identities = [tuple(card) for stack in layout for card in stack]
    assert len(identities) == 52 and set(identities) == {(s, r) for s in range(4) for r in range(13)}
    cards = {}
    while game.s.talon.cards:
        card = game.s.talon.removeCard()
        cards[(card.suit, card.rank)] = card
    for stack, identities in zip(list(game.s.foundations) + list(game.s.rows) + list(game.s.reserves), layout):
        for identity in identities:
            card = cards.pop(tuple(identity))
            card.showFace()
            stack.addCard(card)
    assert not cards



def publish():
    game = current
    if game is None:
        return
    foundations = [len(s.cards) for s in game.s.foundations]
    bridge.publish(success=bool(game.isGameWon()), violations=violations,
        game_id=game.id, foundation_cards=foundations, moves=game.moves.index,
        cards=[{'stack':s.id, 'cards':[[c.suit,c.rank,bool(c.face_up)] for c in s.cards]} for s in game.allstacks],
        progress=sum(foundations)/52)
    game.top.after(50, publish)


def new_game(game, *args, **kwargs):
    global current
    if current is not None:
        return forbidden()
    kwargs['dealer'] = lambda: deal_fixture(game)
    kwargs['autoplay'] = 0
    original_new(game, *args, **kwargs)
    current = game
    game.top.wm_geometry('+80+100')
    game.top.after(250, publish)


Options.setDefaults = defaults
# This package exposes only French-card FreeCell; unrelated tile/card families are not loaded.
CardsetManager.identify_missing_cardsets = lambda self: []
Game.newGame = new_game
Game.autoPlay = lambda *args, **kwargs: 0
Game.showHint = Game.startDemo = Game.restoreGame = Game.restoreGameFromBookmark = forbidden
Game.restartGame = forbidden
for name in ['mNewGame', '_mSelectGame', '_mNewGameBySeed', 'mSelectRandomGame', 'mOpen',
             'mDemo', 'mDemoAllGames', 'mHint', 'mSolver', 'mRestart']:
    if hasattr(PysolMenubar, name):
        setattr(PysolMenubar, name, forbidden)
sys.exit(main(sys.argv))
