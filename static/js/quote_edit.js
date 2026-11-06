// 見積・請求の明細編集（line-form）: 行の追加/削除、金額と消費税のリアルタイム計算、品目マスタからの追加
(function () {
  const form = document.getElementById("line-form");
  if (!form) return;
  const prefix = form.dataset.prefix || "lines";
  const total = form.querySelector(`input[name="${prefix}-TOTAL_FORMS"]`);
  const lines = document.getElementById("lines");
  const tpl = document.getElementById("line-template");
  const margin = parseFloat(form.dataset.margin || "30");
  const rounding = parseInt(form.dataset.rounding || "1", 10);
  const yen = (n) => "¥" + Math.round(n).toLocaleString("ja-JP");

  // 明細金額 = 数量 × 単価（四捨五入）。消費税 = 税率ごとの合計 × 税率（切り捨て）
  function recalc() {
    const buckets = {};
    lines.querySelectorAll("[data-line]").forEach((row) => {
      const del = row.querySelector('input[name$="-DELETE"]');
      row.classList.toggle("deleted", !!(del && del.checked));
      const q = parseFloat(row.querySelector('[name$="-quantity"]').value || "0");
      const p = parseFloat(row.querySelector('[name$="-unit_price"]').value || "0");
      const rate = parseInt(row.querySelector('[name$="-tax_rate"]').value || "10", 10);
      const amount = Math.round(q * p);
      row.querySelector("[data-amount]").textContent = yen(amount);
      if (del && del.checked) return;
      const name = row.querySelector('[name$="-name"]').value.trim();
      if (!name && !amount) return;
      buckets[rate] = (buckets[rate] || 0) + amount;
    });
    let sub = 0, tax = 0;
    Object.entries(buckets).forEach(([rate, base]) => { sub += base; tax += Math.floor(base * rate / 100); });
    document.getElementById("t-subtotal").textContent = yen(sub);
    document.getElementById("t-tax").textContent = yen(tax);
    document.getElementById("t-total").textContent = yen(sub + tax);
  }

  function addLine(values) {
    const idx = parseInt(total.value, 10);
    const html = tpl.innerHTML.replace(/__prefix__/g, idx);
    lines.insertAdjacentHTML("beforeend", html);
    total.value = idx + 1;
    const row = lines.lastElementChild;
    Object.entries(values || {}).forEach(([k, v]) => {
      const el = row.querySelector(`[name="${prefix}-${idx}-${k}"]`);
      if (el && v !== null && v !== undefined) el.value = v;
    });
    recalc();
    row.querySelector('[name$="-name"]').focus();
    return row;
  }

  form.addEventListener("input", recalc);
  form.addEventListener("change", recalc);
  document.getElementById("add-line").addEventListener("click", () => addLine({ quantity: "1", tax_rate: "10" }));

  // ---- 品目マスタから追加 ----
  const search = document.getElementById("item-search");
  const results = document.getElementById("item-results");
  let timer;
  const priceFromCost = (cost) => Math.ceil(cost / (1 - margin / 100) / rounding) * rounding;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    const q = search.value.trim();
    if (!q) { results.hidden = true; return; }
    timer = setTimeout(async () => {
      const r = await fetch(form.dataset.searchUrl + "?q=" + encodeURIComponent(q));
      const data = await r.json();
      results.innerHTML = "";
      if (!data.items.length) {
        results.innerHTML = '<li class="muted">該当する品目がありません</li>';
      }
      data.items.forEach((it) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        const price = it.price !== null ? it.price : priceFromCost(parseFloat(it.cost));
        btn.textContent = `${it.label}（${it.unit}）  ${yen(price)}`;
        btn.addEventListener("click", () => {
          addLine({ name: it.name, spec: it.spec, unit: it.unit, quantity: "1", unit_price: price,
                    tax_rate: "10", direct_cost: it.cost });
          results.hidden = true;
          search.value = "";
        });
        li.appendChild(btn);
        results.appendChild(li);
      });
      results.hidden = false;
    }, 200);
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".picker")) results.hidden = true; });
  recalc();
})();
