"""Generate a script-free, animated SVG from GitHub contribution data.

Python 3.11+; standard library only. Never logs the API token.
"""
import argparse
from datetime import datetime, timedelta, timezone, date
from html import escape
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

QUERY = """query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def fetch_days(username):
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise ValueError("Set GH_TOKEN. In Actions use secrets.GITHUB_TOKEN.")
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=364)).replace(hour=0, minute=0, second=0, microsecond=0)
    payload = json.dumps({"query": QUERY, "variables": {
        "login": username, "from": start.isoformat(), "to": now.isoformat()
    }}).encode()
    for attempt in range(3):
        request = Request("https://api.github.com/graphql", data=payload, headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json", "User-Agent": "profile-activity-renderer"
        })
        try:
            with urlopen(request, timeout=40) as response:
                result = json.load(response)
            break
        except HTTPError as error:
            if error.code >= 500 and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ValueError("GitHub API returned HTTP " + str(error.code)) from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise ValueError("Cannot reach GitHub API; previous image is preserved.") from None
            time.sleep(2 ** attempt)
    if result.get("errors"):
        raise ValueError("GraphQL request failed; check token access and username.")
    user = (result.get("data") or {}).get("user")
    if not user:
        raise ValueError("GitHub user was not found.")
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [day for week in weeks for day in week["contributionDays"]
            if start.date() <= date.fromisoformat(day["date"]) <= now.date()]


def render(username, days, demo=False):
    days = sorted(days, key=lambda day: day["date"])
    if not days:
        raise ValueError("Calendar has no dates; refusing to replace the image.")
    first = date.fromisoformat(days[0]["date"])
    origin = first - timedelta(days=(first.weekday() + 1) % 7)
    active, cells, months = [], [], []
    total = sum(int(day["contributionCount"]) for day in days)
    palette = ["#203047", "#496c3b", "#72a741", "#b5d84b", "#ffcc46"]
    for day in days:
        current = date.fromisoformat(day["date"])
        count = int(day["contributionCount"])
        if count < 0:
            raise ValueError("Contribution counts must be nonnegative.")
        x = 56 + ((current - origin).days // 7) * 16
        y = 116 + ((current.weekday() + 1) % 7) * 20
        level = 0 if count == 0 else min(4, 1 + (count >= 3) + (count >= 6) + (count >= 10))
        cells.append(f'<rect x="{x}" y="{y}" width="12" height="14" rx="2" fill="{palette[level]}"><title>{current}: {count} contributions</title></rect>')
        if count:
            active.append((x + 6, y))
            cells.append(f'<path d="M{x+3} {y+4}h6 M{x+3} {y+10}h6" stroke="#ffe9a6" opacity=".45"/>')
        if current.day == 1:
            months.append(f'<text x="{x}" y="99">{current:%b}</text>')
    start = (30, 275)
    targets = active + [(932, 275)]
    # Quadratic arcs land exactly on the top center of each active calendar cell.
    # A terminal hold lets viewers see the flag before the loop restarts.
    key_times = [0.0]
    positions = [start]
    source = start
    for target in targets:
        for step in range(1, 9):
            t = step / 8
            x = source[0] + (target[0] - source[0]) * t
            y = source[1] + (target[1] - source[1]) * t - 4 * 24 * t * (1-t)
            positions.append((round(x, 2), round(y, 2)))
        source = target
    moving_count = len(positions)
    key_times = [i / (moving_count - 1) * .94 for i in range(moving_count)]
    positions.append(positions[-1])
    key_times.append(1.0)
    duration = max(12, len(targets) * .5 + 2)
    motion = ";".join(f"{x},{y}" for x, y in positions)
    times = ";".join(f"{t:.6f}" for t in key_times)
    sprite = [
        "....RRRRR...", "...RRRRRRRR.", "...BBSSKS...", "..BSBSSSKSS.",
        "..BSBBSSSKS.", "...BSSSSSS..", "....SSSSS...", "...RBRBR....",
        "..RRBRBRRR..", ".RRRBBBBRRR.", ".SSBYBBYBSS.", "..SBBBBBBS..",
        "...BBB.BBB..", "..BBB...BBB.", ".KKK.....KKK", "KKKK.....KKK",
    ]
    colors = {"R": "#ff5148", "B": "#427aff", "S": "#ffd0a0", "K": "#412e2a", "Y": "#ffe15d"}
    pixels = "".join(f'<rect x="{col*1.5-9}" y="{row*1.5-24}" width="1.5" height="1.5" fill="{colors[pixel]}"/>'
                     for row, line in enumerate(sprite) for col, pixel in enumerate(line) if pixel != ".")
    label = "DEMO / SAMPLE DATA" if demo else "LIVE GITHUB CONTRIBUTIONS"
    safe_name = escape(username)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="350" viewBox="0 0 1000 350" role="img" aria-labelledby="title desc">
<title id="title">{safe_name} — contribution adventure</title>
<desc id="desc">{label}. {total} contributions on {len(active)} active days. A pixel character jumps onto active dates in chronological order. Dates run left to right; rows are Sunday through Saturday.</desc>
<defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="#111d34"/><stop offset="1" stop-color="#192f48"/></linearGradient></defs>
<style>text{{font-family:monospace;fill:#9fb7ce;font-size:11px}}.heading{{fill:#f3f7ff;font-size:22px;font-weight:bold}}.coin{{animation:shimmer 1.2s ease-in-out infinite alternate}}@keyframes shimmer{{to{{opacity:.4}}}}@media(prefers-reduced-motion:reduce){{.coin{{animation:none}}}}</style>
<rect x="1" y="1" width="998" height="348" rx="18" fill="url(#sky)" stroke="#304967"/>
<text x="30" y="39" class="heading">CONTRIBUTION ADVENTURE</text>
<text x="30" y="61">{safe_name} / {label}</text>
<text x="968" y="36" text-anchor="end" style="fill:#ffdc74">SCORE {total:05d} / ACTIVE DAYS {len(active)}</text>
<text x="968" y="59" text-anchor="end">{escape(days[0]['date'])} — {escape(days[-1]['date'])}</text>
<path d="M630 81h45m-28-6h16 M760 77h48m-30-6h15" stroke="#7189a5" stroke-width="5" opacity=".25"/>
{''.join(months)}
<text x="15" y="126">Sun</text><text x="15" y="166">Tue</text><text x="15" y="206">Thu</text><text x="15" y="246">Sat</text>
{''.join(cells)}
<path d="M944 175v100" stroke="#b9c9d9" stroke-width="3"/>
<path d="M946 177h30l-10 12 10 12h-30z" fill="#65dba5"/>
<circle class="coin" cx="918" cy="259" r="5" fill="#ffd15a" stroke="#fff3b2"/>
<path d="M20 276h960v25H20z" fill="#a9603e"/>
<path d="M20 276h960 M20 289h960" stroke="#e2a26a" stroke-width="2"/>
<path d="{''.join(f'M{x} 277v11 M{x+15} 290v10 ' for x in range(20,980,30))}" stroke="#5a392f"/>
<g transform="translate(30 275)" shape-rendering="crispEdges">{pixels}
<animateTransform attributeName="transform" type="translate" values="{motion}" keyTimes="{times}" dur="{duration}s" repeatCount="indefinite" calcMode="linear"/>
</g>
<text x="30" y="326">Each block is a date. Brighter blocks mean more contributions. Every active date is visited.</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="SilentSongMEA")
    parser.add_argument("--output", default="assets/activity-mario.svg")
    parser.add_argument("--demo", action="store_true", help="Explicitly labeled synthetic preview; no API call")
    args = parser.parse_args()
    try:
        if args.demo:
            start = date(2025, 10, 20)
            days = [{"date": (start + timedelta(days=i)).isoformat(),
                     "contributionCount": (i % 13 + 1) if i % 17 in (0, 1, 6) else 0} for i in range(365)]
        else:
            days = fetch_days(args.username)
        svg = render(args.username, days, args.demo)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".tmp")
        temporary.write_text(svg, encoding="utf-8")
        temporary.replace(output)
        print("Generated " + str(output))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("Generation failed: " + str(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
