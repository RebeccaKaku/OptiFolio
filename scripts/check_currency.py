import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('config/boc_product_metadata.json', encoding='utf-8') as f:
    data = json.load(f)

no_cur = [p for p in data['products'] if not p.get('currency')]
has_cur = [p for p in data['products'] if p.get('currency')]
print(f"Total: {data['total']},  has_currency: {len(has_cur)},  no_currency: {len(no_cur)}")

print("\n--- Sample products WITHOUT currency ---")
for p in no_cur[:10]:
    code = p.get('product_code','')
    name = (p.get('product_name') or '')[:35]
    mp   = p.get('min_purchase_amount')
    err  = p.get('_html_error','')
    print(f"  {code:<22} min_purchase={mp!r:<12} name={name}  err={err[:40] if err else ''}")

print("\n--- Foreign-name products with no currency ---")
foreign_kw = ['美元','港元','港币','澳元','欧元','英镑','日元','USD','HKD','AUD','EUR']
foreign = [p for p in no_cur if any(k in (p.get('product_name') or '') for k in foreign_kw)]
print(f"  Count: {len(foreign)}")
for p in foreign[:8]:
    print(f"  {p.get('product_code',''):<22} {p.get('product_name','')[:45]}")

print("\n--- Currency distribution for has_currency ---")
from collections import Counter
dist = Counter(p.get('currency') for p in has_cur)
print("  ", dict(dist))
