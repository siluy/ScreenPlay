"""Shared bounded decisions for structured, headless game observations."""
import copy
from gameworld.tasks import load_task


def function(name, description, properties=None):
    properties = properties or {}
    return {"type":"function", "function":{"name":name,"description":description,
            "parameters":{"type":"object","properties":properties,"required":list(properties),
                          "additionalProperties":False}}}


class StructuredText:
    def __init__(self, task_id, condition="text-symbolic", max_decisions=100):
        self.task = load_task(task_id)
        if self.task.game != self.game_name or condition != "text-symbolic":
            raise ValueError("Unsupported game or text condition")
        if type(max_decisions) is not int or max_decisions < 1:
            raise ValueError("Invalid decision budget")
        self.condition, self.max_decisions = condition, max_decisions
        self.decisions = 0; self.receipt = None; self.result = None

    def observe(self):
        return {"task_id":self.task.task_id,"game":self.game_name,"condition":self.condition,
                "observation_id":self.decisions,"instruction":self.task.instruction,
                "rules":self.task.rules+" "+self.action_rules,
                "board_text":self.describe(),"budget_remaining":self.max_decisions-self.decisions,
                "receipt":copy.deepcopy(self.receipt),"ended":self.result is not None,
                "result":copy.deepcopy(self.result)}

    def step(self, action):
        if self.result is not None:
            raise RuntimeError("Episode has ended")
        self.decisions += 1
        valid = True
        try:
            if not isinstance(action,dict):raise ValueError("Expected action object")
            spec=next((t['function']['parameters'] for t in self.tools() if t['function']['name']==action.get('type')),None)
            if spec is None or set(action)!={'type',*spec['required']}:raise ValueError("Invalid fields")
            for key,prop in spec['properties'].items():
                val=action[key]
                if prop['type']=='integer' and (type(val) is not int or val<prop.get('minimum',-10**9) or val>prop.get('maximum',10**9)):
                    raise ValueError("Invalid integer")
                if prop['type']=='string' and not isinstance(val,str):raise ValueError("Invalid string")
                if 'enum' in prop and val not in prop['enum']:raise ValueError("Invalid choice")
            if action['type']!='finish':self.apply(action)
        except ValueError:
            valid=False;self.receipt={'status':'rejected','error':'invalid_action'}
        else:self.receipt={'status':'executed'}
        score=self.score()
        reason=('success' if score['success'] else score.get('failure_reason') if score.get('terminal_failure') else
                'agent_finished' if valid and action['type']=='finish' else
                'decision_budget_exhausted' if self.decisions>=self.max_decisions else None)
        if reason:
            self.result={'success':bool(score['success']),'score':float(score['success']),
                         'stop_reason':reason,'decisions':self.decisions,'evaluator':score['evaluator']}
        return self.observe()
