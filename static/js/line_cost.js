// 原価積算: 材料の追加・原価のリアルタイム計算・目標粗利率からの単価計算
(function () {
  const form = document.getElementById("cost-form");
  if (!form) return;
  const mats = document.getElementById("mats");
  const tpl = document.getElementById("mat-template");
  const total = form.querySelector('input[name="mat-TOTAL_FORMS"]');
  const laborRate = parseFloat(form.dataset.laborRate || "0");
  const margin = parseFloat(form.dataset.margin || "30");
  const rounding = parseInt(form.dataset.rounding || "1", 10);
  const yen = (n) => "¥" + Math.round(n).toLocaleString("ja-JP");
  const num = (el) => parseFloat((el && el.value) || "0") || 0;

  function recalc() {
    let mat = 0;
    mats.querySelectorAll("[data-mat]").forEach((row) => {
      const del = row.querySelector('input[name$="-DELETE"]');
      row.classList.toggle("deleted", !!(del && del.checked));
      const c = num(row.querySelector('[name$="-quantity"]')) * num(row.querySelector('[name$="-unit_cost"]'));
      row.querySelector("[data-amount]").textContent = yen(c);
      if (!(del && del.checked)) mat += c;
    });
    const labor = num(form.querySelector('[name="production_hours"]')) * laborRate;
    const direct = num(form.querySelector('[name="direct_cost"]'));
    const cost = mat + labor + direct;
    document.getElementById("c-mat").textContent = yen(mat);
    document.getElementById("c-labor").textContent = yen(labor);
    document.getElementById("c-direct").textContent = yen(direct);
    document.getElementById("c-cost").textContent = yen(cost);
    const suggest = cost > 0 ? Math.ceil(cost / (1 - margin / 100) / rounding) * rounding : 0;
    document.getElementById("c-suggest").textContent = cost > 0 ? yen(suggest) : "-";
    const cur = window.CURRENT_UNIT_PRICE || 0;
    document.getElementById("c-margin").textContent =
      cur > 0 && cost > 0 ? `（この原価での粗利率 ${(((cur - cost) / cur) * 100).toFixed(1)}%）` : "";
  }

  function addMat(values) {
    const idx = parseInt(total.value, 10);
    mats.insertAdjacentHTML("beforeend", tpl.innerHTML.replace(/__prefix__/g, idx));
    total.value = idx + 1;
    const row = mats.lastElementChild;
    Object.entries(values || {}).forEach(([k, v]) => {
      const el = row.querySelector(`[name="mat-${idx}-${k}"]`);
      if (el && v !== null && v !== undefined) el.value = v;
    });
    recalc();
    (row.querySelector('[name$="-quantity"]') || row.querySelector("input")).focus();
  }

  form.addEventListener("input", recalc);
  form.addEventListener("change", recalc);
  const addBtn = document.getElementById("add-mat");
  if (addBtn) addBtn.addEventListener("click", () => addMat({ quantity: "1" }));

  const search = document.getElementById("mat-search");
  const results = document.getElementById("mat-results");
  let timer;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    const q = search.value.trim();
    if (!q) { results.hidden = true; return; }
    timer = setTimeout(async () => {
      const data = await (await fetch(form.dataset.searchUrl + "?q=" + encodeURIComponent(q))).json();
      results.innerHTML = data.items.length ? "" : '<li class="muted">該当する品目がありません</li>';
      data.items.forEach((it) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = `${it.label}  ${yen(parseFloat(it.cost))}/${it.unit}`;
        btn.addEventListener("click", () => {
          addMat({ item: it.id, name: it.name, spec: it.spec, unit: it.unit, quantity: "1", unit_cost: it.cost });
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
