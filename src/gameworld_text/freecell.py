"""Data-only native PySolFC stacks: native move predicates and native win check."""
from pathlib import Path
import sys
from types import SimpleNamespace

from gameworld.build import ROOT
from .structured import StructuredText, function

SUITS = ('C','S','H','D')
RANKS = ('A','2','3','4','5','6','7','8','9','10','J','Q','K')
STACKS = tuple([f'T{i}' for i in range(1,9)]+[f'R{i}' for i in range(1,5)]+[f'F_{s}' for s in SUITS])


def game_tools():
    location={'type':'string','enum':list(STACKS)}
    return [function('move_cards','Move the last count cards of source, in their current order, onto target as one native drag.',
                     {'source':location,'target':location,'count':{'type':'integer','minimum':1,'maximum':52}}),
            function('undo','Undo one successful move; the decision budget is not refunded.'),
            function('redo','Redo one undone move; the decision budget is not refunded.'),
            function('wait','Leave the cards unchanged and consume one decision.'),
            function('finish','End and evaluate the current position.')]


class FreeCellText(StructuredText):
    game_name='PySolFC FreeCell'
    action_rules=('T1..T8 are tableau columns; R1..R4 are single-card free cells; F_C/F_S/F_H/F_D are suit foundations. '
                  'Lists run from the upper card to the exposed lower end. Move the last count cards; one legal sequence drag costs one decision. '
                  'C=clubs and S=spades are black; H=hearts and D=diamonds are red. Invalid or ineffective actions also cost one decision. '
                  'No automatic foundation play, hints, solver, restart or changed deal are available.')
    tools=staticmethod(game_tools)

    def __init__(self,task_id,condition='text-symbolic',max_decisions=100):
        super().__init__(task_id,condition,max_decisions)
        source=ROOT/'.cache/sources/pysolfc'
        if not source.exists():raise RuntimeError('Pinned PySolFC source missing')
        sys.path.insert(0,str(source))
        from pysollib.stack import SuperMoveAC_RowStack, ReserveStack, SS_FoundationStack
        from pysollib.acard import AbstractCard
        from pysollib.game import Game
        from pysollib.mfxutil import Struct
        self.game=Game.__new__(Game);self.game.s=SimpleNamespace(rows=[],reserves=[],foundations=[])
        self.game.cards=[AbstractCard(i,0,i//13,i%13,self.game) for i in range(52)]
        for card in self.game.cards:card.face_up=1
        for cls,count,group in [(SuperMoveAC_RowStack,8,self.game.s.rows),
                                (ReserveStack,4,self.game.s.reserves),(SS_FoundationStack,4,self.game.s.foundations)]:
            for i in range(count):
                stack=cls.__new__(cls);stack.game=self.game;stack.cards=[]
                cap=dict(suit=-1,color=-1,rank=-1,base_suit=-1,base_color=-1,base_rank=-1,dir=0,mod=8192,
                         max_move=1,max_accept=1,max_cards=999999,min_move=1,min_accept=1,min_cards=0)
                if cls is SuperMoveAC_RowStack:cap.update(dir=-1,max_move=999999,max_accept=999999)
                if cls is ReserveStack:cap.update(max_cards=1)
                if cls is SS_FoundationStack:cap.update(suit=i,base_suit=i,base_rank=0,dir=1,max_cards=13)
                stack.cap=Struct(**cap);group.append(stack)
        self.stacks=self.game.s.rows+self.game.s.reserves+self.game.s.foundations
        p=self.task.parameters
        cut=p.get('foundation_counts',[p.get('foundation_cards')]*4)
        if 'rows' in p:rows,reserves=p['rows'],p['reserves']
        else:
            ranks=[11,10,12] if p['foundation_cards']==10 else [11,10,9,12]
            rows=[[[s,r] for r in ranks] for s in range(4)]+[[] for _ in range(4)]
            reserves=[[] for _ in range(4)]
        layout=rows+reserves+[[[s,r] for r in range(n)] for s,n in enumerate(cut)]
        state=tuple(tuple(s*13+r for s,r in cards) for cards in layout)
        if len(state)!=16 or sorted(c for pile in state for c in pile)!=list(range(52)):
            raise RuntimeError('Invalid FreeCell fixture')
        self.history=[state];self.position=0;self._load(state)
        if self.score()['success']:raise RuntimeError('Initial task already solved')

    def _load(self,state):
        for stack,ids in zip(self.stacks,state):stack.cards=[self.game.cards[i] for i in ids]

    def state(self):return tuple(tuple(c.id for c in stack.cards) for stack in self.stacks)

    def score(self):
        success=bool(self.game.isGameWon())
        return {'success':success,'score':float(success),'evaluator':'pysolfc-native-rules-text-v1'}

    def describe(self):
        lines=['FreeCell visible card layout. Columns are listed upper-to-lower; the last card is exposed.']
        for name,stack in zip(STACKS[:12],self.stacks[:12]):
            cards=', '.join(RANKS[c.rank]+SUITS[c.suit] for c in stack.cards) or 'empty'
            lines.append(f'{name}: {cards}.')
        for name,stack in zip(STACKS[12:],self.stacks[12:]):
            lines.append(f'{name}: top {RANKS[stack.cards[-1].rank]+SUITS[stack.cards[-1].suit] if stack.cards else "empty"}; {len(stack.cards)} cards built from Ace.')
        return '\n'.join(lines)

    def apply(self,action):
        kind=action['type']
        if kind=='wait':return
        if kind in {'undo','redo'}:
            self.position=max(0,self.position-1) if kind=='undo' else min(len(self.history)-1,self.position+1)
            self._load(self.history[self.position]);return
        i,j=STACKS.index(action['source']),STACKS.index(action['target']);count=action['count']
        source,target=self.stacks[i],self.stacks[j]
        if i==j or count>len(source.cards):return
        cards=source.cards[-count:]
        if not source.canMoveCards(cards) or not target.acceptsCards(source,cards):return
        source.cards=source.cards[:-count];target.cards.extend(cards)
        self.history=self.history[:self.position+1]+[self.state()];self.position+=1

    def native_state(self):
        return {'stacks':{name:[[c.suit,c.rank,bool(c.face_up)] for c in stack.cards] for name,stack in zip(STACKS,self.stacks)},
                'history_position':self.position,'native_game_won':bool(self.game.isGameWon())}
