"""Transport-only agent client. Does not access any game files or internals."""
import json
from urllib.request import Request, urlopen
import uuid


class GameWorldClient:
    def __init__(self, base_url: str, token: str):
        self.base_url=base_url.rstrip("/")
        self.token=token

    def _request(self,path,body=None):
        data=None if body is None else json.dumps(body).encode()
        request=Request(self.base_url+path,data=data,headers={
            "Authorization":"Bearer "+self.token,"Content-Type":"application/json"})
        with urlopen(request,timeout=30) as response:
            return json.load(response)

    def observe(self):
        return self._request("/v1/observation")

    def prepare_action(self,observation,action):
        # Keep this exact request if a network retry is needed.
        return {"episode_id":observation["episode_id"],"action_id":uuid.uuid4().hex,
                "based_on_observation_id":observation["observation_id"],"action":action}

    def send_action(self,request):
        return self._request("/v1/action",request)
