#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONCEPTS = os.path.join(ROOT, "concepts")
PROBLEMS = os.path.join(ROOT, "problems")
README = os.path.join(ROOT, "README.md")
ACTIVITY_SVG = os.path.join(ROOT, "assets", "activity.svg")
GITHUB_REPO = "mauli-waghmore/system-design-notes"
GITHUB_BRANCH = "master"

WINDOW_DAYS = 30
STATUS_VALUES = ("Draft", "Review", "Complete")
PRETTY_NAMES = {
    "api": "API",
    "cdn": "CDN",
    "dns": "DNS",
    "id": "ID",
    "sql": "SQL",
    "url": "URL",
}


def prettify(value):
    words = value.replace("_", "-").split("-")
    return " ".join(PRETTY_NAMES.get(word, word.title()) for word in words)


def html_cell(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", " ")
    )


def github_raw_url(rel_path):
    return "https://raw.githubusercontent.com/{}/{}/{}".format(GITHUB_REPO, GITHUB_BRANCH, rel_path)


def excalidraw_open_url(rel_path):
    return "https://excalidraw.com/#url={}".format(quote(github_raw_url(rel_path), safe=""))


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def title_from_markdown(path, fallback):
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if line.startswith("# "):
                    return line[2:].strip()
    except FileNotFoundError:
        pass
    return prettify(fallback)


def status_from_text(text):
    match = re.search(r"(?im)^\s*(?:status|state)\s*:\s*(draft|review|complete)\s*$", text)
    if not match:
        match = re.search(r"(?im)^\s*[-*]\s*\*\*(?:status|state)\*\*\s*:\s*(draft|review|complete)\s*$", text)
    if not match:
        match = re.search(r"(?im)^\|\s*(?:status|state)\s*\|\s*(draft|review|complete)\s*\|", text)
    if not match:
        return "Draft"
    return match.group(1).title()


def status_from_markdown(path):
    try:
        return status_from_text(read_text(path))
    except FileNotFoundError:
        return "Draft"


def excalidraw_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return ""
    texts = []
    for element in data.get("elements", []):
        if element.get("type") == "text" and not element.get("isDeleted"):
            value = element.get("text") or element.get("originalText") or ""
            if value.strip():
                texts.append(value.strip())
    return "\n".join(texts)


def title_from_excalidraw(path, fallback):
    text = excalidraw_text(path)
    for line in text.splitlines():
        clean = line.strip()
        if clean and not clean.lower().startswith(("status:", "category:", "level:", "prerequisites:")):
            return clean.lstrip("#").strip()
    return prettify(fallback)


def status_from_excalidraw(path):
    return status_from_text(excalidraw_text(path))


def added_date(rel_path):
    try:
        result = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%as", "--", rel_path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        return lines[-1] if lines else ""
    except Exception:
        return ""


def collect_concepts():
    items = []
    if not os.path.isdir(CONCEPTS):
        return items
    for filename in sorted(os.listdir(CONCEPTS)):
        if filename.startswith(".") or not filename.endswith(".excalidraw"):
            continue
        full = os.path.join(CONCEPTS, filename)
        if not os.path.isfile(full):
            continue
        rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
        slug = filename[:-11]
        items.append({
            "title": title_from_excalidraw(full, slug),
            "slug": slug,
            "path": rel,
            "status": status_from_excalidraw(full),
            "date": added_date(rel),
        })
    items.sort(key=lambda item: (item["date"] or "9999-99-99", item["title"]))
    return items


def collect_problems():
    items = []
    if not os.path.isdir(PROBLEMS):
        return items
    for name in sorted(os.listdir(PROBLEMS)):
        if name.startswith("."):
            continue
        folder = os.path.join(PROBLEMS, name)
        if not os.path.isdir(folder):
            continue
        readme = os.path.join(folder, "README.md")
        diagram = os.path.join(folder, "diagram.excalidraw")
        if not os.path.exists(readme) and not os.path.exists(diagram):
            continue
        rel_folder = os.path.relpath(folder, ROOT).replace(os.sep, "/")
        readme_rel = os.path.join(rel_folder, "README.md").replace(os.sep, "/")
        diagram_rel = os.path.join(rel_folder, "diagram.excalidraw").replace(os.sep, "/")
        title = title_from_markdown(readme, name) if os.path.exists(readme) else prettify(name)
        status = status_from_markdown(readme) if os.path.exists(readme) else "Draft"
        date_path = readme_rel if os.path.exists(readme) else diagram_rel
        items.append({
            "title": title,
            "slug": name,
            "folder": rel_folder,
            "readme": readme_rel,
            "readme_exists": os.path.exists(readme),
            "diagram": diagram_rel,
            "diagram_exists": os.path.exists(diagram),
            "status": status,
            "date": added_date(date_path),
        })
    items.sort(key=lambda item: (item["date"] or "9999-99-99", item["title"]))
    return items


