// M&M / brokerage active-listings DOM extractor — paste into javascript_tool
// after loading an advisor page in the @browser connection.
//
// WHY BROWSER-ONLY: marcusmillichap.com advisor pages load active listings via
// an internal Sitecore search service (/mm/related/contentSearch) that returns a
// server error to curl/non-browser requests. Only closed transactions render in
// raw HTML. In a real browser the widget populates, so we read the DOM.
//
// TEAM INVENTORY: advisors in the same M&M office share one "Featured Listings"
// set — extract ONE advisor per office, not all of them (dedupe by office).
// Confirmed 2026-07-13: Mitchell/Welch/Shepard (Atlanta) return identical lists.
//
// Usage: navigate to the advisor URL, wait ~5s, then run this. Returns JSON.
(function () {
  const t = document.body.innerText;
  const s = t.indexOf('Featured Listings');
  if (s < 0) return '[]';
  const e = t.indexOf('Featured Closings');
  const block = (e > s ? t.slice(s, e) : t.slice(s)).replace('Featured Listings', '');
  const parts = block.split(/(?=APARTMENTS|MANUFACTURED HOUSING|COMMERCIAL|RETAIL|OFFICE|LAND|MIXED)/);
  const out = [];
  for (const p of parts) {
    const name = (p.split('\n').map(x => x.trim()).filter(x =>
      x && !/^(APARTMENTS|MANUFACTURED|COMMERCIAL|RETAIL|OFFICE|LAND|MIXED|Previous|Next|Number of|Cap Rate|Listing Price|Price\/Space)/.test(x))[0]) || '';
    const city = (p.match(/\n\s*([A-Za-z .'-]+,\s*[A-Z]{2})\s*\n/) || [])[1] || '';
    const units = (p.match(/Number of Units:\s*([\d,]+)/) || [])[1] || '';
    const price = (p.match(/Listing Price:\s*\$([\d,]+)/) || [])[1] || '';
    const cap = (p.match(/Cap Rate:\s*([\d.]+%)/) || [])[1] || '';
    if (name && (units || price)) out.push({ name, city, units, price, cap });
  }
  return JSON.stringify(out);
})()
