"""Per-episode process isolation and external resource watchdog for long histories."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from pydantic import BaseModel, ConfigDict, Field


class ProcessGuard(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_worker_rss_mb: int = Field(default=2048, ge=32)
    hard_wall_seconds: float = Field(default=3900, gt=0)
    poll_seconds: float = Field(default=1, ge=.05, le=5)


def worker_rss_mb(pid: int) -> float:
    result = subprocess.run(['ps','-o','rss=','-p',str(pid)], capture_output=True, text=True, timeout=3)
    if not result.stdout.strip():
        if result.stderr.strip(): raise RuntimeError('Cannot read worker memory usage')
        return 0.0  # Already exited.
    return int(result.stdout.strip()) / 1024


def terminate_group(process: subprocess.Popen):
    """Only the dedicated session created for this known child is targeted."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try: os.killpg(process.pid, sig)
        except ProcessLookupError: break
        if sig == signal.SIGTERM:
            # Allow the worker and native children a short cleanup window.
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
            time.sleep(.1)
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired: pass


def watch(process: subprocess.Popen, directory: Path, guard: ProcessGuard) -> dict:
    start = time.monotonic()
    peak = 0.0
    while process.poll() is None:
        now = time.monotonic()
        peak = max(peak, worker_rss_mb(process.pid))
        reason = None
        if peak > guard.max_worker_rss_mb:
            reason = 'worker_memory_limit'
        elif now-start > guard.hard_wall_seconds:
            reason = 'worker_wall_timeout'
        marker = directory/'private/model_call_active.json'
        if reason is None and marker.exists():
            active = json.loads(marker.read_text())
            if active.get('active') and now > active['deadline_monotonic'] + 2:
                reason = 'request_timeout'
        if reason:
            terminate_group(process)
            return {'failure_reason':reason, 'peak_worker_rss_mb':peak,
                    'wall_seconds':round(time.monotonic()-start,3), 'exit_code':process.poll()}
        time.sleep(guard.poll_seconds)
    return {'failure_reason':None, 'peak_worker_rss_mb':peak,
            'wall_seconds':round(time.monotonic()-start,3), 'exit_code':process.returncode}


def _fallback_result(task_id, directory, reason, agent_config, wall_seconds, *, scored=True):
    from .experiments import usage_summary
    from .runner import write_json, append_json
    from .tasks import load_task
    from .build import source_spec
    task = load_task(task_id)
    directory.mkdir(parents=True, exist_ok=True)
    private = directory/'private'; private.mkdir(exist_ok=True)
    marker = private/'model_call_active.json'
    if marker.exists():
        active = json.loads(marker.read_text())
        calls_path = directory/'model_calls.jsonl'
        calls = [json.loads(x) for x in calls_path.read_text().splitlines()] if calls_path.exists() else []
        if active.get('active') and not any(c['call_index']==active['call_index'] for c in calls):
            append_json(calls_path, {'call_index':active['call_index'], 'observation_id':active['observation_id'],
                                     'status':'worker_terminated', 'failure_reason':reason,
                                     'request_sent':active.get('request_sent'), 'usage':None,
                                     'estimated_cost_usd':None,
                                     'latency_ms':round((time.monotonic()-active['started_monotonic'])*1000,3)})
        write_json(marker, {'active':False, 'terminated_by_watchdog':True})
    interactions = directory/'interactions.jsonl'
    decisions = sum(1 for _ in interactions.open()) if interactions.exists() else 0
    result = {'success':False if scored else None, 'score':0.0 if scored else None,
              'stop_reason':reason, 'decisions':decisions, 'wall_seconds':wall_seconds}
    previous = directory/'result.json'
    if previous.exists():
        write_json(private/'result_before_worker_failure.json', json.loads(previous.read_text()))
    write_json(previous, result)
    append_json(private/'errors.jsonl', {'type':'ProcessWatchdog', 'message':reason})
    # Preserve all existing images. Avoid rebuilding a large inline replay after OOM.
    (directory/'replay.html').write_text('<!doctype html><meta charset="utf-8"><title>Episode stopped</title>'
        '<h1>Episode stopped by resource watchdog</h1><p>'+reason+'</p>'
        '<p><a href="result.json">Result</a> · <a href="interactions.jsonl">Actions</a> · '
        '<a href="frames/">Recorded frames</a></p>')
    usage = usage_summary(directory, applicable=agent_config is not None)
    write_json(directory/'usage.json', usage)
    meta_path = directory/'run_meta.json'
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    else:
        meta = {'episode_id':None,'task':task.public_view(),'source':source_spec(task.package),
                'agent':agent_config.resolve()[0] if agent_config else {'type':'reference'},
                'isolation':'shared-desktop-development-only','orchestration':'external-process-watchdog'}
        write_json(meta_path,meta)
    return {'task_id':task_id, 'package':task.package, 'game':task.game,
            'episode_id':meta.get('episode_id'), 'directory':str(directory), 'result':result,
            'usage':usage, 'interrupted':not scored and reason=='interrupted'}