def active_dates(items):
    days = set()
    for item in items:
        if not item["date"]:
            continue
        try:
            days.add(date.fromisoformat(item["date"]))
        except ValueError:
            pass
    return days


def current_streak(days, today):
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(days):
    best = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue
        length = 0
        cursor = day
        while cursor in days:
            length += 1
            cursor += timedelta(days=1)
        best = max(best, length)
    return best


CELL = 16
GAP = 4
PAD = 6
TOP = 20
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CELL_STYLE = {
    "active": ("#39d353", "1"),
    "missed": ("#3f4650", "1"),
    "out": ("#1f242d", "1"),
}
TODAY_STROKE = "#f0f6fc"
FONT = "-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
LEGEND = [("active", "active"), ("missed", "missed"), ("today", "today")]


def day_status(day, days, today, window_start):
    if day < window_start or day > today:
        return "out"
    if day in days:
        return "active"
    return "missed"


def activity_svg(days, today):
    window_start = today - timedelta(days=WINDOW_DAYS - 1)
    grid_start = window_start - timedelta(days=window_start.weekday())
    grid_end = today + timedelta(days=6 - today.weekday())

    weeks = []
    week = grid_start
    while week <= grid_end:
        weeks.append([
            (week + timedelta(days=i), day_status(week + timedelta(days=i), days, today, window_start))
            for i in range(7)
        ])
        week += timedelta(days=7)

    rows = len(weeks)
    grid_w = 7 * CELL + 6 * GAP
    grid_h = rows * CELL + (rows - 1) * GAP

    swatch, label_gap, item_gap, char_w = 11, 5, 18, 5.6
    item_w = [swatch + label_gap + len(label) * char_w for _, label in LEGEND]
    legend_w = sum(item_w) + item_gap * (len(LEGEND) - 1)

    content_w = max(grid_w, legend_w)
    width = PAD * 2 + content_w
    legend_gap, legend_h = 16, 16
    height = TOP + grid_h + legend_gap + legend_h + PAD

    grid_x = PAD + (content_w - grid_w) / 2
    legend_x = PAD + (content_w - legend_w) / 2
    legend_y = TOP + grid_h + legend_gap

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{:.0f}" height="{:.0f}" '
        'viewBox="0 0 {:.0f} {:.0f}" role="img" aria-label="30-day activity">'.format(width, height, width, height)
    ]
    for col, label in enumerate(WEEKDAYS):
        x = grid_x + col * (CELL + GAP) + CELL / 2
        out.append(
            '<text x="{:.1f}" y="13" text-anchor="middle" font-family="{}" '
            'font-size="9" fill="#8b949e">{}</text>'.format(x, FONT, label)
        )
    for row, days_row in enumerate(weeks):
        for col, (day, status) in enumerate(days_row):
            fill, opacity = CELL_STYLE[status]
            x = grid_x + col * (CELL + GAP)
            y = TOP + row * (CELL + GAP)
            out.append(
                '<rect x="{:.1f}" y="{}" width="{}" height="{}" rx="3" fill="{}" opacity="{}"/>'.format(
                    x, y, CELL, CELL, fill, opacity
                )
            )
            if day == today:
                out.append(
                    '<rect x="{:.1f}" y="{:.1f}" width="{}" height="{}" rx="3" fill="none" '
                    'stroke="{}" stroke-width="1.5"/>'.format(
                        x + 0.75, y + 0.75, CELL - 1.5, CELL - 1.5, TODAY_STROKE
                    )
                )
    lx = legend_x
    for i, (status, label) in enumerate(LEGEND):
        if status == "today":
            out.append(
                '<rect x="{:.1f}" y="{:.1f}" width="{}" height="{}" rx="2.5" fill="none" '
                'stroke="{}" stroke-width="1.5"/>'.format(
                    lx + 0.75, legend_y + 0.75, swatch - 1.5, swatch - 1.5, TODAY_STROKE
                )
            )
        else:
            fill, opacity = CELL_STYLE[status]
            out.append(
                '<rect x="{:.1f}" y="{:.1f}" width="{}" height="{}" rx="2.5" fill="{}" opacity="{}"/>'.format(
                    lx, legend_y, swatch, swatch, fill, opacity
                )
            )
        out.append(
            '<text x="{:.1f}" y="{:.1f}" font-family="{}" font-size="10" fill="#8b949e">{}</text>'.format(
                lx + swatch + label_gap, legend_y + swatch - 1, FONT, label
            )
        )
        lx += item_w[i] + item_gap
    out.append("</svg>")
    return "\n".join(out) + "\n", window_start, today


