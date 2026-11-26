#!/usr/bin/env python3
"""Generate sitemap.xml and feed.xml from the site's HTML pages.

Dates come from the last git commit that touched each file, so the sitemap
and feed stay accurate automatically as pages change. Run from the repo root
(after committing) or via .github/workflows/discovery.yml on push to main.
"""
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SITE = 'https://kibaos.com'
ROOT = Path(__file__).resolve().parent.parent

# slug -> (changefreq, priority)
PAGES = {
    'index.html': ('monthly', '1.0'),
    'kibaos.html': ('monthly', '0.9'),
    'downloads.html': ('monthly', '0.9'),
    'docs.html': ('monthly', '0.9'),
    'about.html': ('monthly', '0.8'),
    'team.html': ('monthly', '0.8'),
    'directory.html': ('monthly', '0.6'),
    'news.html': ('weekly', '0.8'),
    'technical.html': ('monthly', '0.8'),
    'contact.html': ('monthly', '0.8'),
    'compatibility.html': ('monthly', '0.7'),
    'changelog.html': ('weekly', '0.6'),
    'roadmap.html': ('monthly', '0.6'),
    'security.html': ('monthly', '0.6'),
    'accessibility.html': ('monthly', '0.6'),
    'legal.html': ('yearly', '0.5'),
    'privacypolicy.html': ('yearly', '0.5'),
    'mtos.html': ('yearly', '0.4'),
}


def lastmod(slug):
    out = subprocess.run(
        ['git', '-C', str(ROOT), 'log', '-1', '--format=%as', '--', slug],
        capture_output=True, text=True, check=True).stdout.strip()
    if out:
        return out
    out = subprocess.run(
        ['git', '-C', str(ROOT), 'log', '-1', '--format=%as'],
        capture_output=True, text=True, check=True).stdout.strip()
    return out or datetime.now(timezone.utc).strftime('%Y-%m-%d')


def page_meta(slug):
    src = (ROOT / slug).read_text(encoding='utf-8')
    title = re.search(r'<title>(.*?)</title>', src, re.DOTALL)
    desc = re.search(r'<meta name="description" content="(.*?)"\s*/?>', src)
    return (re.sub(r'\s+', ' ', title.group(1)).strip() if title else slug,
            re.sub(r'\s+', ' ', desc.group(1)).strip() if desc else '')


def write_sitemap():
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    items = []
    for slug, (freq, prio) in PAGES.items():
        if not (ROOT / slug).exists():
            print('warning: %s missing, skipped' % slug, file=sys.stderr)
            continue
        url = SITE + '/' if slug == 'index.html' else '%s/%s' % (SITE, slug)
        items.append('  <url>\n'
                     '    <loc>%s</loc>\n'
                     '    <lastmod>%s</lastmod>\n'
                     '    <changefreq>%s</changefreq>\n'
                     '    <priority>%s</priority>\n'
                     '  </url>' % (url, lastmod(slug), freq, prio))
    lines += sorted(items, key=lambda x: -float(re.search(r'<priority>([\d.]+)', x).group(1)))
    lines.append('</urlset>')
    (ROOT / 'sitemap.xml').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('wrote sitemap.xml (%d urls)' % len(items))


def iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def write_feed():
    entries = []
    for slug, (_freq, _prio) in PAGES.items():
        if not (ROOT / slug).exists():
            continue
        day = lastmod(slug)
        try:
            stamp = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        title, desc = page_meta(slug)
        url = SITE + '/' if slug == 'index.html' else '%s/%s' % (SITE, slug)
        entries.append((stamp, url, title, desc, slug))
    entries.sort(key=lambda e: e[0], reverse=True)

    updated = iso(entries[0][0]) if entries else iso(datetime.now(timezone.utc))
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             '  <title>KibaOS updates</title>',
             '  <subtitle>Page updates and news from the KibaOS website, published by Kiba Labs, LLC.</subtitle>',
             '  <id>%s/</id>' % SITE,
             '  <link rel="alternate" type="text/html" href="%s/"/>' % SITE,
             '  <link rel="self" type="application/atom+xml" href="%s/feed.xml"/>' % SITE,
             '  <updated>%s</updated>' % updated,
             '  <author>',
             '    <name>Kiba Labs, LLC</name>',
             '    <email>corporate@kibaos.com</email>',
             '    <uri>%s/</uri>' % SITE,
             '  </author>']
    for stamp, url, title, desc, _slug in entries:
        lines += ['  <entry>',
                  '    <title>%s</title>' % title,
                  '    <link rel="alternate" type="text/html" href="%s"/>' % url,
                  '    <id>%s#updated-%s</id>' % (url, stamp.strftime('%Y%m%d')),
                  '    <updated>%s</updated>' % iso(stamp)]
        if desc:
            lines.append('    <summary>%s</summary>' % desc)
        lines.append('  </entry>')
    lines.append('</feed>')
    (ROOT / 'feed.xml').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('wrote feed.xml (%d entries)' % len(entries))


if __name__ == '__main__':
    write_sitemap()
    write_feed()
