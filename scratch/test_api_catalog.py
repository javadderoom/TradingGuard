import urllib.request
import json

res = urllib.request.urlopen('http://localhost:8000/api/catalog')
data = json.loads(res.read().decode())
print("Catalog symbols:")
for s in data['symbols']:
    print(f"  {s['symbol']}: {s.get('min_date')} to {s.get('max_date')}, total_m1: {s.get('total_m1_bars')}")