def status_counts(items):
    counts = {status: 0 for status in STATUS_VALUES}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


def status_graph(concepts, problems):
    labels = ['"Concepts"', '"Problems"']
    complete = [
        sum(1 for item in concepts if item["status"] == "Complete"),
        sum(1 for item in problems if item["status"] == "Complete"),
    ]
    total = [len(concepts), len(problems)]
    ymax = max(total + [1])
    init = '%%{init: {"xyChart": {"plotColorPalette": ["#0969da", "#3DA639"]}}}%%'
    return (
        "```mermaid\n"
        + init + "\n"
        + "xychart-beta\n"
        + '    title "Progress by lane"\n'
        + "    x-axis [" + ", ".join(labels) + "]\n"
        + '    y-axis "Items" 0 --> ' + str(ymax + 1) + "\n"
        + "    bar [" + ", ".join(str(value) for value in total) + "]\n"
        + "    bar [" + ", ".join(str(value) for value in complete) + "]\n"
        + "```"
    )


def build_progress(concepts, problems, today=None):
    if today is None:
        today = datetime.now(timezone.utc).date()
    all_items = concepts + problems
    days = active_dates(all_items)
    streak = current_streak(days, today)
    longest = longest_streak(days)
    active_in_window = sum(1 for day in days if 0 <= (today - day).days < WINDOW_DAYS)
    diagrams = len(concepts) + sum(1 for problem in problems if problem["diagram_exists"])
    complete = sum(1 for item in all_items if item["status"] == "Complete")
    svg, start, end = activity_svg(days, today)

    stat_line = (
        "**{}** concepts &nbsp;·&nbsp; **{}** designs &nbsp;·&nbsp; **{}** diagrams "
        "&nbsp;·&nbsp; **{}** complete &nbsp;·&nbsp; **{}**-day streak "
        "&nbsp;·&nbsp; **{}** longest &nbsp;·&nbsp; **{}** / 30 active"
    ).format(len(concepts), len(problems), diagrams, complete, streak, longest, active_in_window)

    concept_counts = status_counts(concepts)
    problem_counts = status_counts(problems)

    dashboard = (
        '<div align="center">\n\n'
        + stat_line + "\n\n"
        + "**Daily activity** &nbsp;·&nbsp; " + start.isoformat() + " -> " + end.isoformat() + "\n\n"
        + '<img src="assets/activity.svg" alt="30-day activity calendar" width="320">\n\n'
        + "</div>"
    )

    tables = (
        '<table width="100%">\n'
        "  <thead>\n"
        "    <tr>\n"
        "      <th>Lane</th>\n"
        "      <th align=\"right\">Draft</th>\n"
        "      <th align=\"right\">Review</th>\n"
        "      <th align=\"right\">Complete</th>\n"
        "      <th align=\"right\">Total</th>\n"
        "    </tr>\n"
        "  </thead>\n"
        "  <tbody>\n"
        "    <tr>\n"
        "      <td>Concepts</td>\n"
        "      <td align=\"right\">{Draft}</td>\n"
        "      <td align=\"right\">{Review}</td>\n"
        "      <td align=\"right\">{Complete}</td>\n"
        "      <td align=\"right\">" + str(len(concepts)) + "</td>\n"
        "    </tr>\n"
        "    <tr>\n"
        "      <td>Design problems</td>\n"
        "      <td align=\"right\">{pDraft}</td>\n"
        "      <td align=\"right\">{pReview}</td>\n"
        "      <td align=\"right\">{pComplete}</td>\n"
        "      <td align=\"right\">" + str(len(problems)) + "</td>\n"
        "    </tr>\n"
        "  </tbody>\n"
        "</table>"
    ).format(
        Draft=concept_counts.get("Draft", 0),
        Review=concept_counts.get("Review", 0),
        Complete=concept_counts.get("Complete", 0),
        pDraft=problem_counts.get("Draft", 0),
        pReview=problem_counts.get("Review", 0),
        pComplete=problem_counts.get("Complete", 0),
    )

    return dashboard + "\n\n" + tables + "\n\n" + status_graph(concepts, problems), svg


