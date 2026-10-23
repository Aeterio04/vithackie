import json
from collections import Counter

data = json.load(open('docs/frontend-audit/endpoint_inventory.json', encoding='utf-8'))
print('Total operations tested:', len(data))
print('Status codes:', Counter(d['status_code'] for d in data))

not_2xx = [f"{d['method']} {d['path']}: {d['status_code']}" for d in data if d['status_code'] not in (200, 201, 202, 204)]
print(f'Non-2xx count: {len(not_2xx)}')
for item in not_2xx:
    print(' ', item)
