#!/usr/bin/env python3
"""GovCon deep pricing pass.

For each Top-20 notice (plus any passed in): pull its solicitation documents,
store them in the Drive 'Bid Documents' folder, extract the contract's stated
year-1 ceiling and scope, and write it back into the Drive 'Bid Cache' JSON.

Ceiling logic (apples-to-apples, from the solicitation itself):
  - guaranteed minimum + maximum NTE  -> yr1_ceiling = max_NTE / pop_years
  - construction "magnitude" band      -> yr1_ceiling = band high (single-year project)
  - else                               -> left as None (flagged 'needs review')

Suggested bid (yr-1): default 0.85 * yr1_ceiling, capped under the NTE.
Reads docs from Drive when already stored; otherwise fetches from SAM and stores.
"""
import sqlite3, json, ssl, re, time, zipfile, urllib.request, urllib.parse
from io import BytesIO
from datetime import datetime

SAM = "SAM-eb4fe7b1-74cb-4ecc-9675-14d4fb27d97b"
BID_DOCS_FOLDER = "19aSf82IahDnbi0G4vBQj2qFZ7sUVDCuT"
BID_CACHE_FOLDER = "1nBGkN44a0i39RxNq9s9pYCzBEPRsoVwg"
TOKEN = open('/tmp/gws_token.txt').read().strip()
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE

def drive_list(folder):
    q = urllib.parse.quote(f"'{folder}' in parents and trashed=false")
    u = f"https://www.googleapis.com/drive/v3/files?q={q}&fields=files(id,name)&pageSize=300"
    req = urllib.request.Request(u, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, context=CTX) as r:
        return json.loads(r.read()).get('files', [])

def drive_get(file_id):
    req = urllib.request.Request(f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, context=CTX) as r:
        return r.read()

