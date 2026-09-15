#!/usr/bin/env python3
"""
Generates an animated SVG of the user's REAL GitHub contribution graph,
revealed by a floating sword sweeping left-to-right across the weeks —
the sword equivalent of the classic contribution-snake, built from scratch
since no existing action does this.

Usage:
    GH_TOKEN=xxxx GH_USERNAME=yourname python generate_sword_svg.py

Outputs:
    dist/sword-contributions.svg        (dark background)
    dist/sword-contributions-light.svg  (light background)

NOTE ON THE TOKEN:
    GH_TOKEN must be a Personal Access Token with the "read:user" scope.
    The automatic Actions `secrets.GITHUB_TOKEN` will NOT work here — GitHub's
    GraphQL API rejects it for the `contributionsCollection` field with a
    "Resource not accessible by integration" error. See sword.yml for setup.
"""

import os
import sys
import json
import urllib.request
import urllib.error

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            color
          }
        }
      }
    }
  }
}
"""


def fetch_contributions(username: str, token: str):
    body = json.dumps({"query": QUERY, "variables": {"login": username}}).encode("utf-8")
    req = urllib.request.Request(
        GITHUB_GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "sword-contributions-generator",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API returned HTTP {e.code}. This usually means GH_TOKEN "
            f"is missing the 'read:user' scope (the default Actions token "
            f"does not have it — see sword.yml for how to set up a proper "
            f"Personal Access Token). Raw response: {detail}"
        ) from e

    if "errors" in payload:
        raise RuntimeError(
            "GitHub GraphQL API returned errors — this almost always means "
            "GH_TOKEN lacks the 'read:user' scope. Create a classic PAT "
            "with that scope and store it as the SWORD_PAT secret. "
            f"Errors: {payload['errors']}"
        )

    user = payload.get("data", {}).get("user")
    if not user:
        raise RuntimeError(
            f"No user data returned for login '{username}'. Double check "
            f"GH_USERNAME is correct and the account isn't private/suspended."
        )

    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    if not weeks:
        raise RuntimeError("GitHub returned zero weeks of contribution data.")

    return weeks


def build_svg(weeks, bg_color: str, empty_color: str, text_color: str) -> str:
    cell = 11
    gap = 3
    step = cell + gap
    top_pad = 34
    left_pad = 10

    n_weeks = len(weeks)
    grid_w = n_weeks * step
    grid_h = 7 * step

    width = grid_w + left_pad * 2
    height = grid_h + top_pad + 20

    # timing: each column gets its own staggered start so the sword's
    # pass and the cell reveal line up
    col_stagger = 0.07
    reveal_dur = 0.18
    sweep_span = n_weeks * col_stagger + reveal_dur  # time for the last column to finish
    hold = 2.2
    fade_out = 0.6
    cycle = sweep_span + hold + fade_out

    svg_parts = []
    svg_parts.append(
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )
    svg_parts.append(
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="8" fill="{bg_color}"/>'
    )
    svg_parts.append(
        f'<text x="{left_pad}" y="20" font-family="Fira Code, monospace" '
        f'font-size="13" font-weight="600" fill="{text_color}">'
        f"⚔️ real commits, cut open</text>"
    )

    defs = [
        "<defs>",
        '<linearGradient id="bladeGrad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '<stop offset="0%" stop-color="#f0e9ff"/>',
        '<stop offset="45%" stop-color="#ffffff"/>',
        '<stop offset="55%" stop-color="#cbb8f2"/>',
        '<stop offset="100%" stop-color="#7c6a94"/>',
        "</linearGradient>",
        '<linearGradient id="hiltGrad" x1="0%" y1="0%" x2="0%" y2="100%">',
        '<stop offset="0%" stop-color="#C77DFF"/>',
        '<stop offset="100%" stop-color="#7B2FF7"/>',
        "</linearGradient>",
        "</defs>",
    ]
    svg_parts.extend(defs)

    # grid group, offset below the label
    svg_parts.append(f'<g transform="translate({left_pad},{top_pad})">')

    for wi, week in enumerate(weeks):
        x = wi * step
        begin = round(wi * col_stagger, 3)
        for day in week["contributionDays"]:
            di = _weekday_index(day["date"])
            y = di * step
            color = day["color"] if day["contributionCount"] > 0 else empty_color

            # always-visible dim base cell
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{empty_color}"/>'
            )
            # real-color cell, revealed on the sweep, faded out at cycle end, loops
            t_reveal_end = round(reveal_dur / cycle, 4)
            t_hold_end = round((sweep_span + hold) / cycle, 4)
            # keep the fade-out keyframe strictly before 1.0 so the loop
            # restarts cleanly instead of holding two identical keyframes at 1
            t_fade_end = min(round((sweep_span + hold + fade_out) / cycle, 4), 0.9999)
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}" opacity="0">'
                f'<animate attributeName="opacity" '
                f'values="0;1;1;0;0" '
                f'keyTimes="0;{t_reveal_end};{t_hold_end};{t_fade_end};1" '
                f'dur="{round(cycle, 2)}s" begin="{begin}s" repeatCount="indefinite"/>'
                f"</rect>"
            )

    svg_parts.append("</g>")

    # the floating sword, swept across in sync with the columns
    sword_y = top_pad + grid_h / 2
    x_start = left_pad - 24
    x_end = left_pad + grid_w + 24
    t1 = round(sweep_span / cycle, 4)
    t2 = min(round((sweep_span + hold) / cycle, 4), 0.9999)

    svg_parts.append(f'<g>')
    svg_parts.append(
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="{x_start},{sword_y}; {x_end},{sword_y}; {x_end},{sword_y}; {x_start},{sword_y}" '
        f'keyTimes="0;{t1};{t2};1" dur="{round(cycle,2)}s" repeatCount="indefinite"/>'
    )
    svg_parts.append(
        '<circle cx="0" cy="0" r="10" fill="#9D4EDD" opacity="0.4">'
        '<animate attributeName="r" values="7;13;7" dur="0.6s" repeatCount="indefinite"/>'
        "</circle>"
    )
    svg_parts.append(
        '<polygon points="0,0 34,-5 38,0 34,5" fill="url(#bladeGrad)" stroke="#4b3f5c" stroke-width="1"/>'
    )
    svg_parts.append('<rect x="-4" y="-6" width="4" height="12" fill="url(#hiltGrad)"/>')
    svg_parts.append('<rect x="-13" y="-4" width="9" height="8" rx="2" fill="#2b1f3d"/>')
    svg_parts.append('<circle cx="-16" cy="0" r="3.2" fill="#C77DFF"/>')
    svg_parts.append("</g>")

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def _weekday_index(date_str: str) -> int:
    import datetime

    d = datetime.date.fromisoformat(date_str)
    # GitHub's calendar weeks run Sunday(0) -> Saturday(6)
    return (d.weekday() + 1) % 7


def main():
    username = os.environ.get("GH_USERNAME")
    token = os.environ.get("GH_TOKEN")
    if not username or not token:
        print("Set GH_USERNAME and GH_TOKEN environment variables.", file=sys.stderr)
        sys.exit(1)

    try:
        weeks = fetch_contributions(username, token)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    os.makedirs("dist", exist_ok=True)

    dark_svg = build_svg(weeks, bg_color="#150029", empty_color="#241539", text_color="#f3ecff")
    light_svg = build_svg(weeks, bg_color="#ffffff", empty_color="#ece3fb", text_color="#2b1f3d")

    with open("dist/sword-contributions.svg", "w", encoding="utf-8") as f:
        f.write(dark_svg)
    with open("dist/sword-contributions-light.svg", "w", encoding="utf-8") as f:
        f.write(light_svg)

    print("Wrote dist/sword-contributions.svg and dist/sword-contributions-light.svg")


if __name__ == "__main__":
    main()
