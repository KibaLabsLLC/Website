#!/usr/bin/env python3
"""Collect Kiba Labs build status from CircleCI and GitHub into status.json.

Public CircleCI projects and public GitHub repositories can be read without
credentials. Set GITHUB_TOKEN and/or CIRCLECI_TOKEN in the environment to raise
rate limits; tokens are never written to the output.

Run from anywhere: python3 scripts/fetch_status.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'status.json'
USER_AGENT = 'kibaos-status/1.0 (+https://kibaos.com/status.html)'

# Projects watched by the status page.
CIRCLE_PROJECTS = ['KibaLabsLLC/KibaOS']
GITHUB_REPOS = ['KibaLabsLLC/KibaOS', 'KibaLabsLLC/Lumen', 'KibaLabsLLC/Website']
DEFAULT_BRANCH = 'main'
PRIMARY_REPO = 'KibaLabsLLC/KibaOS'

CIRCLE_PIPELINES_TO_READ = 8
GITHUB_RUNS_PER_REPO = 20
RUNS_IN_OUTPUT = 24
FAILURE_WINDOW_DAYS = 7
RECENT_WINDOW_HOURS = 24

CIRCLE_STATUS = {
    'success': 'success',
    'failed': 'failed',
    'failing': 'failed',
    'error': 'failed',
    'infrastructure_fail': 'failed',
    'timedout': 'failed',
    'unauthorized': 'failed',
    'canceled': 'canceled',
    'cancelled': 'canceled',
    'running': 'running',
    'on_hold': 'on_hold',
    'queued': 'queued',
    'not_run': 'skipped',
    'skipped': 'skipped',
    'not_running': 'skipped',
}

GITHUB_CONCLUSION = {
    'success': 'success',
    'failure': 'failed',
    'timed_out': 'failed',
    'startup_failure': 'failed',
    'action_required': 'failed',
    'cancelled': 'canceled',
    'skipped': 'skipped',
    'neutral': 'skipped',
    'stale': 'skipped',
}

GITHUB_STATUS = {
    'completed': None,
    'in_progress': 'running',
    'queued': 'queued',
    'waiting': 'queued',
    'requested': 'queued',
    'pending': 'queued',
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def iso(value):
    if not value:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')


def seconds_between(start, end):
    if not start or not end:
        return None
    delta = (end - start).total_seconds()
    return int(delta) if delta >= 0 else None


def http_json(url, headers):
    request = urllib.request.Request(url, headers={'Accept': 'application/json',
                                                  'User-Agent': USER_AGENT,
                                                  **headers})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def circle_headers():
    token = os.environ.get('CIRCLECI_TOKEN') or os.environ.get('CIRCLE_TOKEN')
    return {'Authorization': 'Bearer %s' % token} if token else {}


def github_headers():
    token = os.environ.get('GITHUB_TOKEN')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer %s' % token
    return headers


def repo_name(slug):
    return slug.rsplit('/', 1)[-1]


def base_run(provider, repo, workflow):
    return {
        'provider': provider,
        'repo': repo,
        'repo_name': repo_name(repo),
        'workflow': workflow,
        'build': None,
        'branch': None,
        'commit': None,
        'message': None,
        'status': 'unknown',
        'started_at': None,
        'finished_at': None,
        'duration_s': None,
        'url': None,
        'is_default_branch': False,
    }


def collect_circleci():
    """Return (runs, detail) for the configured CircleCI projects."""
    runs = []
    for slug in CIRCLE_PROJECTS:
        project_url = ('https://circleci.com/api/v2/project/gh/%s/pipeline'
                       % slug)
        pipelines = http_json(project_url, circle_headers()).get('items', [])
        for pipeline in pipelines[:CIRCLE_PIPELINES_TO_READ]:
            pipeline_id = pipeline.get('id')
            number = pipeline.get('number')
            vcs = pipeline.get('vcs') or {}
            branch = vcs.get('branch')
            revision = vcs.get('revision') or ''
            commit_message = (vcs.get('commit') or {}).get('subject') if isinstance(vcs.get('commit'), dict) else None
            if not pipeline_id:
                continue
            try:
                workflows = http_json('https://circleci.com/api/v2/pipeline/%s/workflow' % pipeline_id,
                                      circle_headers()).get('items', [])
            except urllib.error.HTTPError:
                continue
            for workflow in workflows:
                started = parse_time(workflow.get('created_at'))
                stopped = parse_time(workflow.get('stopped_at'))
                raw_status = (workflow.get('status') or '').lower()
                run = base_run('circleci', slug, workflow.get('name') or 'workflow')
                run.update({
                    'build': '#%s' % number if number is not None else None,
                    'branch': branch,
                    'commit': revision[:7] or None,
                    'message': (commit_message or '').strip()[:120] or None,
                    'status': CIRCLE_STATUS.get(raw_status, 'unknown'),
                    'status_raw': workflow.get('status'),
                    'started_at': iso(started),
                    'finished_at': iso(stopped),
                    'duration_s': seconds_between(started, stopped),
                    'url': ('https://app.circleci.com/pipelines/github/%s/%s/workflows/%s'
                            % (slug, number, workflow.get('id'))),
                    'is_default_branch': branch == DEFAULT_BRANCH,
                })
                runs.append(run)
    detail = 'CircleCI project %s' % ', '.join(CIRCLE_PROJECTS)
    return runs, detail


def collect_github():
    """Return (runs, detail) for the configured GitHub repositories."""
    runs = []
    for slug in GITHUB_REPOS:
        payload = http_json('https://api.github.com/repos/%s/actions/runs?per_page=%d'
                            % (slug, GITHUB_RUNS_PER_REPO), github_headers())
        for item in payload.get('workflow_runs', []):
            finished = parse_time(item.get('updated_at')) if item.get('status') == 'completed' else None
            started = parse_time(item.get('run_started_at') or item.get('created_at'))
            raw_status = (item.get('status') or '').lower()
            if item.get('status') == 'completed':
                status = GITHUB_CONCLUSION.get((item.get('conclusion') or '').lower(), 'unknown')
            else:
                status = GITHUB_STATUS.get(raw_status, 'unknown') or 'unknown'
            branch = item.get('head_branch')
            commit = item.get('head_sha') or ''
            run = base_run('github', slug, item.get('name') or 'workflow')
            run.update({
                'build': '#%s' % item.get('run_number') if item.get('run_number') else None,
                'branch': branch,
                'commit': commit[:7] or None,
                'message': ((item.get('head_commit') or {}).get('message') or '').splitlines()[0][:120] or None,
                'status': status,
                'status_raw': item.get('conclusion') or item.get('status'),
                'started_at': iso(started),
                'finished_at': iso(finished),
                'duration_s': seconds_between(started, finished),
                'url': item.get('html_url'),
                'is_default_branch': branch == DEFAULT_BRANCH,
            })
            runs.append(run)
    detail = 'repositories %s' % ', '.join(GITHUB_REPOS)
    return runs, detail


def sort_key(run):
    stamp = parse_time(run.get('started_at'))
    return stamp or datetime.min.replace(tzinfo=timezone.utc)


def overall_state(pipelines, sources):
    ok_sources = [s for s in sources if s['ok']]
    if not ok_sources:
        return 'unknown'
    failing = [p for p in pipelines if p['is_default_branch'] and p['status'] == 'failed']
    if failing:
        return 'degraded'
    if len(ok_sources) != len(sources):
        return 'partial'
    return 'operational'


def summarise(pipelines, sources, state, generated):
    if state == 'unknown':
        return ('Build data unavailable',
                'Neither CircleCI nor GitHub could be reached for this update.')
    failing = [p for p in pipelines if p['is_default_branch'] and p['status'] == 'failed']
    if state == 'degraded':
        names = ', '.join('%s (%s)' % (p['workflow'], p['repo_name']) for p in failing[:3])
        if len(failing) > 3:
            names += ' and %d more' % (len(failing) - 3)
        return ('Build failing on main',
                'Failing now: %s. Every other workflow is green.' % names)
    if state == 'partial':
        down = ', '.join(s['name'] for s in sources if not s['ok'])
        return ('Pipelines operational',
                'No workflow is failing on main. %s data is unavailable for this update.' % down)
    return ('All pipelines operational',
            'No workflow is failing on main. Last update %s UTC.'
            % generated.strftime('%d %B %Y, %H:%M'))


def collect_stats(runs, generated):
    completed = [r for r in runs if r['status'] in ('success', 'failed') and r['finished_at']]
    since = generated - timedelta(hours=RECENT_WINDOW_HOURS)
    recent = [r for r in completed if (parse_time(r['finished_at']) or since) >= since]
    passed = [r for r in recent if r['status'] == 'success']
    durations = [r['duration_s'] for r in completed if r['duration_s']]
    greens = [r for r in completed if r['status'] == 'success' and r['is_default_branch']]
    primary_greens = [r for r in greens if r['repo'] == PRIMARY_REPO]
    if primary_greens:
        greens = primary_greens
    latest_green = None
    if greens:
        best = max(greens, key=lambda r: parse_time(r['finished_at']) or sort_key(r))
        latest_green = {
            'repo': best['repo'],
            'workflow': best['workflow'],
            'build': best['build'],
            'commit': best['commit'],
            'finished_at': best['finished_at'],
            'url': best['url'],
        }
    return {
        'runs_passed_24h': {'passed': len(passed), 'total': len(recent)},
        'median_duration_s': int(statistics.median(durations)) if durations else None,
        'latest_green': latest_green,
    }


def collect_incidents(runs, generated):
    """Group consecutive failures on the default branch into incidents."""
    cutoff = generated - timedelta(days=FAILURE_WINDOW_DAYS)
    groups = {}
    for run in sorted(runs, key=sort_key):
        if not run['is_default_branch'] or run['status'] not in ('success', 'failed'):
            continue
        groups.setdefault((run['provider'], run['repo'], run['workflow']), []).append(run)

    incidents = []
    for (provider, repo, workflow), history in groups.items():
        streak = []
        for run in history + [None]:
            if run is not None and run['status'] == 'failed':
                streak.append(run)
                continue
            if streak:
                first = streak[0]
                last = streak[-1]
                recovered = run if (run is not None and run['status'] == 'success') else None
                when = parse_time(first['started_at']) or cutoff
                if when >= cutoff:
                    incidents.append({
                        'state': 'resolved' if recovered else 'ongoing',
                        'provider': provider,
                        'repo': repo,
                        'repo_name': repo_name(repo),
                        'workflow': workflow,
                        'failed_runs': len(streak),
                        'first_failure_at': first['started_at'],
                        'last_failure_at': last['finished_at'] or last['started_at'],
                        'resolved_at': recovered['finished_at'] if recovered else None,
                        'commit': last['commit'],
                        'message': last['message'],
                        'url': last['url'],
                        'branch': last['branch'],
                    })
                streak = []
    incidents.sort(key=lambda i: parse_time(i['last_failure_at']) or cutoff, reverse=True)
    return incidents[:4]


def write_if_changed(payload):
    """Write status.json only when the results differ from the file on disk.

    generated_at moves on every run, so it is excluded from the comparison;
    an unchanged result therefore leaves the file (and git) untouched instead
    of producing a bot commit every 15 minutes.
    """
    previous = None
    if OUTPUT.exists():
        try:
            previous = json.loads(OUTPUT.read_text(encoding='utf-8'))
        except ValueError:
            previous = None
    if isinstance(previous, dict):
        current = dict(payload)
        existing = dict(previous)
        current.pop('generated_at', None)
        existing.pop('generated_at', None)
        if current == existing:
            print('no changes: results are identical, status.json left untouched')
            return False
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=False) + '\n', encoding='utf-8')
    return True


def main():
    generated = now_utc()
    sources = []
    runs = []

    for name, collector, url in (
        ('CircleCI', collect_circleci, 'https://app.circleci.com/pipelines/github/KibaLabsLLC'),
        ('GitHub Actions', collect_github, 'https://github.com/KibaLabsLLC'),
    ):
        try:
            collected, detail = collector()
            runs.extend(collected)
            sources.append({'name': name, 'ok': True, 'detail': detail, 'url': url})
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
            detail = 'request failed: %s' % (error,)
            print('warning: %s %s' % (name, detail), file=sys.stderr)
            sources.append({'name': name, 'ok': False, 'detail': detail, 'url': url})

    runs.sort(key=sort_key, reverse=True)

    # One card per workflow: prefer its newest run on the default branch, so a
    # red pull-request run does not make a healthy main branch look broken.
    latest = {}
    for run in runs:
        key = (run['provider'], run['repo'], run['workflow'])
        if key not in latest:
            latest[key] = run
        elif run['is_default_branch'] and not latest[key]['is_default_branch']:
            latest[key] = run
    pipelines = sorted(latest.values(), key=sort_key, reverse=True)

    state = overall_state(pipelines, sources)
    title, summary = summarise(pipelines, sources, state, generated)

    payload = {
        'version': 1,
        'generated_at': iso(generated),
        'generator': 'scripts/fetch_status.py',
        'overall': {'state': state, 'title': title, 'summary': summary},
        'sources': sources,
        'stats': collect_stats(runs, generated),
        'pipelines': pipelines,
        'runs': runs[:RUNS_IN_OUTPUT],
        'incidents': collect_incidents(runs, generated),
    }

    changed = write_if_changed(payload)
    print('%s %s: %d pipeline(s), %d run(s), %d incident(s), state=%s'
          % ('wrote' if changed else 'kept', OUTPUT.name, len(payload['pipelines']),
             len(payload['runs']), len(payload['incidents']), state))


if __name__ == '__main__':
    main()
