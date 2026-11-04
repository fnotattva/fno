import csv,io,urllib.request,zipfile,collections
url='https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_20261103_F_0000.csv.zip'
req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.nseindia.com/'})
with urllib.request.urlopen(req,timeout=25) as x: blob=x.read()
with zipfile.ZipFile(io.BytesIO(blob)) as z:
 with z.open(next(n for n in z.namelist() if n.lower().endswith('.csv'))) as f: rows=list(csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig')))
print('TOTAL',len(rows));print('TYPES',collections.Counter(r['FinInstrmTp'] for r in rows))
seen=set()
for r in rows:
 if r['FinInstrmTp'] in seen: continue
 seen.add(r['FinInstrmTp']);print('SAMPLE', {k:r.get(k) for k in ('FinInstrmTp','TckrSymb','XpryDt','StrkPric','OptnTp','OpnIntrst','ChngInOpnIntrst','ClsPric','SttlmPric','UndrlygPric','TtlTradgVol','SctySrs')})
