# 02-incident-analysis

## Innehåll
- `data/network_incidents.csv` – indata (incident-export)
- `src/incident_analysis.py` – Python-script för analys
- `output/incident_analysis.txt` – genererad rapport
- `output/incidents_by_site.csv` – sammanfattning per site
- `output/problem_devices.csv` – enheter sorterade på incidenter/kostnad
- `output/cost_analysis.csv` – trend/veckovis kostnad (om implementerad)

## Körning
Kör från repo-roten:

```bash
python3 src/incident_analysis.py
