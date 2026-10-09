/* Oberfläche.
   Ein Wort behält seine Bedeutung durch den ganzen Ablauf: Was „Analyse
   starten" heißt, meldet später „Analyse fertig". */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* Texte kommen aus app/i18n.py und werden von der Vorlage eingesetzt.
     Ein Katalog für Server und Browser — zwei laufen sonst auseinander. */
  const T = window.TEXTE || {};
  const txt = (schluessel, werte = {}) =>
    (T[schluessel] || schluessel).replace(/\{(\w+)\}/g,
      (_, name) => (name in werte ? werte[name] : "{" + name + "}"));
  const sichtung = $("sichtung");
  const ruhig = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const zustand = {
    datei: null,
    jobId: null,
    tiefe: "schnell",
    format: "16:9",
    anzahl: 3,
    motivlage: "egal",
    lageprio: "position",
    pollen: null,
    begonnen: 0,
  };

  // --- Hilfen -------------------------------------------------------------

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const zeitcode = (s) => {
    const m = Math.floor(s / 60), r = s - m * 60;
    return `${String(m).padStart(2, "0")}:${r.toFixed(2).padStart(5, "0")}`;
  };

  const mb = (b) => (b / (1024 * 1024)).toFixed(1) + " MB";

  /* Pfeil in eine Ablage — dasselbe Zeichen, das Betriebssysteme für
     „herunterladen" benutzen. Inline, damit kein zweiter Abruf nötig ist. */
  const PFEIL = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"
    stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true"><path d="M8 1.6v8.2M4.6 6.6 8 10l3.4-3.4M2 11.4v1.5a1.5
    1.5 0 0 0 1.5 1.5h9a1.5 1.5 0 0 0 1.5-1.5v-1.5"/></svg>`;

  const zeitpunkt = (sekunden) => new Date(sekunden * 1000)
    .toLocaleString(document.documentElement.lang || "de",
      { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

  async function json(url, optionen) {
    const antwort = await fetch(url, {
      headers: { "Content-Type": "application/json" }, ...optionen,
    });
    const text = await antwort.text();
    let daten = {};
    try { daten = text ? JSON.parse(text) : {}; } catch { /* leer */ }
    if (!antwort.ok) {
      throw new Error(daten.detail || txt("fehler_anfrage"));
    }
    return daten;
  }

  // --- Eingaben -----------------------------------------------------------

  function zaehler(feldId, zaehlerId, grenze, ab) {
    const feld = $(feldId), anzeige = $(zaehlerId);
    const zeichnen = () => {
      const n = feld.value.length;
      anzeige.hidden = n < ab;
      anzeige.textContent = `${n}/${grenze}`;
      anzeige.classList.toggle("nah", n >= ab && n < grenze);
      anzeige.classList.toggle("drueber", n >= grenze);
    };
    feld.addEventListener("input", zeichnen);
    zeichnen();
  }
  zaehler("headline", "headlinezaehler", 120, 90);
  zaehler("beschreibung", "beschreibungzaehler", 500, 400);

  document.querySelectorAll(".wahl").forEach((gruppe) => {
    gruppe.addEventListener("click", (e) => {
      const knopf = e.target.closest("button");
      if (!knopf) return;
      gruppe.querySelectorAll("button").forEach((b) =>
        b.setAttribute("aria-pressed", String(b === knopf)));
      const name = gruppe.dataset.name;
      zustand[name] = name === "anzahl" ? Number(knopf.dataset.wert) : knopf.dataset.wert;
      if (name === "tiefe") $("tiefehinweis").hidden = zustand.tiefe !== "gruendlich";
      // Die Prioritaet wirkt wie die Lage selbst: sofort und kostenlos.
      if (name === "lageprio" && zustand.jobId && document.querySelector(".ergebnis")) {
        neuOrdnen();
      }
    });
  });

  /* Motivlage. Das Raster ist ein Bild des Bildes: Neun Flächen sagen
     schneller, was gemeint ist, als neun Wörter. „egal" liegt daneben, weil
     es keine Position ist, sondern deren Abwesenheit. */
  const lageraster = $("lageraster"), lagestand = $("lagestand");

  function lageSetzen(wert, auchNeuordnen = true) {
    zustand.motivlage = wert;
    lageraster.querySelectorAll("button").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.lage === wert)));
    lagestand.textContent = txt("lage_" + wert);
    lagestand.classList.toggle("gesetzt", wert !== "egal");
    // Die Prioritaet ist eine Unterfrage der Position -- ohne Position gibt
    // es nichts zu priorisieren, also auch nichts anzuzeigen.
    $("lageprio").hidden = wert === "egal";
    // Liegt schon ein Ergebnis vor, kostet das Neuordnen nichts: Die Lage
    // jedes Kandidaten steht im Protokoll, das Modell wird nicht gefragt.
    if (auchNeuordnen && zustand.jobId && document.querySelector(".ergebnis")) {
      neuOrdnen();
    }
  }

  /* Nach der Analyse zeigt das Raster, wo dieses Video ueberhaupt Material
     hat: Punktstaerke = Kandidaten je Zelle. Man sieht VOR dem Markieren,
     dass z. B. die obere Zeile leer ist, statt blind zu waehlen und einen
     Rueckfall erklaert zu bekommen. Ohne Ergebnis bleibt das Raster neutral. */
  function lageDichteZeigen(dichte) {
    const werte = dichte ? Object.values(dichte) : [];
    const max = werte.length ? Math.max(...werte) : 0;
    lageraster.classList.toggle("dichte", max > 0);
    lageraster.querySelectorAll("button").forEach((b) => {
      const n = (dichte || {})[b.dataset.lage] || 0;
      const name = txt("lage_" + b.dataset.lage);
      if (max > 0) {
        b.style.setProperty("--dichte", n ? (0.5 + 0.5 * n / max).toFixed(2) : 0.12);
        b.title = `${name} — ${
          n === 0 ? txt("lage_anzahl_keine")
                  : n === 1 ? txt("lage_anzahl_eins")
                            : txt("lage_anzahl", { n })}`;
      } else {
        b.style.removeProperty("--dichte");
        b.title = name;
      }
      b.setAttribute("aria-label", b.title);
    });
  }

  lageraster.addEventListener("click", (e) => {
    const knopf = e.target.closest("button");
    if (!knopf) return;
    // Zweiter Klick auf dieselbe Zelle hebt die Wahl auf. Ein eigener
    // „egal"-Knopf hätte eine Zeile gekostet, die es nicht gibt.
    lageSetzen(knopf.dataset.lage === zustand.motivlage ? "egal" : knopf.dataset.lage);
  });

  async function neuOrdnen() {
    const knopf = $("neue");
    const alt = knopf ? knopf.textContent : "";
    if (knopf) { knopf.disabled = true; knopf.textContent = txt("lage_neu"); }
    try {
      await json(`/api/jobs/${zustand.jobId}/rerank`, {
        method: "POST",
        body: JSON.stringify({ motivlage: zustand.motivlage,
                               lage_prio: zustand.lageprio }),
      });
      const daten = await json(`/api/jobs/${zustand.jobId}`);
      zeigeErgebnis(daten.results);
    } catch (fehler) {
      if (knopf) { knopf.disabled = false; knopf.textContent = alt; }
      zeigeFehler(fehler.message);
    }
  }

  $("schaerfe").addEventListener("input", (e) => {
    $("schaerfewert").textContent = Number(e.target.value).toFixed(2);
  });

  // Ablagefeld und Adressfeld schließen einander aus — sichtbar, nicht erst
  // beim Absenden.
  const ablage = $("ablage"), quellurl = $("quellurl");
  function abgleichen() {
    const hatUrl = quellurl.value.trim().length > 0;
    ablage.classList.toggle("aus", hatUrl);
    $("datei").disabled = hatUrl;
    $("dateiwahl").disabled = hatUrl;
    quellurl.disabled = !!zustand.datei;
    pruefeStart();
  }
  quellurl.addEventListener("input", abgleichen);

  function dateiSetzen(datei) {
    if (!datei) return;
    if (!datei.type.startsWith("video/")) {
      zeigeFehler(txt("fehler_kein_video"));
      return;
    }
    zustand.datei = datei;
    $("dateiname").textContent = `${datei.name} · ${mb(datei.size)}`;
    $("dateizeile").hidden = false;
    // Das Ablagefeld weicht der Dateizeile: Seine Aufforderung ist erledigt,
    // und die Spalte soll ohne Scrollen auf einen 13-Zoll-Schirm passen.
    ablage.hidden = true;
    abgleichen();
  }

  $("dateiwahl").addEventListener("click", () => $("datei").click());
  $("datei").addEventListener("change", (e) => dateiSetzen(e.target.files[0]));
  $("dateiweg").addEventListener("click", () => {
    lageDichteZeigen(null);
    zustand.datei = null;
    $("datei").value = "";
    $("dateizeile").hidden = true;
    ablage.hidden = false;
    abgleichen();
  });

  ["dragenter", "dragover"].forEach((art) =>
    ablage.addEventListener(art, (e) => {
      e.preventDefault(); ablage.classList.add("drueber");
    }));
  ["dragleave", "drop"].forEach((art) =>
    ablage.addEventListener(art, (e) => {
      e.preventDefault(); ablage.classList.remove("drueber");
    }));
  ablage.addEventListener("drop", (e) => dateiSetzen(e.dataTransfer.files[0]));

  /* Headline und Beschreibung sind freiwillig — zum Starten reicht ein
     Video. Was das Weglassen kostet, sagt der Hinweis darunter. */
  function pruefeStart() {
    $("start").disabled = !(zustand.datei || quellurl.value.trim().length > 0);
  }
  $("headline").addEventListener("input", pruefeStart);
  pruefeStart();

  // --- Hinweis auf die freiwilligen Felder --------------------------------

  const HINWEIS_WEG = "loupe_hinweis_felder_weg";
  const feldhinweis = $("feldhinweis");

  function hinweisPruefen() {
    const leer = !$("headline").value.trim() || !$("beschreibung").value.trim();
    let weggeklickt = false;
    try { weggeklickt = localStorage.getItem(HINWEIS_WEG) === "1"; } catch { /* egal */ }
    feldhinweis.hidden = !leer || weggeklickt;
  }

  $("hinweisweg").addEventListener("click", () => {
    feldhinweis.hidden = true;
    try { localStorage.setItem(HINWEIS_WEG, "1"); } catch { /* egal */ }
  });
  $("headline").addEventListener("input", hinweisPruefen);
  $("beschreibung").addEventListener("input", hinweisPruefen);
  hinweisPruefen();

  // --- Ablauf -------------------------------------------------------------

  /* Nach dem Start dorthin springen, wo etwas passiert. Wer weit unten im
     Formular auf „Analyse starten" geklickt hat, sähe den Fortschritt sonst
     gar nicht. */
  function zumSichtungsbereich() {
    const oben = () => sichtung.getBoundingClientRect().top;
    if (ruhig) {
      sichtung.scrollIntoView({ block: "start", behavior: "auto" });
      return;
    }
    sichtung.scrollIntoView({ block: "start", behavior: "smooth" });
    // Weiches Scrollen wird von manchen Umgebungen nicht ausgeführt — dann
    // bliebe man stehen, wo man war, und sähe vom Fortschritt nichts. Nach
    // einem halben Moment nachsehen und notfalls springen.
    setTimeout(() => {
      if (Math.abs(oben()) > 8) {
        sichtung.scrollIntoView({ block: "start", behavior: "auto" });
      }
    }, 500);
  }

  $("formular").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("start").disabled = true;
    zumSichtungsbereich();
    try {
      let uploadId = "";
      if (zustand.datei) {
        uploadId = await hochladen(zustand.datei);
      }
      const { job_id } = await json("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          upload_id: uploadId,
          quell_url: uploadId ? "" : quellurl.value.trim(),
          headline: $("headline").value.trim(),
          beschreibung: $("beschreibung").value.trim(),
          tiefe: zustand.tiefe,
          format: zustand.format,
          gesichter: $("gesichter").checked,
          textflaeche: $("textflaeche").checked,
          anzahl: zustand.anzahl,
          transkript: $("transkript").checked,
          motivlage: zustand.motivlage,
          lage_prio: zustand.lageprio,
          schaerfe_perzentil: Number($("schaerfe").value),
        }),
      });
      zustand.jobId = job_id;
      zustand.begonnen = Date.now();
      zeigeArbeit(txt("wird_gestartet"), 0.05);
      zumSichtungsbereich();
      pollen();
    } catch (fehler) {
      zeigeFehler(fehler.message);
    }
  });

  /* Stückweiser Upload. Railway begrenzt nicht die Größe eines Requests,
     sondern bricht nach fünf Minuten ab — ein großes Video in einem Rutsch
     scheitert also auf langsamen Leitungen, und zwar erst nach fünf Minuten
     Warten. In Stücken dauert jeder Request Sekunden, und ein abgerissenes
     Stück lässt sich einzeln wiederholen statt alles von vorn. */
  async function hochladen(datei) {
    const { upload_id, teilgroesse } = await json("/api/uploads", {
      method: "POST",
      body: JSON.stringify({ filename: datei.name, size: datei.size }),
    });

    const anzahl = Math.ceil(datei.size / teilgroesse);
    for (let i = 0; i < anzahl; i++) {
      const stueck = datei.slice(i * teilgroesse, (i + 1) * teilgroesse);
      await mitWiederholung(async () => {
        const antwort = await fetch(`/api/uploads/${upload_id}/${i}`, {
          method: "PUT", body: stueck,
        });
        if (!antwort.ok) throw new Error("Stück " + i + " kam nicht an");
      });
      zeigeArbeit(
        txt("uebertragung", { prozent: Math.round(((i + 1) / anzahl) * 100) }),
        0.02 + 0.08 * ((i + 1) / anzahl),
      );
    }
    return upload_id;
  }

  async function mitWiederholung(arbeit, versuche = 3) {
    for (let n = 1; ; n++) {
      try {
        return await arbeit();
      } catch (fehler) {
        if (n >= versuche) {
          throw new Error(txt("fehler_upload"));
        }
        await new Promise((r) => setTimeout(r, 800 * n));
      }
    }
  }

  function pollen() {
    clearInterval(zustand.pollen);
    zustand.pollen = setInterval(async () => {
      try {
        const daten = await json(`/api/jobs/${zustand.jobId}`);
        if (daten.status === "fertig") {
          clearInterval(zustand.pollen);
          zeigeErgebnis(daten.results);
          verlaufLaden();
        } else if (daten.status === "fehler") {
          clearInterval(zustand.pollen);
          zeigeFehler(daten.message || txt("fehler_anfrage"));
        } else {
          zeigeArbeit(daten.stage, daten.progress);
        }
      } catch (fehler) {
        clearInterval(zustand.pollen);
        zeigeFehler(fehler.message);
      }
    }, 1500);
  }

  // --- Zustände des Sichtungsbereichs -------------------------------------

  function zeigeArbeit(stufe, anteil) {
    const sekunden = zustand.begonnen
      ? Math.round((Date.now() - zustand.begonnen) / 1000) : 0;
    sichtung.innerHTML = `
      <div class="arbeit">
        <p class="stufe">${esc(stufe)}</p>
        <div class="balken"><i style="width:${Math.round((anteil || 0) * 100)}%"></i></div>
        <p class="dauer">${sekunden ? sekunden + " s" : ""}</p>
      </div>`;
  }

  function zeigeFehler(meldung) {
    sichtung.innerHTML = `
      <div class="fehler" role="alert">
        <h2>${esc(txt("fehler_titel"))}</h2>
        <p>${esc(meldung)}</p>
        <div><button type="button" class="schlicht" id="nochmal">${esc(txt("erneut"))}</button></div>
      </div>`;
    $("nochmal").addEventListener("click", () => {
      sichtung.innerHTML = `<div class="leer"><h2>${esc(txt("leer_titel"))}</h2>
        <p>${esc(txt("leer_text"))}</p></div>`;
      pruefeStart();
    });
    pruefeStart();
  }

  function zeigeErgebnis(ergebnis) {
    if (!ergebnis) return zeigeFehler(txt("fehler_leer"));
    const dauer = ergebnis.dauer || 1;
    const zwischenstufen = $("zwischenstufen").checked;
    const k = ergebnis.kennzahlen || {};

    const karten = ergebnis.vorschlaege.map((v) => `
      <article class="vorschlag" data-id="${esc(v.id)}">
        <span class="bild">
          <img src="${esc(v.url)}" alt="${esc(txt("sichern"))} ${esc(v.zeitcode)}"
               decoding="async" fetchpriority="high">
          <a class="sichern" href="${esc(v.url)}&laden=1"
             title="${esc(txt("herunterladen"))}"
             aria-label="${esc(txt("herunterladen"))} ${esc(v.zeitcode)}">${PFEIL}</a>
        </span>
        <div class="text">
          <div class="zeile">
            <span class="zeit">${esc(v.zeitcode)}</span>
            <span class="wert">${v.gesamt}</span>
          </div>
          ${lageMarke(v, ergebnis)}
          <p>${esc(v.begruendung)}</p>
        </div>
      </article>`).join("");

    const gewaehlt = new Set(ergebnis.vorschlaege.map((v) => v.id));
    const striche = zwischenstufen
      ? (ergebnis.kandidaten || []).filter((c) => !gewaehlt.has(c.id))
        .map((c) => `<span class="strich" style="left:${(100 * c.zeit / dauer).toFixed(3)}%"></span>`)
        .join("")
      : "";
    const marken = ergebnis.vorschlaege.map((v) => `
      <button type="button" class="marke" data-id="${esc(v.id)}"
        style="left:${(100 * v.zeit / dauer).toFixed(3)}%"
        aria-label="Vorschlag bei ${esc(v.zeitcode)}"></button>`).join("");

    sichtung.innerHTML = `
      <div class="ergebnis">
        <div class="ergebnis-kopf">
          <h2>${esc(txt("fertig"))}</h2>
          <div class="kennzahlen">
            <span>${k.frames ?? "—"} ${esc(txt("frames"))}</span>
            <span>${k.kandidaten ?? "—"} ${esc(txt("kandidaten"))}</span>
            <span>${k.laufzeit ?? "—"} s</span>
            <span>${esc(ergebnis.format)}</span>
            ${k.transkript ? `<span>${esc(txt("mit_transkript"))}</span>` : ""}
          </div>
        </div>

        ${ergebnis.fallback
          ? `<p class="rueckfall">${esc(txt("rueckfall"))}</p>` : ""}

        ${ergebnis.durchlauf_erschoepft
          ? `<p class="rueckfall">${esc(txt("erschoepft"))}</p>` : ""}

        ${lageHinweis(ergebnis.motivlage_bilanz)}

        <div class="vorschlaege">${karten}</div>

        <div class="herkunft">
          <h3>${esc(txt("herkunft"))}</h3>
          <div class="leiste">
            <span class="spur"></span>${striche}${marken}
          </div>
          <div class="skala"><span>00:00</span><span>${zeitcode(dauer)}</span></div>
        </div>

        <div class="nochmal">
          <button type="button" class="schlicht" id="neue">${
            esc(txt("neue", { anzahl: ergebnis.vorschlaege.length }))}</button>
          <p class="hilfe">${esc(txt("neue_hilfe"))}</p>
        </div>
      </div>`;

    lageDichteZeigen(ergebnis.lage_dichte);
    koppeln();
    einblenden();
    $("neue").addEventListener("click", neueAuswahl);
    pruefeStart();
  }

  /* Die Lage auf der Karte ist eine Eigenschaft des Frames, keine Antwort auf
     den Wunsch. Ohne das Wort „Motiv" davor las sich „mittig links" wie eine
     Bestätigung, obwohl „oben links" gewählt war. Messing nur beim echten
     Treffer — dann trägt die Farbe die Auskunft. */
  /* Eigene Zeile, nicht neben den Zeitcode: „Motiv mittig rechts" ist länger
     als der Platz zwischen Zeitcode und Bewertung, beides stieß aneinander
     und die Zahl rutschte um. */
  function lageMarke(v, ergebnis) {
    if (!ergebnis.motivlage || ergebnis.motivlage === "egal") return "";
    if (!v.motivlage || v.motivlage === "kein_klares_motiv") return "";
    return `<p class="lage${v.lage_treffer ? " lagetreffer" : ""}">${
      esc(txt("motiv_kurz"))} ${esc(txt("lage_" + v.motivlage))}</p>`;
  }

  /* Ging der Positionswunsch nicht auf, muss das dastehen — sonst sieht die
     Auswahl aus wie eine Antwort auf die Frage, die sie gar nicht ist. */
  function lageHinweis(bilanz) {
    if (!bilanz || !bilanz.gewuenscht || bilanz.gewuenscht === "egal") return "";
    if (bilanz.stand === "genau") return "";
    const lage = txt("lage_" + bilanz.gewuenscht);
    if (bilanz.stand === "keiner")
      return `<p class="rueckfall lage">${esc(txt("lage_keiner", { lage }))}</p>`;
    // Bei genau einem Treffer braucht es die andere Verbform.
    const naehe = bilanz.stand === "naehe";
    const n = naehe ? bilanz.teilweise : bilanz.genau;
    const zusatz = n === bilanz.gesamt && naehe ? "_alle" : (n === 1 ? "_eins" : "");
    const schluessel = (naehe ? "lage_naehe" : "lage_teils") + zusatz;
    const text = txt(schluessel, { lage, n, gesamt: bilanz.gesamt });
    return `<p class="rueckfall lage">${esc(text)}</p>`;
  }

  function koppeln() {
    document.querySelectorAll("[data-id]").forEach((el) => {
      const partner = () => document.querySelectorAll(`[data-id="${el.dataset.id}"]`);
      el.addEventListener("mouseenter", () =>
        partner().forEach((p) => p.classList.add("an")));
      el.addEventListener("mouseleave", () =>
        partner().forEach((p) => p.classList.remove("an")));
      el.addEventListener("focus", () =>
        partner().forEach((p) => p.classList.add("an")));
      el.addEventListener("blur", () =>
        partner().forEach((p) => p.classList.remove("an")));
    });
  }

  /* Ein einziger choreografierter Moment: die Vorschläge blenden nacheinander
     mit 80 ms Versatz ein. */
  function einblenden() {
    const karten = document.querySelectorAll(".vorschlag");
    karten.forEach((karte, i) => {
      if (ruhig) { karte.classList.add("da"); return; }
      setTimeout(() => karte.classList.add("da"), i * 80);
    });
  }

  // --- Verlauf ------------------------------------------------------------

  async function verlaufLaden() {
    let daten;
    try {
      daten = await json("/api/verlauf");
    } catch {
      return;                       // Der Verlauf ist Beiwerk, kein Grund für einen Fehler
    }
    const liste = $("verlaufliste");
    $("verlauf").hidden = daten.eintraege.length === 0;
    liste.innerHTML = daten.eintraege.map((e) => `
      <button type="button" class="eintrag" data-job="${esc(e.job_id)}">
        <img src="${esc(e.bild)}" alt="" loading="lazy">
        <span class="text">
          <span class="titel${e.headline ? "" : " ohne"}">${
            esc(e.headline || txt("ohne_headline"))}</span>
          <span class="daten">${esc(zeitpunkt(e.erstellt))} · ${
            esc(e.format)} · ${e.anzahl}</span>
        </span>
      </button>`).join("");

    liste.querySelectorAll(".eintrag").forEach((knopf) => {
      knopf.addEventListener("click", () => verlaufOeffnen(knopf.dataset.job));
    });
  }

  async function verlaufOeffnen(jobId) {
    try {
      const daten = await json(`/api/jobs/${jobId}`);
      if (!daten.results) throw new Error(txt("verlauf_weg"));
      zustand.jobId = jobId;
      if (daten.results?.motivlage) lageSetzen(daten.results.motivlage, false);
      if (daten.results?.lage_prio) {
        zustand.lageprio = daten.results.lage_prio;
        document.querySelectorAll('[data-name="lageprio"] button').forEach((b) =>
          b.setAttribute("aria-pressed", String(b.dataset.wert === zustand.lageprio)));
      }
      zeigeErgebnis(daten.results);
      zumSichtungsbereich();
    } catch (fehler) {
      zeigeFehler(fehler.message);
    }
  }

  verlaufLaden();

  async function neueAuswahl() {
    const knopf = $("neue");
    knopf.disabled = true;
    knopf.textContent = txt("wird_neu_gewaehlt");
    try {
      await json(`/api/jobs/${zustand.jobId}/rerank`, { method: "POST" });
      const daten = await json(`/api/jobs/${zustand.jobId}`);
      zeigeErgebnis(daten.results);
    } catch (fehler) {
      zeigeFehler(fehler.message);
    }
  }
})();
