"""Text port panels backed by the pinned C++ trading/hiring engine."""
import json
import math
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time

from gameworld.build import ROOT
from gameworld.native import NativeBackend
from .structured import StructuredText, function

COMMODITIES=('Food','Clothing','Metal','Plastic','Equipment','Medical','Industrial','Electronics','Heavy Metals','Luxury Goods')


def game_tools():
    commodity={'type':'string','enum':list(COMMODITIES)}
    return [function('open_panel','Open or switch to one port panel; costs one decision.',
                     {'panel':{'type':'string','enum':['trading','hiring']}}),
            function('close_panel','Return to the port overview; costs one decision.'),
            function('buy','Click buy on one commodity row once; at most one ton, with native affordability/capacity rules.',{'commodity':commodity}),
            function('sell','Click sell on one commodity row once; at most one ton.',{'commodity':commodity}),
            function('hire','Hire at most one crew member in the hiring panel.'),
            function('fire','Dismiss at most one extra crew member in the hiring panel; required crew cannot be dismissed.'),
            function('wait','Spend simulation update opportunities while staying in port.',
                     {'duration_ms':{'type':'integer','minimum':0,'maximum':3000}}),
            function('finish','End and evaluate the native current state.')]


class EndlessText(StructuredText):
    game_name='Endless Sky'
    action_rules=('Only the currently open panel is described. Panel switches cost one decision. '
                  'buy/sell need the trading panel and affect at most one ton; hire/fire need the hiring panel and affect at most one person. '
                  'Ordinary inputs consume 6 update opportunities; wait consumes ceil(duration_ms/17), capped by the remaining simulation budget. '
                  'Thinking time is frozen. This port-only text interface has no loan, outfit, travel, bulk modifier or automatic shopping command. '
                  'Invalid or ineffective actions still consume a decision.')
    tools=staticmethod(game_tools)

    def __init__(self,task_id,condition='text-symbolic',max_decisions=100):
        super().__init__(task_id,condition,max_decisions)
        binary=ROOT/'build/text_endless_sky/endless-text'
        if not binary.exists():raise RuntimeError('Build the independent headless Endless Sky driver first')
        (ROOT/'tmp').mkdir(exist_ok=True)
        self._temporary=tempfile.TemporaryDirectory(prefix='text-endless-',dir=ROOT/'tmp')
        private=Path(self._temporary.name)
        (private/'fixture.txt').write_text(self.task.parameters['native_fixture'])
        (private/'advance.txt').write_text('0 0\n')
        env=dict(os.environ,GAMEWORLD_SESSION='text-port',GAMEWORLD_SCENARIO=self.task.game_id,
                 GAMEWORLD_PRIVATE_DIR=str(private),GAMEWORLD_STATE_FILE=str(private/'state.json'),
                 GAMEWORLD_CONTROL_FILE=str(private/'advance.txt'))
        self._log=(private/'native.log').open('wb');self.process=None;self._buffer=b''
        self.max_updates=self.task.parameters['max_updates']
        self._evaluator=NativeBackend();self._evaluator.task=self.task
        try:
            self.process=subprocess.Popen([str(binary),'--resources',str(ROOT/'.cache/prepared/endless_sky'),
                 '--config',str(private)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self._log,env=env)
            self._state=self._read()
            if self.score()['success']:raise RuntimeError('Initial task already solved')
        except BaseException:
            self.close();raise

    def _read(self):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if b'\n' in self._buffer:
                line,self._buffer=self._buffer.split(b'\n',1)
                if line.startswith(b'GWSTATE '):return json.loads(line[8:])
                continue
            ready,_,_=select.select([self.process.stdout],[],[],max(0,deadline-time.monotonic()))
            if not ready:break
            data=os.read(self.process.stdout.fileno(),65536)
            if not data:raise RuntimeError('Native port driver exited before replying')
            self._buffer+=data
        raise RuntimeError('Native port driver reply timed out')

    def score(self):return self._evaluator.evaluate(self._state)

    def describe(self):
        s=self._state
        lines=[f'Current panel: {s["panel"]}. Port: New Boston. Ship: original Shuttle.',f'Credits: {s["cash"]}.']
        if s['panel']=='trading':
            lines.append(f'Cargo capacity: {s["cargo_capacity"]} tons; free: {s["cargo_capacity"]-sum(s["cargo"].values())} tons.')
            lines += [f'{name}: price {s["prices"][name]} credits/ton; in hold {s["cargo"][name]} tons.' for name in COMMODITIES]
        elif s['panel']=='hiring':
            lines += [f'Crew including pilot: {s["crew"]}; required: {s["required_crew"]}; bunks: {s["bunks"]}.',
                      f'Extra crew: {max(0,s["crew"]-s["required_crew"])}; unused bunks: {max(0,s["bunks"]-s["crew"])}.',
                      'Salary is 100 credits per extra crew member per day.']
        else:lines.append('Available panels: trading, hiring. Cargo, prices and crew details are shown only when their panel is open.')
        lines.append(f'Simulation update opportunities remaining: {self.max_updates-s["processed_updates"]}.')
        return '\n'.join(lines)

    def apply(self,action):
        kind=action['type'];panel=self._state['panel']
        if kind in {'buy','sell'} and panel!='trading':raise ValueError('Wrong panel')
        if kind in {'hire','fire'} and panel!='hiring':raise ValueError('Wrong panel')
        updates=math.ceil(action['duration_ms']/self.task.parameters.get('update_ms',17)) if kind=='wait' else 6
        updates=min(updates,max(0,self.max_updates-self._state['processed_updates']))
        if kind=='open_panel':command=f'open {updates} {action["panel"]}'
        elif kind=='close_panel':command=f'close {updates}'
        elif kind in {'buy','sell'}:command=f'{kind} {updates} {json.dumps(action["commodity"])}'
        else:command=f'{kind} {updates}'
        self.process.stdin.write((command+'\n').encode());self.process.stdin.flush()
        self._state=self._read()

    def native_state(self):return dict(self._state)

    def close(self):
        if self.process:
            if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
            if self.process.stdout:self.process.stdout.close()
        self._log.close();self._temporary.cleanup()