def drive_upload(name, data, mime, folder, existing_id=None):
    boundary = 'govcon_boundary'
    meta = json.dumps({"name": name, "parents": [folder]} if not existing_id else {"name": name}).encode()
    body = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode() + meta + b'\r\n' +
            f'--{boundary}\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n' + f'--{boundary}--'.encode())
    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
    method = 'POST'
    if existing_id:
        url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_id}?uploadType=multipart"
        method = 'PATCH'
    req = urllib.request.Request(url, data=body, method=method,
        headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': f'multipart/related; boundary={boundary}'})
    with urllib.request.urlopen(req, context=CTX) as r:
        return json.loads(r.read()).get('id')

def sam_download(rid):
    url = f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{rid}/download?api_key={SAM}"
    with urllib.request.urlopen(urllib.request.Request(url), context=CTX, timeout=60) as r:
        return r.read(), r.headers.get('Content-Disposition', '')

def extract_text(name, data):
    if name.lower().endswith('.docx') or data[:2] == b'PK':
        try:
            z = zipfile.ZipFile(BytesIO(data))
            xml = z.read('word/document.xml').decode('utf-8', 'ignore')
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', xml))
        except Exception:
            pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return data.decode('utf-8', 'ignore')

MONEY = r'\$?\s?([\d]{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{4,}(?:\.\d{2})?)'

def money(s):
    return float(s.replace(',', ''))

def parse_pricing(text):
    t = re.sub(r'\s+', ' ', text)
    res = {'guaranteed_min': None, 'max_nte': None, 'magnitude': None, 'pop_years': None,
           'volume_note': None}
    m = re.search(r'guaranteed minimum[^$]{0,60}' + MONEY, t, re.I)
    if m: res['guaranteed_min'] = money(m.group(1))
    for pat in [r'shall not exceed\s*' + MONEY, r'maximum amount[^$]{0,40}' + MONEY,
                r'not[- ]to[- ]exceed[^$]{0,30}' + MONEY, r'total maximum[^$]{0,40}' + MONEY]:
        m = re.search(pat, t, re.I)
        if m:
            res['max_nte'] = money(m.group(1)); break
    # construction magnitude band, e.g. "between $25,000 and $100,000"
    m = re.search(r'(?:magnitude|between)[^$]{0,40}' + MONEY + r'[^$]{0,15}(?:and|to|-)[^$]{0,10}' + MONEY, t, re.I)
    if m:
        res['magnitude'] = [money(m.group(1)), money(m.group(2))]
    # FAR 36.204 magnitude phrasing
    m = re.search(r'(more than|exceed)\s*' + MONEY + r'[^.]{0,40}(less than|not exceed)\s*' + MONEY, t, re.I)
    if m and not res['magnitude']:
        res['magnitude'] = [money(m.group(2)), money(m.group(4))]
    # period of performance years
    opts = len(re.findall(r'option (?:year|period)\s*(?:no\.?\s*)?\d', t, re.I))
    if re.search(r'base year plus (four|4)|five[- ]year|5[- ]year ordering', t, re.I):
        res['pop_years'] = 5
    elif opts:
        res['pop_years'] = 1 + min(opts, 4)
    elif re.search(r'one base year', t, re.I):
        res['pop_years'] = 1
    # volume hints
    m = re.search(r'(\d{2,6})\s*(?:pounds|lbs)[^.]{0,20}(?:per week|weekly|/week)', t, re.I)
    if m: res['volume_note'] = f"{m.group(1)} lbs/week"
    m2 = re.search(r'([\d,]{3,})\s*(?:square feet|sq\.?\s?ft|sf)\b', t, re.I)
    if m2 and not res['volume_note']: res['volume_note'] = f"{m2.group(1)} sq ft"
    return res

def compute(p):
    """Return (yr1_ceiling, suggested_bid, basis_note)."""
    if p.get('max_nte') and p.get('pop_years'):
        ceil = p['max_nte'] / p['pop_years']
        return round(ceil), round(ceil * 0.85), f"NTE ${p['max_nte']:,.0f}/{p['pop_years']}yr"
    if p.get('max_nte'):
        return round(p['max_nte']), round(p['max_nte'] * 0.85), f"NTE ${p['max_nte']:,.0f} (term n/a)"
    if p.get('magnitude'):
        lo, hi = p['magnitude']
        mid = (lo + hi) / 2
        return round(hi), round(mid), f"magnitude ${lo:,.0f}-${hi:,.0f}"
    return None, None, "no stated ceiling - needs review"

def main():
    top = json.load(open('/tmp/top20.json'))
    c = sqlite3.connect('olive-tree-govcon/cache.db')
    docs_index = {f['name']: f['id'] for f in drive_list(BID_DOCS_FOLDER)}
    cache_index = {f['name']: f['id'] for f in drive_list(BID_CACHE_FOLDER)}
    results = []
    for s in top:
        nid = s['nid']
        row = c.execute("SELECT data_json FROM opportunity_store WHERE notice_id=?", (nid,)).fetchone()
        rlinks, sol_no = [], ''
        if row:
            o = json.loads(row[0]); rlinks = o.get('resourceLinks') or []; sol_no = o.get('solicitationNumber', '')
        text = ""
        stored = []
        for url in rlinks[:3]:
            rid = url.rstrip('/').split('/')[-1]
            if rid == 'download':
                rid = url.rstrip('/').split('/')[-2]
            fname = f"{nid}_{rid[:8]}"
            try:
                # prefer Drive copy
                match = next((dn for dn in docs_index if dn.startswith(f"{nid}_{rid[:8]}")), None)
                if match:
                    data = drive_get(docs_index[match]); fname = match
                else:
                    data, cd = sam_download(rid)
                    m = re.search(r'filename=(.+)$', cd)
                    fn = (m.group(1).strip().strip('"') if m else f"{rid[:8]}.pdf")
                    fname = f"{nid}_{fn}"[:120]
                    mime = 'application/pdf' if fn.lower().endswith('pdf') else 'application/octet-stream'
                    fid = drive_upload(fname, data, mime, BID_DOCS_FOLDER)
                    docs_index[fname] = fid
                    stored.append(fname)
                text += "\n" + extract_text(fname, data)
            except Exception as e:
                text += f"\n[doc err {rid[:8]}: {e}]"
            time.sleep(0.2)
        p = parse_pricing(text)
        ceil, sug, basis = compute(p)
        rec = {'nid': nid, 'title': s['title'], 'naics': s['naics'], 'state': s['state'],
               'days': s['days'], 'sol_no': sol_no, 'pricing': p,
               'yr1_ceiling': ceil, 'suggested_bid': sug, 'basis': basis, 'stored_docs': stored}
        results.append(rec)
        # write/update Drive bid cache JSON
        cache_obj = {
            'notice_id': nid, 'title': s['title'], 'solicitation_number': sol_no,
            'naics': s['naics'], 'state': s['state'], 'trade': s.get('trade'),
            'deadline': s['deadline'], 'resource_links': rlinks,
            'pricing': p, 'yr1_ceiling': ceil, 'suggested_bid_yr1': sug, 'pricing_basis': basis,
            'pws_text': (re.sub(r'\s+', ' ', text)[:4000] if text.strip() else 'Pending'),
            'cached_date': datetime.now().strftime('%Y-%m-%d'), 'cache_version': 2,
        }
        existing = cache_index.get(f"{nid}.json")
        try:
            drive_upload(f"{nid}.json", json.dumps(cache_obj, indent=2).encode(),
                         'application/json', BID_CACHE_FOLDER, existing_id=existing)
        except Exception as e:
            rec['cache_err'] = str(e)
        print(f"{nid[:10]} {s['state']} {s['naics']} | ceil={ceil} sug={sug} | {basis} | {s['title'][:45]}",
              flush=True)
    json.dump(results, open('/tmp/pricing_deep.json', 'w'), indent=2)
    print(f"\nDONE: {len(results)} bids processed, results saved.")

if __name__ == '__main__':
    main()
