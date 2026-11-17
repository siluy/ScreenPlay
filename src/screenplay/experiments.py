"""Serial, resumable experiment runs on a shared development desktop."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import fcntl
from collections import Counter
import html
import json
from pathlib import Path
import random
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from .agents import AgentConfig, APIError, CapacityError, OpenAICompatibleAgent, SYSTEM_PROMPT, load_agent_config
from .guarded import ProcessGuard, run_guarded
from .build import ROOT, source_spec
from .desktop import require_permissions
from .replay import export_replay
from .runner import Episode, write_json, append_json
from .tasks import catalog, load_task


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_model_calls: int | None = Field(default=None, ge=1)
    max_decisions: int | None = Field(default=None, ge=1)
    max_wall_seconds: float | None = Field(default=None, gt=0)
    max_observed_tokens: int | None = Field(default=None, ge=1)


def usage_summary(directory: Path, *, applicable: bool) -> dict:
    path = directory / "model_calls.jsonl"
    calls = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    sent = [r for r in calls if r.get('request_sent',True)]
    complete = applicable and all((r.get("usage") or {}).get("total_tokens") is not None for r in sent)
    known = sum((r.get("usage") or {}).get("total_tokens") or 0 for r in sent)
    cost_complete = applicable and all(r.get("estimated_cost_usd") is not None for r in sent)
    return {"applicable": applicable, "model_calls": len(sent), "request_attempts":len(calls),
            "usage_complete": complete, "total_tokens": known if complete else None,
            "known_total_tokens": known,
            "calls_with_unknown_usage": sum((r.get("usage") or {}).get("total_tokens") is None for r in sent),
            "estimated_cost_usd": sum(r["estimated_cost_usd"] for r in sent) if cost_complete else None,
            "inference_seconds": sum(r.get("latency_ms", 0) for r in calls)/1000}


def choose_with_rate_limit_retries(agent, observation, directory, limits, started_at):
    """Retry only explicit HTTP 429 rejections, without executing or consuming an action."""
    for retry in range(agent.config.rate_limit_retries + 1):
        try:
            return agent.choose(observation, directory)
        except APIError as error:
            if error.http_status != 429 or retry == agent.config.rate_limit_retries:
                raise
            delay = max((15, 30, 60)[retry], error.retry_after_seconds or 0)
            # Respect a longer server cooldown by stopping rather than retrying early.
            if delay > 120:
                raise
            if limits.max_model_calls is not None and agent.calls >= limits.max_model_calls:
                raise CapacityError('model_call_budget_exhausted') from error
            if limits.max_observed_tokens is not None:
                # A rejected request's token usage is unknown; do not evade a token cap.
                raise
            if limits.max_wall_seconds is not None and time.monotonic() - started_at + delay >= limits.max_wall_seconds:
                raise CapacityError('wall_budget_exhausted') from error
            append_json(directory / 'private/provider_retries.jsonl', {
                'http_status': 429, 'observation_id': observation['observation_id'],
                'failed_call_index': agent.calls, 'retry_number': retry + 1,
                'delay_seconds': delay, 'same_observation': True, 'action_executed': False})
            # Each choose() writes its own request/error/usage record. During backoff
            # the request marker is inactive; the worker wall/memory guards stay active.
            until = time.monotonic() + delay
            while (remaining := until - time.monotonic()) > 0:
                time.sleep(min(remaining, 30))


def run_one(task_id: str, *, agent_config: AgentConfig | None = None, reference=False,
            output: Path | None = None, limits: Limits | None = None) -> dict:
    limits = limits or Limits()
    task = load_task(task_id)
    if limits.max_decisions is not None:
        task = replace(task, max_decisions=min(task.max_decisions, limits.max_decisions))
    agent = OpenAICompatibleAgent(agent_config) if agent_config is not None else None
    if (agent is None) == (not reference):
        raise ValueError("Select exactly one model configuration or reference policy")
    authored = catalog()[task_id].get("reference") if reference else None
    if reference and (not authored or not authored.get("actions")):
        raise ValueError(f"No executable authored reference for {task_id}")
    require_permissions()
    episode = Episode(task, output)
    write_json(episode.directory / "agent_config.json", {
        "agent":agent.public_config if agent else {"type":"reference"}, "limits":limits.model_dump(), "task_id":task_id})
    start = time.monotonic()
    interrupted = False
    try:
        observation = episode.start()
        meta = json.loads((episode.directory / "run_meta.json").read_text())
        meta.update(agent=agent.public_config if agent else {"type": "reference"},
                    limits=limits.model_dump(), orchestration="serial-local-episode-v1")
        write_json(episode.directory / "run_meta.json", meta)
        write_json(episode.directory / "agent_provenance.json", {
            "type": "openai-compatible-model" if agent else "fixture-author-reference",
            "autonomous_model": agent is not None,
            "observations": ("public screenshot, task, receipts and self-produced history only" if agent else
                             "authored reference input sequence; screenshots are recorded but do not choose actions"),
            "isolation": "shared-development-desktop"})
        if reference and authored.get("viewport") and authored["viewport"] != [observation["image"]["width"], observation["image"]["height"]]:
            raise RuntimeError("Reference viewport does not match the observed window")
        index = 0
        while not observation["ended"]:
            if limits.max_wall_seconds is not None and time.monotonic()-start >= limits.max_wall_seconds:
                episode.abort("wall_budget_exhausted", valid_failure=True); break
            if agent and limits.max_model_calls is not None and agent.calls >= limits.max_model_calls:
                episode.abort("model_call_budget_exhausted", valid_failure=True); break
            if agent and limits.max_observed_tokens is not None:
                usage = usage_summary(episode.directory, applicable=True)
                if usage["known_total_tokens"] >= limits.max_observed_tokens:
                    episode.abort("observed_token_budget_exhausted", valid_failure=True); break
            before = observation
            if agent:
                model_view = {**before, "budget_remaining": dict(before["budget_remaining"])}
                if limits.max_model_calls is not None:
                    model_view["budget_remaining"]["model_calls"] = limits.max_model_calls - agent.calls
                if limits.max_wall_seconds is not None:
                    model_view["budget_remaining"]["wall_seconds"] = max(0, limits.max_wall_seconds - (time.monotonic()-start))
                if limits.max_observed_tokens is not None:
                    used = usage_summary(episode.directory, applicable=True)
                    model_view["budget_remaining"]["observed_tokens"] = max(0, limits.max_observed_tokens-used["known_total_tokens"])
                    model_view["budget_remaining"]["token_usage_complete"] = used["usage_complete"]
                decision = choose_with_rate_limit_retries(agent, model_view, episode.directory, limits, start)
                if limits.max_observed_tokens is not None and decision.record["usage"]["total_tokens"] is None:
                    episode.abort("token_usage_unavailable"); break
                if limits.max_wall_seconds is not None and time.monotonic()-start >= limits.max_wall_seconds:
                    episode.abort("wall_budget_exhausted", valid_failure=True); break
                action = decision.action
                context = {"call_index": decision.record["call_index"], "latency_ms": decision.record["latency_ms"],
                           "usage": decision.record["usage"], "memory": decision.memory,
                           "parse_error": decision.record["parse_error"]}
            else:
                actions = authored["actions"]
                action = actions[index] if index < len(actions) else {"type": "finish"}
                context = {"policy": "reference", "reference_index": index}
            observation = episode.act({"episode_id": episode.id, "action_id": f"decision-{index}",
                "based_on_observation_id": before["observation_id"], "action": action}, agent_context=context)
            if agent:
                agent.remember(before, decision, observation)
            index += 1
    except KeyboardInterrupt:
        interrupted = True
        episode.abort("interrupted")
    except (CapacityError, MemoryError) as error:
        reason = error.reason if isinstance(error, CapacityError) else 'memory_limit_exceeded'
        append_json(episode.private / 'errors.jsonl', {'type':type(error).__name__,'message':reason})
        episode.abort(reason, valid_failure=True)
    except APIError as error:
        append_json(episode.private / "errors.jsonl", {"type": "APIError", "message": str(error)})
        episode.abort("api_error")
    except Exception as error:
        append_json(episode.private / "errors.jsonl", {"type": type(error).__name__, "message": str(error)})
        episode.abort("environment_error")
    finally:
        episode.close()
        usage = usage_summary(episode.directory, applicable=agent is not None)
        write_json(episode.directory / "usage.json", usage)
        meta_path = episode.directory / "run_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text()); meta["model_usage"] = usage
            write_json(meta_path, meta)
        export_replay(episode.directory)
    result = json.loads((episode.directory / "result.json").read_text())
    return {"task_id": task_id, "package": task.package, "game": task.game, "episode_id": episode.id,
            "directory": str(episode.directory), "result": result, "usage": usage, "interrupted": interrupted}


class ExperimentAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    type: Literal["reference", "openai-compatible"]
    config: str | None = None


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "ScreenPlay experiment"
    tasks: list[str] = Field(min_length=1)
    agents: list[ExperimentAgent] = Field(min_length=1)
    repetitions: int = Field(default=1, ge=1, le=1000)
    order_seed: int | None = None
    job_order: Literal['shuffle','paired_rounds'] = 'shuffle'
    limits: Limits = Field(default_factory=Limits)
    stop_on_api_error: bool = True
    stop_on_infrastructure_error: bool = False
    process_guard: ProcessGuard | None = None
    stop_file: str | None = None


def prepare_plan(config_path: Path) -> tuple[dict, dict[str, AgentConfig | None], ExperimentConfig]:
    config = ExperimentConfig.model_validate(json.loads(config_path.read_text()))
    if len(config.tasks) != len(set(config.tasks)) or len({a.id for a in config.agents}) != len(config.agents):
        raise ValueError("Task and agent IDs must be unique; use repetitions for repeated runs")
    all_tasks = catalog()
    missing = [t for t in config.tasks if t not in all_tasks]
    if missing: raise ValueError("Unknown tasks: " + ", ".join(missing))
    agents, public_agents = {}, {}
    for item in config.agents:
        if item.type == "reference":
            if item.config: raise ValueError("Reference policy must not have a model config")
            unavailable = [t for t in config.tasks if not all_tasks[t].get("reference", {}).get("actions")]
            if unavailable: raise ValueError("Tasks without references: " + ", ".join(unavailable))
            agents[item.id] = None
            public_agents[item.id] = {"type": "reference"}
        else:
            if not item.config: raise ValueError("Model agent needs a config file")
            cfg = load_agent_config((config_path.parent / item.config).resolve())
            public, _, _ = cfg.resolve()
            agents[item.id], public_agents[item.id] = cfg, public
    jobs = [{"task_id": task, "agent_id": a.id, "repeat": repeat}
            for a in config.agents for repeat in range(config.repetitions) for task in config.tasks]
    if config.order_seed is not None: random.Random(config.order_seed).shuffle(jobs)
    if config.job_order == 'paired_rounds':
        rng=random.Random(config.order_seed)
        jobs=[]
        for repeat in range(config.repetitions):
            task_order=list(config.tasks);rng.shuffle(task_order)
            for task in task_order:
                agent_order=list(config.agents);rng.shuffle(agent_order)
                jobs.extend({'task_id':task,'agent_id':a.id,'repeat':repeat} for a in agent_order)
    for i, job in enumerate(jobs): job["job_id"] = f"{i:06d}"
    plan = {"schema_version": 1, "name": config.name, "config": config.model_dump(),
            "agents": public_agents, "tasks": {t: all_tasks[t] for t in config.tasks},
            "sources": {p: source_spec(p) for p in {all_tasks[t]["package"] for t in config.tasks}},
            "jobs": jobs, "isolation": "shared-desktop-serial-development"}
    if any(a is not None for a in agents.values()):
        plan["model_system_prompt"] = SYSTEM_PROMPT
    return plan, agents, config


def recover_finished_attempts(output: Path, plan: dict, status: dict):
    """Recover a finalized run if interruption occurred before jobs.json was committed."""
    changed = False
    for job in plan["jobs"]:
        row = status[job["job_id"]]
        known = {a["directory"] for a in row["attempts"]}
        parent = output / "jobs" / job["job_id"]
        for directory in sorted(parent.glob("attempt-*")):
            if str(directory) in known or not (directory/"result.json").exists(): continue
            meta_path = directory/"run_meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            result = json.loads((directory/"result.json").read_text())
            task = load_task(job["task_id"])
            cap = plan["config"]["limits"].get("max_decisions")
            if cap is not None: task = replace(task, max_decisions=min(task.max_decisions,cap))
            if type(result.get("success")) is bool:
                if meta.get("task") != task.public_view() or meta.get("source") != plan["sources"][task.package] or meta.get("agent") != plan["agents"][job["agent_id"]]:
                    raise ValueError("Completed orphan attempt does not match the experiment plan")
            usage_path = directory/"usage.json"
            usage = json.loads(usage_path.read_text()) if usage_path.exists() else usage_summary(
                directory, applicable=plan["agents"][job["agent_id"]]["type"] != "reference")
            entry = {"task_id":job["task_id"],"package":task.package,"game":task.game,
                     "episode_id":meta.get("episode_id"),"directory":str(directory),"result":result,
                     "usage":usage,"interrupted":result.get("stop_reason")=="interrupted","recovered_from_disk":True}
            row["attempts"].append(entry)
            if row["last"] is None or type(row["last"]["result"].get("success")) is not bool:
                row["last"] = entry
            append_json(output/"results.jsonl", {**job, **entry})
            changed = True
    if changed: write_json(output/"jobs.json", status)


def summarize(output: Path, plan: dict, status: dict) -> dict:
    summaries = {}
    for agent_id in plan["agents"]:
        jobs = [j for j in plan["jobs"] if j["agent_id"] == agent_id]
        valid, errors, pending = [], [], []
        for job in jobs:
            last = status[job["job_id"]].get("last")
            if last is None: pending.append(job)
            elif type(last["result"].get("success")) is bool: valid.append((job,last))
            else: errors.append((job,last))
        games, families = {}, {}
        for job,last in valid:
            task = plan["tasks"][job["task_id"]]
            games.setdefault(task["game"], {}).setdefault(job["task_id"], []).append(float(last["result"]["success"]))
            families.setdefault(task["package"], {}).setdefault(job["task_id"], []).append(float(last["result"]["success"]))
        def macro(groups):
            return {name: sum(sum(v)/len(v) for v in tasks.values())/len(tasks) for name,tasks in groups.items()}
        game_rates, family_rates = macro(games), macro(families)
        complete = not errors and not pending
        interrupted = [(job,last) for job,last in errors if last['result'].get('stop_reason') == 'interrupted']
        attempts = [attempt for job in jobs for attempt in status[job["job_id"]]["attempts"]]
        applicable = plan["agents"][agent_id]["type"] != "reference"
        known_tokens = sum(a["usage"]["known_total_tokens"] for a in attempts)
        usage_complete = applicable and all(a["usage"]["usage_complete"] for a in attempts)
        cost_complete = applicable and all(a["usage"]["estimated_cost_usd"] is not None for a in attempts)
        summaries[agent_id] = {"planned":len(jobs), "valid":len(valid), "successes":sum(last["result"]["success"] for _,last in valid),
            "failures":sum(not last["result"]["success"] for _,last in valid), "infrastructure_errors":len(errors)-len(interrupted),
            "operator_interruptions":len(interrupted),
            "pending":len(pending), "complete":complete,
            "stop_reason_counts":dict(Counter(last['result']['stop_reason'] for _,last in valid)),
            "success_rate_completed":sum(last["result"]["success"] for _,last in valid)/len(valid) if valid else None,
            "macro_success_by_game_completed":game_rates, "macro_success_by_family_completed":family_rates,
            "macro_success":sum(game_rates.values())/len(game_rates) if game_rates and complete else None,
            "attempts":len(attempts),
            "infrastructure_error_attempts":sum(type(a["result"].get("success")) is not bool and a['result'].get('stop_reason') != 'interrupted' for a in attempts),
            "operator_interruption_attempts":sum(a['result'].get('stop_reason') == 'interrupted' for a in attempts),
            "model_calls_all_attempts":sum(a["usage"]["model_calls"] for a in attempts),
            "known_total_tokens_all_attempts":known_tokens,
            "total_tokens_all_attempts":known_tokens if usage_complete else None,
            "calls_with_unknown_usage":sum(a["usage"]["calls_with_unknown_usage"] for a in attempts),
            "estimated_cost_usd_all_attempts":sum(a["usage"]["estimated_cost_usd"] for a in attempts) if cost_complete else None}
    report = {"name":plan["name"], "updated_at":datetime.now(timezone.utc).isoformat(),
              "complete":all(a["complete"] for a in summaries.values()), "agents":summaries,
              "score_note":"Macro scores require all planned jobs to have valid results; infrastructure errors and operator interruptions remain unscored."}
    write_json(output / "summary.json", report)
    rows = []
    for job in plan["jobs"]:
        last = status[job["job_id"]].get("last")
        if last:
            result = last["result"]
            label = "成功" if result.get("success") is True else "未完成" if result.get("success") is False else "人工中断" if result.get('stop_reason') == 'interrupted' else "环境/API 故障"
            link = Path(last["directory"]).relative_to(output) / "replay.html"
            replay = f'<a href="{html.escape(str(link), quote=True)}">回放</a>'
            decisions = str(result["decisions"])
        else:
            label, replay, decisions = "待运行", "", "—"
        attempts = []
        for number, attempt in enumerate(status[job["job_id"]]["attempts"],1):
            path = Path(attempt["directory"]).relative_to(output)/"replay.html"
            attempts.append(f'<a href="{html.escape(str(path),quote=True)}">{number}</a>')
        rows.append("<tr>"+"".join(f"<td>{html.escape(str(x))}</td>" for x in [job["agent_id"], job["task_id"], job["repeat"], label, decisions])+f"<td>{replay}</td><td>{' · '.join(attempts)}</td></tr>")
    document = '<!doctype html><meta charset="utf-8"><title>ScreenPlay 批量运行</title><style>body{font:16px system-ui;max-width:1150px;margin:40px auto;padding:0 24px;color:#17212b}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap;background:#eee;padding:18px}a{color:#175ab2}</style><h1>'+html.escape(plan["name"])+'</h1><p>共享开发桌面串行运行。参考操作不代表模型成绩。未完成计划或存在基础设施故障时，不发布完整宏平均分数。</p><pre>'+html.escape(json.dumps(report["agents"],ensure_ascii=False,indent=2))+'</pre><table><tr><th>Agent</th><th>任务</th><th>重复编号</th><th>结果</th><th>动作数</th><th>记录</th><th>所有尝试</th></tr>'+''.join(rows)+'</table>'
    (output / "report.html").write_text(document)
    return report


def run_batch(config_path: Path, output: Path, *, resume=False, max_jobs: int | None = None) -> dict:
    plan, agents, config = prepare_plan(config_path.resolve())
    require_permissions()
    output = output.resolve()
    if not resume:
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_json(output / "plan.json", plan)
        status = {j["job_id"]:{"attempts":[], "last":None} for j in plan["jobs"]}
        write_json(output / "jobs.json", status)
    else:
        if json.loads((output / "plan.json").read_text()) != plan:
            raise ValueError("Resume configuration, task definitions or source versions changed; use a new output directory")
    with (output / ".batch.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = json.loads((output / "jobs.json").read_text())
        if resume: recover_finished_attempts(output, plan, status)
        count = 0
        summarize(output, plan, status)
        for job in plan["jobs"]:
            if config.stop_file and (config_path.resolve().parent / config.stop_file).exists():
                break
            row = status[job["job_id"]]
            if row["last"] and type(row["last"]["result"].get("success")) is bool:
                continue
            if max_jobs is not None and count >= max_jobs: break
            parent = output / "jobs" / job["job_id"]
            parent.mkdir(parents=True, exist_ok=True)
            attempt = 1
            while (parent / f"attempt-{attempt:03d}").exists(): attempt += 1
            directory = parent / f"attempt-{attempt:03d}"
            arguments = dict(agent_config=agents[job['agent_id']],reference=agents[job['agent_id']] is None,
                             output=directory,limits=config.limits)
            entry = (run_guarded(job['task_id'],**arguments,guard=config.process_guard) if config.process_guard
                     else run_one(job['task_id'],**arguments))
            row["attempts"].append(entry); row["last"] = entry
            append_json(output / "results.jsonl", {**job, "attempt":attempt, **entry})
            write_json(output / "jobs.json", status)
            report = summarize(output, plan, status)
            count += 1
            print(json.dumps({"job":job["job_id"], "task":job["task_id"], "agent":job["agent_id"],
                              "result":entry["result"]}, ensure_ascii=False), flush=True)
            if entry["interrupted"] or (config.stop_on_api_error and entry["result"]["stop_reason"] == "api_error"):
                break
            if config.stop_on_infrastructure_error and type(entry['result'].get('success')) is not bool:
                break
        return {"directory":str(output), **summarize(output, plan, status)}
