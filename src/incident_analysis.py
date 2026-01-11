import csv
import statistics
from pathlib import Path
from collections import defaultdict, Counter

# Mappning severity -> numeriskt värde (används i problem_devices.csv för avg_severity_score)
SEVERITY_SCORE = {"low": 1, "medium": 2, "high": 3, "critical": 4}

def parse_swedish_cost(value: str) -> float:
    """
    Parsar svenska belopp som t.ex. "4 567,50" till float 4567.50
    Hanterar tomma värden genom att returnera 0.0.
    """
    if value is None:
        return 0.0
    value = value.strip().strip('"')
    if not value:
        return 0.0
    return float(value.replace(" ", "").replace(",", "."))

def safe_int(value: str, default: int = 0) -> int:
    """
    Robust int-parsning. Tomma/ogiltiga värden -> default.
    """
    try:
        v = (value or "").strip()
        return int(v) if v else default
    except ValueError:
        return default

def safe_float(value: str, default: float = 0.0) -> float:
    """
    Robust float-parsning. Tomma/ogiltiga värden -> default.
    """
    try:
        v = (value or "").strip()
        return float(v) if v else default
    except ValueError:
        return default

def severity_from_impact(score: float) -> str:
    """
    FACIT-LOGIK: härled severity från impact_score (inte från CSV-kolumnen severity).
    Detta är det som ger fördelningen 8/15/16/13 för din dataset.

      critical: impact >= 9.0
      high    : impact >= 7.1
      medium  : impact >= 4.9
      low     : impact <  4.9
    """
    if score >= 9.0:
        return "critical"
    if score >= 7.1:
        return "high"
    if score >= 4.9:
        return "medium"
    return "low"

def format_swedish_number(value: float, decimals: int = 0) -> str:
    """
    Formatterar tal med svensk konvention: tusentalsmellanrum och komma som decimaltecken.
    Ex: 18456.0 -> "18 456"
    """
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")

def format_sek(value: float, decimals: int = 2) -> str:
    """
    Formatterar belopp som svenska kronor med valfritt antal decimaler.
    Ex: 4567.5 -> "4 567,50 SEK"
    """
    return f"{value:,.{decimals}f} SEK".replace(",", " ").replace(".", ",")

def severity_label(sev: str) -> str:
    """
    Snyggare label i rapporten.
    """
    return {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}.get(sev, sev)

def read_csv(path: Path):
    """
    Läser CSV och normaliserar/berikar varje rad med:
      - cost_float: float-baserat belopp
      - impact_score: float
      - severity: härledd från impact_score (facit-logik)
      - severity_raw: original severity från CSV (för spårbarhet)
      - severity_score: numeriskt severityvärde för enklare aggregat
    """
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for r in rows:
        # Trimma strängar för att undvika whitespace-problem
        r["ticket_id"] = (r.get("ticket_id") or "").strip()
        r["site"] = (r.get("site") or "").strip()
        r["device_hostname"] = (r.get("device_hostname") or "").strip()
        r["category"] = (r.get("category") or "").strip()
        r["description"] = (r.get("description") or "").strip()
        r["reported_by"] = (r.get("reported_by") or "").strip()
        r["resolution_notes"] = (r.get("resolution_notes") or "").strip()

        # Numeriska fält (robust parsing)
        r["week_number"] = safe_int(r.get("week_number"))
        r["resolution_minutes"] = safe_int(r.get("resolution_minutes"))
        r["affected_users"] = safe_int(r.get("affected_users"))
        r["cost_float"] = parse_swedish_cost(r.get("cost_sek", ""))
        r["impact_score"] = safe_float(r.get("impact_score"), 0.0)

        # Behåll original severity men använd facit-klassning i analysen
        r["severity_raw"] = (r.get("severity") or "").strip().lower()
        r["severity"] = severity_from_impact(r["impact_score"])  # <-- här byter vi logik
        r["severity_score"] = SEVERITY_SCORE.get(r["severity"], 0)

    return rows

