from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import sys
from .build import ROOT, build, fetch
from .desktop import permissions, require_permissions
from .tasks import catalog, load_task
from .runner import Episode
from .replay import export_replay
from .validation import validate
from .agents import load_agent_config, load_env_file, OpenAICompatibleAgent
from .experiments import Limits, run_one, run_batch


def emit(value):
    print(json.dumps(value,ensure_ascii=False,indent=2),flush=True)


def main():
    parser = argparse.ArgumentParser(description="GameWorld native desktop research runtime")
    sub = parser.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor")
    sub.add_parser("tasks")
    sub.add_parser("validate")
    for action in ["fetch","build"]:
        p = sub.add_parser(action); p.add_argument("package",choices=["tatham", "openttd", "singularity", "pysolfc", "enigma", "endless_sky"])
    for action in ["serve","run"]:
        p = sub.add_parser(action); p.add_argument("task"); p.add_argument("--output",type=Path)
        if action == "serve":
            p.add_argument("--port",type=int,default=8788)
        else:
            modes = p.add_mutually_exclusive_group(required=True)
            modes.add_argument("--actions",type=Path)
            modes.add_argument("--reference",action="store_true")
            modes.add_argument("--agent-config",type=Path)
            p.add_argument("--env-file",type=Path)
            p.add_argument("--max-model-calls",type=int)
            p.add_argument("--max-decisions",type=int)
            p.add_argument("--max-wall-seconds",type=float)
            p.add_argument("--max-observed-tokens",type=int)
    p = sub.add_parser("batch")
    p.add_argument("--config",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--env-file",type=Path)
    p.add_argument("--resume",action="store_true")
    p.add_argument("--max-jobs",type=int)
    p = sub.add_parser("agent-info")
    p.add_argument("--config",type=Path,required=True)
    p.add_argument("--env-file",type=Path)
    p = sub.add_parser("request-preview")
    p.add_argument("--agent-config",type=Path,required=True)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--env-file",type=Path)
    p = sub.add_parser("replay"); p.add_argument("directory",type=Path)
    args = parser.parse_args()
    try:
        load_env_file(getattr(args,"env_file",None))
        if args.command == "doctor":
            emit({"python":sys.version.split()[0],"permissions":permissions(),
                  "engine_built":(ROOT/"build/tatham/bin/gw-engine").exists(),
                  "native_frontend_built":(ROOT/"build/tatham/bin/GameWorldPuzzles.app").exists(),
                  "openttd_built":(ROOT/"build/openttd-native/openttd").exists(),
                  "native_packages": {name: {"built": (ROOT/"build"/("openttd-native" if name == "openttd" else name)/"build_receipt.json").exists(),
                      "tasks":sum(t["package"] == name for t in catalog().values())}
                      for name in ["tatham", "openttd", "singularity", "pysolfc", "enigma", "endless_sky"]},
                  "isolation":"local development; official isolated evaluation not yet implemented"})
        elif args.command == "tasks":
            emit([{ "task_id":key,"package":task["package"],"game":task["game"],"instruction":task["instruction"],
                   "max_decisions":task["max_decisions"],"split":"development",
                   "difficulty":task.get("parameters",{}).get("curriculum",{}).get("difficulty"),
                   "difficulty_status":"author_estimate"} for key,task in catalog().items()])
        elif args.command == "fetch":
            emit({"source_directory":str(fetch(args.package))})
        elif args.command == "build":
            emit(build(args.package))
        elif args.command == "validate":
            report = validate()
            emit({"passed":report["passed"],"checks":len(report["checks"]),
                  "report":str(ROOT/"artifacts/engine-validation.json"),"scope":report["scope"]})
            return 0 if report["passed"] else 1
        elif args.command == "replay":
            emit({"replay":str(export_replay(args.directory))})
        elif args.command == "agent-info":
            config = load_agent_config(args.config)
            public, key, missing = config.resolve(preview=True)
            emit({"ready":not missing,"config":public,"api_key_present":bool(key),"missing":missing})
        elif args.command == "request-preview":
            import base64
            from PIL import Image
            run = args.run.resolve()
            meta = json.loads((run/"run_meta.json").read_text())
            frame = run/"frames/000000.png"
            with Image.open(frame) as image: width,height = image.size
            observation = {"task":meta["task"],"observation_id":0,
                "image":{"width":width,"height":height,"base64":base64.b64encode(frame.read_bytes()).decode()},
                "budget_remaining":{"decisions":meta["task"]["max_decisions"]},"receipt":{"status":"ready"}}
            agent=OpenAICompatibleAgent(load_agent_config(args.agent_config),preview=True)
            body, _=agent.build_request(observation)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps({"preview_only":True,"network_requests_sent":0,
                "missing_configuration":agent.missing,"body":body},ensure_ascii=False,indent=2)+"\n")
            emit({"preview":str(args.output.resolve()),"network_requests_sent":0,"missing":agent.missing})
        elif args.command == "batch":
            if args.max_jobs is not None and args.max_jobs < 1: raise ValueError("max-jobs must be positive")
            report=run_batch(args.config,args.output,resume=args.resume,max_jobs=args.max_jobs)
            emit(report)
            return 0 if report["complete"] else 2
        elif args.command == "run" and (args.agent_config or args.reference):
            limits=Limits(max_model_calls=args.max_model_calls,max_decisions=args.max_decisions,
                          max_wall_seconds=args.max_wall_seconds,max_observed_tokens=args.max_observed_tokens)
            config=load_agent_config(args.agent_config) if args.agent_config else None
            run=run_one(args.task,agent_config=config,reference=args.reference,output=args.output,limits=limits)
            emit({"result":run["result"],"usage":run["usage"],"replay":str(Path(run["directory"])/"replay.html")})
            return 0 if run["result"].get("success") else 1
        else:
            if args.command == "run" and any(getattr(args,n,None) is not None for n in ["max_model_calls","max_decisions","max_wall_seconds","max_observed_tokens"]):
                raise ValueError("Limits apply to --reference and --agent-config; action-file runs use the task budget")
            require_permissions()
            episode = Episode(load_task(args.task),args.output)
            try:
                observation = episode.start()
                if args.command == "serve":
                    from .server import serve
                    token = secrets.token_urlsafe(32)
                    emit({"url":f"http://127.0.0.1:{args.port}","token":token,"episode_id":episode.id,
                          "run_directory":str(episode.directory),"mode":"shared desktop development"})
                    serve(episode,token,port=args.port)
                else:
                    if args.reference:
                        reference = catalog()[args.task].get("reference",{})
                        actions = reference.get("actions")
                        if actions is None: raise ValueError("This task has no reference input trace")
                        expected_viewport = reference.get("viewport")
                        if expected_viewport and [observation["image"]["width"], observation["image"]["height"]] != expected_viewport:
                            raise ValueError("Reference input viewport does not match the observed game window")
                        (episode.directory/"agent_provenance.json").write_text(json.dumps({"type":"fixture-author-reference","autonomous_model":False}))
                    elif args.actions:
                        actions = json.loads(args.actions.read_text())
                    else:
                        raise ValueError("Use --actions FILE or --reference")
                    for i,action in enumerate(actions):
                        if observation["ended"]: break
                        observation = episode.act({"episode_id":episode.id,"action_id":f"a{i}",
                            "based_on_observation_id":observation["observation_id"],"action":action})
                    if not observation["ended"]:
                        observation=episode.act({"episode_id":episode.id,"action_id":"finish",
                            "based_on_observation_id":observation["observation_id"],"action":{"type":"finish"}})
                    emit({"result":observation["result"],"replay":str(export_replay(episode.directory))})
                    return 0 if observation["result"].get("success") else 1
            finally:
                episode.close()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