def build_concept_index(concepts):
    if not concepts:
        return "_No concepts yet - add Excalidraw canvases under_ `concepts/`."
    rows = [
        '<table width="100%">',
        "  <thead>",
        "    <tr>",
        "      <th align=\"center\">#</th>",
        "      <th>Concept</th>",
        "      <th align=\"center\">Status</th>",
        "      <th align=\"center\">Added</th>",
        "    </tr>",
        "  </thead>",
        "  <tbody>",
    ]
    for index, item in enumerate(concepts, 1):
        rows.extend([
            "    <tr>",
            "      <td align=\"center\">{:02d}</td>".format(index),
            '      <td><a href="{}">{}</a></td>'.format(
                excalidraw_open_url(item["path"]),
                html_cell(item["title"]),
            ),
            "      <td align=\"center\"><code>{}</code></td>".format(html_cell(item["status"])),
            "      <td align=\"center\">{}</td>".format(html_cell(item["date"] or "-")),
            "    </tr>",
        ])
    rows.extend(["  </tbody>", "</table>"])
    return "\n".join(rows)


def build_problem_index(problems):
    if not problems:
        return "_No design problems yet - add folders under_ `problems/`."
    rows = []
    rows.extend([
        '<table width="100%">',
        "  <thead>",
        "    <tr>",
        "      <th align=\"center\">#</th>",
        "      <th>Design problem</th>",
        "      <th align=\"center\">Diagram</th>",
        "      <th align=\"center\">Status</th>",
        "      <th align=\"center\">Added</th>",
        "    </tr>",
        "  </thead>",
        "  <tbody>",
    ])
    for index, item in enumerate(problems, 1):
        title_link = item["readme"] if item["readme_exists"] else item["folder"]
        diagram = '<a href="{}">open</a>'.format(excalidraw_open_url(item["diagram"])) if item["diagram_exists"] else "-"
        rows.extend([
            "    <tr>",
            "      <td align=\"center\">{:02d}</td>".format(index),
            '      <td><a href="{}">{}</a></td>'.format(title_link, html_cell(item["title"])),
            "      <td align=\"center\">{}</td>".format(diagram),
            "      <td align=\"center\"><code>{}</code></td>".format(html_cell(item["status"])),
            "      <td align=\"center\">{}</td>".format(html_cell(item["date"] or "-")),
            "    </tr>",
        ])
    rows.extend(["  </tbody>", "</table>"])
    return "\n".join(rows)



def replace_region(text, name, payload):
    start = "<!-- {}:START -->".format(name)
    end = "<!-- {}:END -->".format(name)
    pattern = re.compile(re.escape(start) + ".*?" + re.escape(end), re.DOTALL)
    updated, count = pattern.subn(start + "\n" + payload + "\n" + end, text)
    if count != 1:
        raise RuntimeError("Expected exactly one {} region in README.md.".format(name))
    return updated


def read_readme():
    return read_text(README)


def readme_activity_end(text):
    match = re.search(r"\d{4}-\d{2}-\d{2}\s+(?:->|→)\s+(\d{4}-\d{2}-\d{2})", text)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def replace_badge_count(text, label, count):
    pattern = r"({}-)\d+(-[^)]*\?style=flat-square)".format(re.escape(label))
    return re.sub(pattern, lambda match: "{}{}{}".format(match.group(1), count, match.group(2)), text)


def generate(readme_text=None, today=None):
    concepts = collect_concepts()
    problems = collect_problems()
    progress, svg = build_progress(concepts, problems, today=today)
    text = readme_text if readme_text is not None else read_readme()

    text = replace_region(text, "STATS", progress)
    text = replace_region(text, "CONCEPTS", build_concept_index(concepts))
    text = replace_region(text, "PROBLEMS", build_problem_index(problems))
    text = replace_badge_count(text, "Concepts", len(concepts))
    text = replace_badge_count(text, "Designs", len(problems))

    return text, svg, len(concepts), len(problems)


def main():
    parser = argparse.ArgumentParser(description="Generate README progress, indexes, and activity SVG.")
    parser.add_argument("--check", action="store_true", help="fail if generated files are not up to date")
    args = parser.parse_args()

    if args.check:
        current_readme = read_readme()
        text, svg, concepts, problems = generate(current_readme, today=readme_activity_end(current_readme))
        if os.path.exists(ACTIVITY_SVG):
            current_svg = read_text(ACTIVITY_SVG)
        else:
            current_svg = ""
        if current_readme != text or current_svg != svg:
            print("README.md or assets/activity.svg is out of date. Run: python3 scripts/generate_readme.py", file=sys.stderr)
            return 1
        print("README.md and assets/activity.svg are up to date for {} concept(s) and {} design problem(s).".format(concepts, problems))
        return 0

    text, svg, concepts, problems = generate()

    with open(README, "w", encoding="utf-8") as handle:
        handle.write(text)

    os.makedirs(os.path.dirname(ACTIVITY_SVG), exist_ok=True)
    with open(ACTIVITY_SVG, "w", encoding="utf-8") as handle:
        handle.write(svg)

    print("Generated README + assets/activity.svg for {} concept(s) and {} design problem(s).".format(concepts, problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
