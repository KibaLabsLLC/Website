(function () {
  'use strict';

  // status.json is only rewritten when results change, so a long gap between
  // updates is normal. Only flag it after a week.
  var STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;
  var UTC = { timeZone: 'UTC' };

  var STATUS = {
    success: { label: 'Passed', tone: 'ok' },
    failed: { label: 'Failed', tone: 'fail' },
    running: { label: 'Running', tone: 'busy' },
    queued: { label: 'Queued', tone: 'busy' },
    on_hold: { label: 'On hold', tone: 'busy' },
    canceled: { label: 'Canceled', tone: 'busy' },
    skipped: { label: 'Skipped', tone: 'busy' },
    unknown: { label: 'Unknown', tone: 'busy' }
  };

  var OVERALL_TONE = { operational: 'ok', degraded: 'fail', partial: 'busy', unknown: 'fail' };
  var PROVIDER = { circleci: 'CircleCI', github: 'GitHub Actions' };

  function node(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function setText(selector, text, root) {
    var target = (root || document).querySelector(selector);
    if (target) target.textContent = text;
  }

  function pill(status) {
    var meta = STATUS[status] || STATUS.unknown;
    return node('span', 'status-pill status-pill--' + meta.tone, meta.label);
  }

  function tonePill(tone, label) {
    return node('span', 'status-pill status-pill--' + tone, label);
  }

  function provider(run) {
    return PROVIDER[run.provider] || run.provider;
  }

  function fmtDuration(seconds) {
    if (!seconds && seconds !== 0) return '—';
    var total = Math.round(seconds);
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var secs = total % 60;
    if (hours) return hours + 'h ' + minutes + 'm';
    if (minutes) return minutes + 'm ' + secs.toString().padStart(2, '0') + 's';
    return secs + 's';
  }

  function fmtWhen(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (isNaN(date)) return '—';
    var day = new Intl.DateTimeFormat('en-GB', Object.assign({ day: '2-digit', month: 'short' }, UTC)).format(date);
    var time = new Intl.DateTimeFormat('en-GB', Object.assign({ hour: '2-digit', minute: '2-digit', hour12: false }, UTC)).format(date);
    return day + ', ' + time + ' UTC';
  }

  function fmtDay(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (isNaN(date)) return '—';
    return new Intl.DateTimeFormat('en-GB', Object.assign({ day: 'numeric', month: 'long', year: 'numeric' }, UTC)).format(date);
  }

  function relative(value) {
    var stamp = new Date(value).getTime();
    if (isNaN(stamp)) return 'unknown';
    var diff = Math.max(0, Date.now() - stamp) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) {
      var minutes = Math.round(diff / 60);
      return minutes + (minutes === 1 ? ' minute ago' : ' minutes ago');
    }
    if (diff < 86400) {
      var hours = Math.round(diff / 3600);
      return hours + (hours === 1 ? ' hour ago' : ' hours ago');
    }
    var days = Math.round(diff / 86400);
    return days + (days === 1 ? ' day ago' : ' days ago');
  }

  function cardValue(label, value, mono) {
    var item = node('li');
    item.appendChild(node('span', '', label));
    item.appendChild(node('span', 'status-card__val' + (mono ? ' mono' : ''), value));
    return item;
  }

  function pipelineCard(run) {
    var card = node('article', 'status-card');
    var head = node('div', 'status-card__head');
    var titles = node('div');
    titles.appendChild(node('h3', 'status-card__name', run.workflow));
    titles.appendChild(node('p', 'status-card__repo', run.repo_name + ' · ' + provider(run)));
    head.appendChild(titles);
    head.appendChild(pill(run.status));
    card.appendChild(head);

    var rows = node('ul', 'status-card__rows');
    rows.appendChild(cardValue('Last build', run.build || '—'));
    rows.appendChild(cardValue('Branch', run.branch || '—', true));
    rows.appendChild(cardValue('Commit', run.commit || '—', true));
    rows.appendChild(cardValue('Duration', fmtDuration(run.duration_s)));
    rows.appendChild(cardValue('Finished', run.finished_at ? fmtWhen(run.finished_at) : 'in progress'));
    card.appendChild(rows);

    if (run.url) {
      var link = node('a', 'status-card__link', 'Open run');
      link.href = run.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      card.appendChild(link);
    }
    return card;
  }

  function cell(text, className) {
    var td = node('td');
    if (className === 'code') {
      td.appendChild(node('code', '', text || '—'));
    } else {
      td.textContent = text || '—';
    }
    return td;
  }

  function buildRow(run) {
    var row = node('tr');
    var head = node('th');
    head.scope = 'row';
    head.appendChild(node('span', 'build-table__name', run.workflow));
    head.appendChild(node('span', 'build-table__repo', run.repo_name + ' · ' + provider(run)));
    if (run.message) head.title = run.message;
    row.appendChild(head);
    row.appendChild(cell(run.branch, 'code'));
    row.appendChild(cell(run.commit, 'code'));
    var result = node('td');
    result.appendChild(pill(run.status));
    row.appendChild(result);
    row.appendChild(cell(fmtDuration(run.duration_s)));
    row.appendChild(cell(run.finished_at ? fmtWhen(run.finished_at) : '—'));
    return row;
  }

  function incidentItem(incident) {
    var item = node('li');
    item.setAttribute('data-state', incident.state === 'ongoing' ? 'bad' : 'ok');

    var time = node('time');
    if (incident.first_failure_at) time.dateTime = incident.first_failure_at;
    time.textContent = fmtDay(incident.last_failure_at || incident.first_failure_at);
    item.appendChild(time);

    var branch = incident.branch || 'main';
    var title = incident.failed_runs > 1
      ? incident.workflow + ' failed ' + incident.failed_runs + ' times on ' + branch
      : incident.workflow + ' failed on ' + branch;
    item.appendChild(node('h3', '', title));

    var detail = [
      incident.repo_name + ' · ' + (PROVIDER[incident.provider] || incident.provider),
      'First failure ' + fmtWhen(incident.first_failure_at) + '.'
    ];
    if (incident.resolved_at) {
      detail.push('Recovered ' + fmtWhen(incident.resolved_at) + '.');
    } else {
      detail.push('Still failing as of this snapshot.');
    }
    if (incident.commit) detail.push('Latest failed commit ' + incident.commit + '.');
    item.appendChild(node('p', '', detail.join(' ')));

    if (incident.url) {
      var link = node('a', '', 'Open the failed run');
      link.href = incident.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      var line = node('p');
      line.appendChild(link);
      item.appendChild(line);
    }

    item.appendChild(incident.state === 'ongoing'
      ? tonePill('fail', 'Ongoing')
      : tonePill('ok', 'Resolved'));
    return item;
  }

  function statList(selector, rows) {
    var list = document.querySelector(selector);
    if (!list) return;
    list.textContent = '';
    rows.forEach(function (row) {
      var item = node('li');
      item.appendChild(node('span', 'status-stats__label', row.label));
      item.appendChild(node('span', 'status-stats__value', row.value));
      item.appendChild(node('span', 'status-stats__note', row.note));
      list.appendChild(item);
    });
  }

  function summaryIcon(state) {
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2.4');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    var path = document.createElementNS(ns, 'path');
    if (state === 'operational') {
      path.setAttribute('d', 'M4 12.5 9.5 18 20 6.5');
    } else if (state === 'degraded') {
      path.setAttribute('d', 'M12 4.5v9.5M12 18.5v.5');
    } else {
      path.setAttribute('d', 'M12 5a7 7 0 1 0 .01 0M12 8.5v3.5M12 15.5v.5');
    }
    svg.appendChild(path);
    return svg;
  }

  function renderSources(data) {
    var note = document.querySelector('[data-status-sources]');
    if (!note) return;
    var parts = data.sources.map(function (source) {
      return source.name + (source.ok ? ' reachable' : ' unavailable');
    });
    var text = 'Sources: ' + parts.join(' · ') + '. Generated ' + relative(data.generated_at)
      + ' by scripts/fetch_status.py.';
    var age = Date.now() - new Date(data.generated_at).getTime();
    if (age > STALE_AFTER_MS) {
      var days = Math.round(age / 86400000);
      text += ' The results have not changed in ' + days + ' days; check that the scheduled refresh is still running.';
    }
    note.textContent = text;
  }

  function render(data) {
    var state = (data.overall && data.overall.state) || 'unknown';
    var tone = OVERALL_TONE[state] || 'busy';

    var overall = document.querySelector('[data-status-overall]');
    if (overall) {
      overall.className = 'status-pill status-pill--' + tone;
      overall.textContent = (data.overall && data.overall.title) || 'Build status';
    }

    var updated = document.querySelector('[data-status-updated]');
    if (updated) {
      updated.textContent = '';
      if (data.generated_at) {
        var time = node('time');
        time.dateTime = data.generated_at;
        time.textContent = relative(data.generated_at);
        updated.appendChild(document.createTextNode('CircleCI + GitHub Actions, updated '));
        updated.appendChild(time);
      } else {
        updated.textContent = 'CircleCI + GitHub Actions';
      }
    }

    var dot = document.querySelector('[data-status-dot]');
    if (dot) {
      dot.className = 'status-summary__dot status-summary__dot--' + tone;
      dot.textContent = '';
      dot.appendChild(summaryIcon(state));
    }

    setText('[data-status-summary-title]', (data.overall && data.overall.title) || 'Build status');
    setText('[data-status-summary-lede]', (data.overall && data.overall.summary) || '');

    var stats = data.stats || {};
    var recent = stats.runs_passed_24h || {};
    var green = stats.latest_green;
    statList('[data-status-stats]', [
      {
        label: 'Runs passed (24h)',
        value: recent.total ? recent.passed + ' / ' + recent.total : '—',
        note: recent.total ? 'workflow runs that finished' : 'no run finished in the last 24 hours'
      },
      {
        label: 'Median run',
        value: fmtDuration(stats.median_duration_s),
        note: 'completed CircleCI workflows and Actions runs'
      },
      {
        label: 'Latest green build',
        value: green ? (green.build || green.commit || '—') : '—',
        note: green ? green.workflow + ' · ' + green.repo.split('/').pop() + ', ' + fmtWhen(green.finished_at) : 'no successful run on main yet'
      }
    ]);

    var grid = document.querySelector('#pipeline-grid');
    if (grid) {
      grid.textContent = '';
      var pipelines = data.pipelines || [];
      if (!pipelines.length) {
        var empty = node('article', 'status-card status-card--placeholder');
        empty.appendChild(node('p', '', 'No workflow runs found in the last update.'));
        empty.appendChild(node('p', 'status-card__hint', 'CircleCI and GitHub Actions have the current state.'));
        grid.appendChild(empty);
      } else {
        pipelines.forEach(function (run) { grid.appendChild(pipelineCard(run)); });
      }
    }

    var body = document.querySelector('#builds-body');
    if (body) {
      body.textContent = '';
      var runs = (data.runs || []).slice(0, 8);
      if (!runs.length) {
        var row = node('tr');
        var emptyCell = node('td', '', 'No runs were returned by CircleCI or GitHub in this update.');
        emptyCell.colSpan = 6;
        row.appendChild(emptyCell);
        body.appendChild(row);
      } else {
        runs.forEach(function (run) { body.appendChild(buildRow(run)); });
      }
    }

    var timeline = document.querySelector('#incident-list');
    if (timeline) {
      timeline.textContent = '';
      var incidents = data.incidents || [];
      if (!incidents.length) {
        var quiet = node('li');
        quiet.setAttribute('data-state', 'ok');
        quiet.appendChild(node('h3', '', 'No failed runs on main in the last seven days.'));
        quiet.appendChild(node('p', '', 'Consecutive failures are grouped here automatically, with the run that recovered them.'));
        quiet.appendChild(tonePill('ok', 'Nothing to report'));
        timeline.appendChild(quiet);
      } else {
        incidents.forEach(function (incident) { timeline.appendChild(incidentItem(incident)); });
      }
    }

    renderSources(data);
  }

  function fail(error) {
    var overall = document.querySelector('[data-status-overall]');
    if (overall) {
      overall.className = 'status-pill status-pill--fail';
      overall.textContent = 'Live data unavailable';
    }
    setText('[data-status-updated]', 'Could not read status.json');
    setText('[data-status-summary-title]', 'Could not load build data');
    setText('[data-status-summary-lede]', 'status.json did not load, so this page cannot show live results. CircleCI and GitHub Actions have the current state.');
    var note = document.querySelector('[data-status-sources]');
    if (note) {
      note.textContent = 'status.json could not be loaded (' + (error && error.message ? error.message : 'unknown error')
        + '). The generated file is refreshed every 15 minutes by .github/workflows/status.yml.';
    }

    var dot = document.querySelector('[data-status-dot]');
    if (dot) {
      dot.className = 'status-summary__dot status-summary__dot--fail';
      dot.textContent = '';
      dot.appendChild(summaryIcon('unknown'));
    }

    statList('[data-status-stats]', [
      { label: 'Runs passed (24h)', value: '—', note: 'unavailable' },
      { label: 'Median run', value: '—', note: 'unavailable' },
      { label: 'Latest green build', value: '—', note: 'unavailable' }
    ]);

    var grid = document.querySelector('#pipeline-grid');
    if (grid) {
      grid.textContent = '';
      var card = node('article', 'status-card status-card--placeholder');
      card.appendChild(node('p', '', 'Build data could not be loaded.'));
      card.appendChild(node('p', 'status-card__hint', 'Open CircleCI or GitHub Actions for the current state.'));
      grid.appendChild(card);
    }

    var body = document.querySelector('#builds-body');
    if (body) {
      body.textContent = '';
      var row = node('tr');
      var empty = node('td', '', 'Build data could not be loaded. Open CircleCI or GitHub Actions for the current state.');
      empty.colSpan = 6;
      row.appendChild(empty);
      body.appendChild(row);
    }

    var timeline = document.querySelector('#incident-list');
    if (timeline) {
      timeline.textContent = '';
      var item = node('li');
      item.appendChild(node('h3', '', 'Incident history unavailable'));
      item.appendChild(node('p', '', 'It is generated from the same status.json as the rest of this page.'));
      timeline.appendChild(item);
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!document.querySelector('[data-status-overall]')) return;
    fetch('status.json', { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(render)
      .catch(fail);
  });
})();