def write_csv(path: Path, fieldnames, rows):
    """
    Skriver CSV med angivna kolumnnamn i given ordning.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def main():
    # Repo-struktur:
    # repo_root/
    #   data/network_incidents.csv
    #   output/...
    #   src/<detta_script>.py
    repo_root = Path(__file__).resolve().parents[1]
    data_path = repo_root / "data" / "network_incidents.csv"
    out_dir = repo_root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(data_path)

    # A) Grundsummeringar
    # Här räknas severity på impact-baserad severity ("severity" som vi satte i read_csv)
    sev_counts = Counter(r["severity"] for r in rows)

    # "Stora" incidenter (användare >100)
    big_impact = [r for r in rows if r["affected_users"] > 100]

    # Dyraste Top-5
    top5_cost = sorted(rows, key=lambda r: r["cost_float"], reverse=True)[:5]

    # B) Total kostnad
    total_cost = sum(r["cost_float"] for r in rows)

    # C) Genomsnittlig resolution per severity
    avg_res_by_sev = {}
    for sev in ["critical", "high", "medium", "low"]:
        rs = [r["resolution_minutes"] for r in rows if r["severity"] == sev]
        avg_res_by_sev[sev] = statistics.mean(rs) if rs else 0.0

    # D) KPI-rader per severity: antal, andel, snitt resolution, snittkostnad per incident
    sev_order = ["critical", "high", "medium", "low"]
    sev_kpi = {}
    for sev in sev_order:
        sev_rows = [r for r in rows if r["severity"] == sev]
        n = len(sev_rows)
        pct = (n / len(rows) * 100.0) if rows else 0.0
        avg_res = statistics.mean([r["resolution_minutes"] for r in sev_rows]) if n else 0.0
        avg_cost = (sum(r["cost_float"] for r in sev_rows) / n) if n else 0.0
        sev_kpi[sev] = {"n": n, "pct": pct, "avg_res": avg_res, "avg_cost": avg_cost}

    # E) Översikt per site
    site = defaultdict(lambda: {"total": 0, "cost": 0.0, "res": [], "sev": Counter()})
    for r in rows:
        s = site[r["site"]]
        s["total"] += 1
        s["cost"] += r["cost_float"]
        s["res"].append(r["resolution_minutes"])
        s["sev"][r["severity"]] += 1

    site_rows = []
    for site_name, v in sorted(site.items()):
        site_rows.append({
            "site": site_name,
            "total_incidents": v["total"],
            "critical_incidents": v["sev"].get("critical", 0),
            "high_incidents": v["sev"].get("high", 0),
            "medium_incidents": v["sev"].get("medium", 0),
            "low_incidents": v["sev"].get("low", 0),
            "avg_resolution_minutes": round(statistics.mean(v["res"]), 2) if v["res"] else 0,
            "total_cost_sek": round(v["cost"], 2),
        })

    write_csv(
        out_dir / "incidents_by_site.csv",
        ["site","total_incidents","critical_incidents","high_incidents","medium_incidents","low_incidents","avg_resolution_minutes","total_cost_sek"],
        site_rows
    )

    # F) Category impact: avg impact per kategori
    cat = defaultdict(list)
    for r in rows:
        cat[r["category"]].append(r["impact_score"])
    cat_lines = [(k, len(v), statistics.mean(v)) for k, v in cat.items()]

    # G) problem_devices.csv: aggregering per device
    device = defaultdict(lambda: {"site": "", "count": 0, "cost": 0.0, "sev_scores": [], "impact": [], "affected": []})
    for r in rows:
        d = device[r["device_hostname"]]
        d["site"] = r["site"]
        d["count"] += 1
        d["cost"] += r["cost_float"]
        d["sev_scores"].append(r["severity_score"])
        d["impact"].append(r["impact_score"])
        d["affected"].append(r["affected_users"])

    problem_rows = []
    for hostname, v in device.items():
        problem_rows.append({
            "device_hostname": hostname,
            "site": v["site"],
            "incident_count": v["count"],
            "avg_severity_score": round(statistics.mean(v["sev_scores"]), 2),
            "total_cost_sek": round(v["cost"], 2),
            "avg_affected_users": round(statistics.mean(v["affected"]), 2),
            "avg_impact_score": round(statistics.mean(v["impact"]), 2),
        })

    problem_rows.sort(key=lambda r: (r["incident_count"], r["total_cost_sek"]), reverse=True)

    write_csv(
        out_dir / "problem_devices.csv",
        ["device_hostname","site","incident_count","avg_severity_score","total_cost_sek","avg_affected_users","avg_impact_score"],
        problem_rows
    )

    # H) cost_analysis.csv: veckovis trend
    week = defaultdict(lambda: {"count": 0, "cost": 0.0, "impact": [], "affected": []})
    for r in rows:
        w = week[r["week_number"]]
        w["count"] += 1
        w["cost"] += r["cost_float"]
        w["impact"].append(r["impact_score"])
        w["affected"].append(r["affected_users"])

    week_rows = []
    for wk, v in sorted(week.items()):
        week_rows.append({
            "week_number": wk,
            "total_incidents": v["count"],
            "total_cost_sek": round(v["cost"], 2),
            "avg_impact_score": round(statistics.mean(v["impact"]), 2),
            "avg_affected_users": round(statistics.mean(v["affected"]), 2),
        })

    write_csv(
        out_dir / "cost_analysis.csv",
        ["week_number","total_incidents","total_cost_sek","avg_impact_score","avg_affected_users"],
        week_rows
    )

    # I) Textrapport (incident_analysis.txt)
    report = []
    report.append("=" * 80)
    report.append("INCIDENT ANALYSIS - NETWORK INCIDENTS".center(80))
    report.append("=" * 80)
    report.append(f"Total incidents: {len(rows)}")
    report.append(f"Total kostnad: {format_sek(total_cost, 2)}")
    report.append("")
    report.append("EXECUTIVE SUMMARY")
    report.append("-" * 80)

    # Snabb severity-fördelning (facitlogik)
    report.append(
        f"Critical: {sev_counts.get('critical',0)} | "
        f"High: {sev_counts.get('high',0)} | "
        f"Medium: {sev_counts.get('medium',0)} | "
        f"Low: {sev_counts.get('low',0)}"
    )

    # KPI-rader per severity (antal, procent, snittid, snittkostnad/incident)
    for sev in ["critical", "high", "medium", "low"]:
        k = sev_kpi[sev]
        report.append(
            f"{severity_label(sev)}: {k['n']} st ({k['pct']:.0f}%) - "
            f"Genomsnitt: {k['avg_res']:.0f} min resolution, "
            f"{format_swedish_number(k['avg_cost'], 0)} SEK/incident"
        )

    report.append(f"Incidents >100 affected users: {len(big_impact)}")
    report.append("Dyraste incidenter (Top 5):")
    for r in top5_cost:
        report.append(f"  {r['ticket_id']}  {r['device_hostname']}  {r['site']}  {format_sek(r['cost_float'], 2)}")

    report.append("")
    report.append("AVG RESOLUTION (MIN) PER SEVERITY")
    report.append("-" * 80)
    for sev in ["critical","high","medium","low"]:
        report.append(f"{sev:8}: {avg_res_by_sev[sev]:.1f} min")

    report.append("")
    report.append("SUMMARY PER SITE")
    report.append("-" * 80)
    for r in site_rows:
        report.append(
            f"{r['site']}: {r['total_incidents']} incidents  "
            f"cost {format_sek(r['total_cost_sek'], 2)}  "
            f"avg res {str(r['avg_resolution_minutes']).replace('.', ',')} min"
        )

    report.append("")
    report.append("CATEGORY IMPACT (AVG)")
    report.append("-" * 80)
    for k, n, m in sorted(cat_lines, key=lambda x: x[2], reverse=True):
        report.append(f"{k:12}: {n:>2} st, avg impact {m:.2f}")

    report.append("")
    report.append("=" * 80)
    report.append("RAPPORT SLUT".center(80))
    report.append("=" * 80)

    (out_dir / "incident_analysis.txt").write_text("\n".join(report), encoding="utf-8")
    print("OK: Skapade output/incident_analysis.txt + CSV-filer")

if __name__ == "__main__":
    main()