def run_guarded(task_id, *, agent_config=None, reference=False, output, limits, guard):
    from .runner import write_json
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    spec_path = output.parent/f'.{output.name}.worker-input.json'
    result_path = output.parent/f'.{output.name}.worker-result.json'
    spec = {'task_id':task_id, 'agent_config':agent_config.model_dump() if agent_config else None,
            'reference':reference, 'output':str(output), 'limits':limits.model_dump(),
            'result_path':str(result_path)}
    write_json(spec_path, spec)  # Config includes environment variable names, never the API key.
    with (output.parent/f'.{output.name}.worker.log').open('w') as log:
        process = subprocess.Popen([sys.executable,'-m','screenplay.guarded','--worker',str(spec_path)],
                                   start_new_session=True, stdout=log, stderr=log)
        try:
            outcome = watch(process, output, guard)
        except KeyboardInterrupt:
            terminate_group(process)
            entry = _fallback_result(task_id,output,'interrupted',agent_config,0,scored=False)
            return entry
        except Exception:
            terminate_group(process)
            return _fallback_result(task_id,output,'watchdog_error',agent_config,0,scored=False)
        finally:
            terminate_group(process)
    if outcome['failure_reason']:
        entry = _fallback_result(task_id,output,outcome['failure_reason'],agent_config,outcome['wall_seconds'])
    elif result_path.exists():
        payload = json.loads(result_path.read_text())
        if 'entry' in payload:
            entry = payload['entry']
        elif payload.get('error_type')=='MemoryError':
            entry = _fallback_result(task_id,output,'memory_limit_exceeded',agent_config,outcome['wall_seconds'])
        else:
            entry = _fallback_result(task_id,output,'worker_setup_error',agent_config,outcome['wall_seconds'],scored=False)
    else:
        # SIGKILL may be the OS OOM killer, but we do not assert that without evidence.
        entry = _fallback_result(task_id,output,'worker_abnormal_exit',agent_config,outcome['wall_seconds'])
    entry['process_guard'] = outcome
    write_json(output/'private/process_guard.json', outcome)
    return entry


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--worker',type=Path,required=True)
    args=parser.parse_args(); spec=json.loads(args.worker.read_text())
    from .agents import AgentConfig
    from .experiments import Limits,run_one
    from .runner import write_json
    try:
        entry=run_one(spec['task_id'],agent_config=AgentConfig.model_validate(spec['agent_config']) if spec['agent_config'] else None,
                      reference=spec['reference'],output=Path(spec['output']),limits=Limits.model_validate(spec['limits']))
        write_json(Path(spec['result_path']),{'entry':entry})
    except Exception as error:
        # Do not emit configuration or environment values into worker errors.
        write_json(Path(spec['result_path']),{'error_type':type(error).__name__})
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
