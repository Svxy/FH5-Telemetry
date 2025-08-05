import csv
from collections import defaultdict

csv_file = "log2.csv"

stats = defaultdict(lambda: {"min": float("inf"), "max": float("-inf"), "sum": 0.0, "count": 0})

with open(csv_file, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        for key, val in row.items():
            if key == "timestamp": continue
            try:
                x = float(val)
                s = stats[key]
                s["min"] = min(s["min"], x)
                s["max"] = max(s["max"], x)
                s["sum"] += x
                s["count"] += 1
            except ValueError:
                continue

for k in sorted(stats):
    s = stats[k]
    avg = s["sum"] / s["count"] if s["count"] else 0
    print(f"{k:>30} | min: {s['min']:>10.3f} | max: {s['max']:>10.3f} | avg: {avg:>10.3f}")