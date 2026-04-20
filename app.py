"""
Italiano Trainer – Spaced Repetition Vokabeltrainer
SM-2 Algorithmus, JSON-basiert, mit optionaler Ollama-Integration
"""

import streamlit as st
import json
import os
import uuid
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

# ─── Konfiguration ────────────────────────────────────────────────────────────

VOKABULAR_FILE = "vokabular.json"
VOKABULAR_BASIS = "vokabular_basis.json"
TRACKING_FILE  = "tracking.json"
OLLAMA_MODEL   = "gemma3:12b"
OLLAMA_URL     = "http://localhost:11434/api/chat"

# ─── SM-2 Algorithmus ─────────────────────────────────────────────────────────

def sm2_update(meta: dict, bewertung: int) -> dict:
    """
    SM-2 Update nach einer Abfrage.
    bewertung: 0-5
      0-2 = vergessen → Reset auf Intervall 1
      3-5 = gewusst   → Intervall wächst exponentiell
    """
    ef = meta.get("easiness_factor", 2.5)
    n  = meta.get("wiederholungen", 0)

    if bewertung < 3:
        n = 0
        intervall = 1
    else:
        if n == 0:
            intervall = 1
        elif n == 1:
            intervall = 6
        else:
            intervall = round(meta.get("intervall_tage", 1) * ef)
        ef = ef + (0.1 - (5 - bewertung) * (0.08 + (5 - bewertung) * 0.02))
        ef = max(1.3, round(ef, 2))
        n += 1

    return {
        "intervall_tage": intervall,
        "naechste_wiederholung": str(date.today() + timedelta(days=intervall)),
        "easiness_factor": ef,
        "wiederholungen": n,
        "letzte_bewertung": bewertung,
    }

# ─── Tracking ─────────────────────────────────────────────────────────────────

def lade_tracking() -> dict:
    if not os.path.exists(TRACKING_FILE):
        return {"tage": {}, "wochenziel": 20}
    with open(TRACKING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def speichere_tracking(t: dict):
    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2)

def tracking_karte_bewertet(bewertung: int):
    """Wird nach jeder Kartenbewertung aufgerufen. Zählt gelernte Karten pro Tag."""
    heute = str(date.today())
    t = lade_tracking()
    tag = t["tage"].setdefault(heute, {"bewertet": 0, "richtig": 0})
    tag["bewertet"] += 1
    if bewertung >= 3:
        tag["richtig"] += 1
    speichere_tracking(t)

def woche_start() -> date:
    """Montag der aktuellen Woche."""
    h = date.today()
    return h - timedelta(days=h.weekday())

def karten_diese_woche(t: dict) -> int:
    start = woche_start()
    total = 0
    for i in range(7):
        tag = str(start + timedelta(days=i))
        total += t["tage"].get(tag, {}).get("bewertet", 0)
    return total

def streak_berechnen(t: dict) -> int:
    """Anzahl aufeinanderfolgender Tage mit mind. 1 Karte."""
    streak = 0
    check = date.today()
    while True:
        eintrag = t["tage"].get(str(check), {})
        if eintrag.get("bewertet", 0) > 0:
            streak += 1
            check -= timedelta(days=1)
        else:
            break
    return streak

def kategorie_fortschritt(vok: list) -> dict:
    """
    Pro Kategorie: Anteil Karten mit easiness_factor >= 2.0 UND mind. 3 Wiederholungen
    als 'beherrscht' gewertet.
    """
    from collections import defaultdict
    gesamt = defaultdict(int)
    beherrscht = defaultdict(int)
    for k in vok:
        kat = k.get("kategorie", "?")
        gesamt[kat] += 1
        meta = k.get("meta", {})
        if meta.get("wiederholungen", 0) >= 3 and meta.get("easiness_factor", 2.5) >= 2.0:
            beherrscht[kat] += 1
    return {kat: (beherrscht[kat], gesamt[kat]) for kat in sorted(gesamt)}

# ─── Daten laden / speichern ──────────────────────────────────────────────────

def lade_vokabular() -> list:
    # vokabular.json vorhanden → laden
    if os.path.exists(VOKABULAR_FILE):
        with open(VOKABULAR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback: vokabular_basis.json als Startwert kopieren
    if os.path.exists(VOKABULAR_BASIS):
        with open(VOKABULAR_BASIS, "r", encoding="utf-8") as f:
            basis = json.load(f)
        speichere_vokabular(basis)   # direkt als vokabular.json abspeichern
        return basis
    return []

def speichere_vokabular(vok: list):
    with open(VOKABULAR_FILE, "w", encoding="utf-8") as f:
        json.dump(vok, f, ensure_ascii=False, indent=2)

def merge_vokabular(bestand: list, neu: list) -> tuple[list, int, int]:
    """
    Fügt neue Karten ein, überspringt bereits vorhandene IDs.
    Gibt (merged_list, neu_hinzugefügt, übersprungen) zurück.
    """
    vorhandene_ids = {k["id"] for k in bestand}
    hinzugefuegt = 0
    uebersprungen = 0
    for karte in neu:
        if karte.get("id") in vorhandene_ids:
            uebersprungen += 1
        else:
            # Sicherstellen dass meta-Felder vorhanden sind
            if "meta" not in karte:
                karte["meta"] = {
                    "intervall_tage": 1,
                    "naechste_wiederholung": str(date.today()),
                    "easiness_factor": 2.5,
                    "wiederholungen": 0,
                    "letzte_bewertung": None,
                }
            bestand.append(karte)
            hinzugefuegt += 1
    return bestand, hinzugefuegt, uebersprungen

def faellige_karten(vok: list, kategorie_filter=None) -> list:
    heute = str(date.today())
    ergebnis = []
    for k in vok:
        if kategorie_filter and k.get("kategorie") != kategorie_filter:
            continue
        naechste = k["meta"].get("naechste_wiederholung", heute)
        if naechste <= heute:
            ergebnis.append(k)
    return ergebnis

PERSONEN = ["io","tu","lui/lei","noi","voi","loro"]
ZEITFORMEN = {
    "presente":         "Presente",
    "passato_prossimo": "Passato Prossimo",
    "imperfetto":       "Imperfetto",
    "futuro":           "Futuro Semplice",
}

def render_konjugation_tabelle(konjugation: dict) -> str:
    """Baut eine HTML-Tabelle aus dem strukturierten konjugation-Dict."""
    rows = ""
    for zeit_key, zeit_label in ZEITFORMEN.items():
        formen = konjugation.get(zeit_key, [])
        if not formen:
            continue
        rows += f'<tr><td colspan="2" style="background:#1a1a2e;color:#f8f4ef;font-weight:600;padding:4px 10px;font-size:0.82rem;letter-spacing:0.5px">{zeit_label}</td></tr>'
        for i, form in enumerate(formen):
            person = PERSONEN[i] if i < len(PERSONEN) else ""
            bg = "#faf8f5" if i % 2 == 0 else "#ffffff"
            rows += f'<tr style="background:{bg}"><td style="color:#888;font-size:0.85rem;padding:3px 10px;width:70px">{person}</td><td style="font-weight:600;color:#c0392b;padding:3px 10px">{form}</td></tr>'
    return f'<table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;border:1px solid #e8ddd0">{rows}</table>'

def zufaellige_konjugations_frage(konjugation: dict) -> tuple[str, str, str, int]:
    """Wählt zufällig Zeitform + Person. Gibt (zeitform_label, person, antwort, person_idx) zurück."""
    import random
    zeitform_key = random.choice(list(ZEITFORMEN.keys()))
    formen = konjugation.get(zeitform_key, [])
    person_idx = random.randint(0, len(formen) - 1)
    return ZEITFORMEN[zeitform_key], PERSONEN[person_idx], formen[person_idx], person_idx

def alle_kategorien(vok: list) -> list:
    return sorted(set(k.get("kategorie", "Allgemein") for k in vok))

def ollama_konjugiert(wort_de: str, wort_it: str) -> str:
    """Lässt Ollama die Konjugation in 4 Zeitformen erklären (mit Beispielsätzen)."""
    try:
        import urllib.request
        import streamlit as _st
        model   = _st.session_state.get("ollama_model_aktiv", OLLAMA_MODEL)
        timeout = _st.session_state.get("ollama_timeout", 60)
        payload = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Sei un insegnante di italiano per un tedesco. "
                        "Mostra la coniugazione del verbo nei tempi: Presente, Passato Prossimo, "
                        "Imperfetto e Futuro Semplice. Formato: tabella con io/tu/lui-lei/noi/voi/loro. "
                        "Aggiungi per ogni tempo un esempio pratico (contesto: costruzione o vita in Toscana). "
                        "Rispondi in italiano con traduzioni tedesche tra parentesi dove utile."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Coniuga il verbo '{wort_it}' (tedesco: '{wort_de}').",
                },
            ],
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data["message"]["content"]
    except Exception as e:
        return f"⚠️ Ollama nicht erreichbar: {e}"


def ollama_erklaere(wort_de: str, wort_it: str, beispiel: str) -> str:
    """Fragt Ollama nach einer Erklärung mit Grammatikhinweis."""
    try:
        import urllib.request
        import streamlit as _st
        model   = _st.session_state.get("ollama_model_aktiv", OLLAMA_MODEL)
        timeout = _st.session_state.get("ollama_timeout", 60)
        payload = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Sei un insegnante di italiano per un tedesco che impara l'italiano "
                        "soprattutto per lavori di costruzione e vita quotidiana in Toscana. "
                        "Spiega brevemente (3-5 frasi), dai un suggerimento grammaticale se utile, "
                        "e proponi un secondo esempio pratico. Rispondi in italiano e tedesco."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Spiega la parola italiana: '{wort_it}' (tedesco: '{wort_de}'). "
                        f"Esempio già noto: {beispiel}"
                    ),
                },
            ],
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data["message"]["content"]
    except Exception as e:
        return f"⚠️ Ollama nicht erreichbar: {e}"

# ─── Session State initialisieren ─────────────────────────────────────────────

def init_state():
    if "vokabular" not in st.session_state:
        st.session_state.vokabular = lade_vokabular()
    if "lern_queue" not in st.session_state:
        st.session_state.lern_queue = []
    if "lern_index" not in st.session_state:
        st.session_state.lern_index = 0
    if "zeige_antwort" not in st.session_state:
        st.session_state.zeige_antwort = False
    if "session_stats" not in st.session_state:
        st.session_state.session_stats = {"richtig": 0, "falsch": 0}
    if "ollama_erklaerung" not in st.session_state:
        st.session_state.ollama_erklaerung = ""
    if "ollama_konjugation" not in st.session_state:
        st.session_state.ollama_konjugation = ""
    if "konj_frage" not in st.session_state:
        st.session_state.konj_frage = None   # (zeitform, person, antwort, idx)
    if "konj_zeige_antwort" not in st.session_state:
        st.session_state.konj_zeige_antwort = False
    if "aktive_kategorie" not in st.session_state:
        st.session_state.aktive_kategorie = "Alle"
    if "lernmodus_alle" not in st.session_state:
        st.session_state.lernmodus_alle = False
    if "ollama_model_aktiv" not in st.session_state:
        st.session_state.ollama_model_aktiv = OLLAMA_MODEL

# ─── UI Styling ───────────────────────────────────────────────────────────────

def apply_style():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Sans+3:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Source Sans 3', sans-serif;
    }

    .main-title {
        font-family: 'Playfair Display', serif;
        font-size: 2.4rem;
        font-weight: 700;
        color: #1a1a2e;
        letter-spacing: -0.5px;
        margin-bottom: 0;
    }
    .subtitle {
        color: #6b7280;
        font-size: 0.95rem;
        font-weight: 300;
        margin-top: 2px;
    }

    .karte {
        background: linear-gradient(135deg, #fefefe 0%, #f8f4ef 100%);
        border: 1.5px solid #e8ddd0;
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin: 1rem 0;
        box-shadow: 0 4px 20px rgba(139,90,43,0.08);
    }
    .wort-de {
        font-family: 'Playfair Display', serif;
        font-size: 2rem;
        font-weight: 600;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .wort-it {
        font-size: 2.2rem;
        font-weight: 600;
        color: #c0392b;
        font-family: 'Playfair Display', serif;
    }
    .beispiel {
        font-size: 0.95rem;
        color: #555;
        font-style: italic;
        margin-top: 0.8rem;
        padding-top: 0.8rem;
        border-top: 1px solid #e0d5c8;
    }
    .tag {
        display: inline-block;
        background: #1a1a2e;
        color: #f8f4ef;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        padding: 3px 10px;
        border-radius: 20px;
        margin-bottom: 1rem;
    }

    .stat-box {
        background: #1a1a2e;
        color: white;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        text-align: center;
    }
    .stat-zahl {
        font-size: 2rem;
        font-weight: 700;
        font-family: 'Playfair Display', serif;
    }
    .stat-label {
        font-size: 0.8rem;
        opacity: 0.7;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    div[data-testid="stButton"] > button {
        border-radius: 8px;
        font-family: 'Source Sans 3', sans-serif;
        font-weight: 600;
        transition: all 0.15s ease;
    }

    .ollama-box {
        background: #f0f4ff;
        border-left: 3px solid #3b5bdb;
        border-radius: 0 10px 10px 0;
        padding: 1rem 1.2rem;
        margin-top: 1rem;
        font-size: 0.92rem;
        color: #2c3e50;
    }
    </style>
    """, unsafe_allow_html=True)

# ─── Seiten ───────────────────────────────────────────────────────────────────

def seite_lernen():
    vok = st.session_state.vokabular

    if not vok:
        st.info("📂 Kein Vokabular geladen. Bitte zuerst JSON importieren (Seite 'Importieren').")
        return

    kategorien = ["Alle"] + alle_kategorien(vok)
    kat_filter = st.selectbox("Kategorie", kategorien, key="lern_kat")
    filter_val = None if kat_filter == "Alle" else kat_filter

    # Queue neu aufbauen wenn Kategorie gewechselt wurde
    if kat_filter != st.session_state.aktive_kategorie:
        st.session_state.aktive_kategorie = kat_filter
        st.session_state.lern_queue = []
        st.session_state.lern_index = 0
        st.session_state.zeige_antwort = False
        st.session_state.session_stats = {"richtig": 0, "falsch": 0}
        st.session_state.ollama_erklaerung = ""

    faellig = faellige_karten(vok, filter_val)

    # Im Review-Modus alle Karten der Kategorie zeigen
    if st.session_state.lernmodus_alle:
        karten_fuer_session = [k for k in vok if filter_val is None or k.get("kategorie") == filter_val]
    else:
        karten_fuer_session = faellig

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""<div class="stat-box"><div class="stat-zahl">{len(faellig)}</div>
        <div class="stat-label">Fällig heute</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="stat-box"><div class="stat-zahl">{st.session_state.session_stats['richtig']}</div>
        <div class="stat-label">Richtig</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="stat-box"><div class="stat-zahl">{st.session_state.session_stats['falsch']}</div>
        <div class="stat-label">Wiederholen</div></div>""", unsafe_allow_html=True)

    st.markdown("---")

    if not karten_fuer_session:
        if st.session_state.lernmodus_alle:
            st.info("Keine Karten in dieser Kategorie.")
        else:
            st.success("🎉 **Perfetto!** Keine fälligen Karten für heute. Domani si studia ancora!")
            st.info("💡 Tipp: Wechsle in der Sidebar auf **'Alle Karten (Review)'** um trotzdem zu üben.")
        return

    # Queue aufbauen wenn leer oder Session abgeschlossen
    if not st.session_state.lern_queue or st.session_state.lern_index >= len(st.session_state.lern_queue):
        import random

        if st.session_state.lernmodus_alle:
            # Reihenfolge wählen
            reihenfolge = st.radio(
                "Reihenfolge",
                ["🔀 Zufällig", "📋 Alphabetisch (DE)", "📋 Alphabetisch (IT)", "🎯 Ab bestimmter Karte"],
                horizontal=True,
                key="review_reihenfolge",
            )

            karten_sortiert = list(karten_fuer_session)
            startindex = 0

            if reihenfolge == "🔀 Zufällig":
                random.shuffle(karten_sortiert)
            elif reihenfolge == "📋 Alphabetisch (DE)":
                karten_sortiert.sort(key=lambda k: k["de"].lower())
            elif reihenfolge == "📋 Alphabetisch (IT)":
                karten_sortiert.sort(key=lambda k: k["it"].lower())
            elif reihenfolge == "🎯 Ab bestimmter Karte":
                karten_sortiert.sort(key=lambda k: k["de"].lower())
                optionen = [f"{k['de']} → {k['it']}" for k in karten_sortiert]
                start_auswahl = st.selectbox("Starten ab:", optionen, key="review_startkarte")
                startindex = optionen.index(start_auswahl)

            if st.button("▶️ Session starten", type="primary"):
                ids = [k["id"] for k in karten_sortiert]
                st.session_state.lern_queue = ids[startindex:]
                st.session_state.lern_index = 0
                st.session_state.zeige_antwort = False
                st.session_state.session_stats = {"richtig": 0, "falsch": 0}
                st.rerun()
            return
        else:
            # Fällige Karten: immer zufällig
            karten_sortiert = list(karten_fuer_session)
            random.shuffle(karten_sortiert)
            st.session_state.lern_queue = [k["id"] for k in karten_sortiert]
            st.session_state.lern_index = 0
            st.session_state.zeige_antwort = False

    idx = st.session_state.lern_index
    if idx >= len(st.session_state.lern_queue):
        st.success("✅ Session abgeschlossen!")
        st.session_state.session_stats = {"richtig": 0, "falsch": 0}
        return

    karten_id = st.session_state.lern_queue[idx]
    karte = next((k for k in vok if k["id"] == karten_id), None)
    if karte is None:
        st.session_state.lern_index += 1
        st.rerun()

    richtung = st.radio("Abfragerichtung", ["🇩🇪 → 🇮🇹", "🇮🇹 → 🇩🇪"], horizontal=True, key="richtung")

    # Fortschritt + Überspringen in einer Zeile
    prog_col, skip_col = st.columns([3, 1])
    with prog_col:
        st.markdown(f"**Karte {idx+1} / {len(st.session_state.lern_queue)}**")
    with skip_col:
        if st.button("⏭ Überspringen"):
            st.session_state.lern_index += 1
            st.session_state.zeige_antwort = False
            st.session_state.ollama_erklaerung = ""
            st.rerun()

    if richtung == "🇩🇪 → 🇮🇹":
        frage, antwort = karte["de"], karte["it"]
        beispiel_frage = karte.get("beispiel_de", "")
        beispiel_antwort = karte.get("beispiel_it", "")
    else:
        frage, antwort = karte["it"], karte["de"]
        beispiel_frage = karte.get("beispiel_it", "")
        beispiel_antwort = karte.get("beispiel_de", "")

    st.markdown(f"""
    <div class="karte">
        <div class="tag">{karte.get('kategorie','?')}</div><br>
        <div class="wort-de">{frage}</div>
        <div class="beispiel">{beispiel_frage}</div>
    </div>""", unsafe_allow_html=True)

    if not st.session_state.zeige_antwort:
        if st.button("👁 Antwort zeigen", type="primary"):
            st.session_state.zeige_antwort = True
            st.session_state.ollama_erklaerung = ""
            st.rerun()
    else:
        erklaerung = karte.get("erklaerung", "")
        erklaerung_html = f'<div class="beispiel" style="color:#3b5bdb"><b>📖</b> {erklaerung}</div>' if erklaerung else ""
        st.markdown(f"""
        <div class="karte">
            <div class="wort-it">{antwort}</div>
            <div class="beispiel">{beispiel_antwort}</div>
            {erklaerung_html}
        </div>""", unsafe_allow_html=True)

        # Bewertungsbuttons
        st.markdown("**Wie gut wusstest du es?**")
        b1, b2, b3, b4 = st.columns(4)
        def bewerter(note):
            # Karte in vokabular updaten
            for i, k in enumerate(st.session_state.vokabular):
                if k["id"] == karten_id:
                    st.session_state.vokabular[i]["meta"] = sm2_update(k["meta"], note)
                    break
            speichere_vokabular(st.session_state.vokabular)
            tracking_karte_bewertet(note)
            if note >= 3:
                st.session_state.session_stats["richtig"] += 1
            else:
                st.session_state.session_stats["falsch"] += 1
            st.session_state.lern_index += 1
            st.session_state.zeige_antwort = False
            st.session_state.ollama_erklaerung = ""
            st.session_state.ollama_konjugation = ""
            st.session_state.konj_frage = None
            st.session_state.konj_zeige_antwort = False

        with b1:
            if st.button("😵 Vergessen\n(0)"):
                bewerter(0); st.rerun()
        with b2:
            if st.button("😕 Schwer\n(2)"):
                bewerter(2); st.rerun()
        with b3:
            if st.button("🙂 Gut\n(4)"):
                bewerter(4); st.rerun()
        with b4:
            if st.button("😎 Sofort\n(5)"):
                bewerter(5); st.rerun()

    # ── Ollama / Konjugation – immer sichtbar, unabhängig von Antwort ──────────
    st.markdown("---")
    ist_verb = karte.get("kategorie") == "Verben"
    konj = karte.get("konjugation") if ist_verb else None
    hat_strukturierte_konj = isinstance(konj, dict)
    cache = karte.get("cache", {})
    hat_erklaerung_cache  = bool(cache.get("ollama_erklaerung"))
    hat_konjugation_cache = bool(cache.get("ollama_konjugation"))

    def speichere_cache(feld: str, wert: str):
        """Schreibt Ollama-Antwort in cache-Feld der Karte und speichert vokabular.json."""
        for i, k in enumerate(st.session_state.vokabular):
            if k["id"] == karten_id:
                if "cache" not in st.session_state.vokabular[i]:
                    st.session_state.vokabular[i]["cache"] = {}
                st.session_state.vokabular[i]["cache"][feld] = wert
                break
        speichere_vokabular(st.session_state.vokabular)

    # Buttons: Zeile 1 – Ollama Erklärung
    oc1, oc2 = st.columns(2)
    with oc1:
        label_erkl = "🤖 Ollama erklärt ✅" if hat_erklaerung_cache else "🤖 Ollama erklärt"
        if st.button(label_erkl):
            if hat_erklaerung_cache:
                st.session_state.ollama_erklaerung = cache["ollama_erklaerung"]
            else:
                with st.spinner("Ollama denkt nach..."):
                    result = ollama_erklaere(karte["de"], karte["it"], karte.get("beispiel_it", ""))
                    st.session_state.ollama_erklaerung = result
                    speichere_cache("ollama_erklaerung", result)
            st.session_state.ollama_konjugation = ""
            st.session_state.konj_frage = None
            st.rerun()
    with oc2:
        if ist_verb:
            label_konj = "🤖 Ollama konjugiert ✅" if hat_konjugation_cache else "🤖 Ollama konjugiert"
            if st.button(label_konj):
                if hat_konjugation_cache:
                    st.session_state.ollama_konjugation = cache["ollama_konjugation"]
                else:
                    with st.spinner("Ollama konjugiert..."):
                        result = ollama_konjugiert(karte["de"], karte["it"])
                        st.session_state.ollama_konjugation = result
                        speichere_cache("ollama_konjugation", result)
                st.session_state.ollama_erklaerung = ""
                st.session_state.konj_frage = None
                st.rerun()

    # Buttons: Zeile 2 – lokal (nur wenn strukturierte Konjugation vorhanden)
    if hat_strukturierte_konj:
        kc1, kc2 = st.columns(2)
        with kc1:
            if st.button("📋 Konjugationstabelle"):
                st.session_state.ollama_konjugation = "tabelle"
                st.session_state.ollama_erklaerung = ""
                st.session_state.konj_frage = None
                st.rerun()
        with kc2:
            if st.button("🎯 Konjugations-Quiz"):
                st.session_state.konj_frage = zufaellige_konjugations_frage(konj)
                st.session_state.konj_zeige_antwort = False
                st.session_state.ollama_erklaerung = ""
                st.session_state.ollama_konjugation = ""
                st.rerun()

    # Cache löschen (nur wenn Cache vorhanden)
    if hat_erklaerung_cache or hat_konjugation_cache:
        with st.expander("🗑 Cache dieser Karte löschen"):
            cc1, cc2 = st.columns(2)
            with cc1:
                if hat_erklaerung_cache and st.button("Erklärung löschen"):
                    speichere_cache("ollama_erklaerung", "")
                    st.session_state.ollama_erklaerung = ""
                    st.rerun()
            with cc2:
                if hat_konjugation_cache and st.button("Konjugation löschen"):
                    speichere_cache("ollama_konjugation", "")
                    st.session_state.ollama_konjugation = ""
                    st.rerun()

    # Ausgabe: Ollama Erklärung
    if st.session_state.ollama_erklaerung:
        st.markdown(f"""<div class="ollama-box">{st.session_state.ollama_erklaerung}</div>""",
                    unsafe_allow_html=True)

    # Ausgabe: Ollama Konjugation (Text)
    if st.session_state.ollama_konjugation and st.session_state.ollama_konjugation != "tabelle":
        st.markdown(f"""<div class="ollama-box">{st.session_state.ollama_konjugation}</div>""",
                    unsafe_allow_html=True)

    # Ausgabe: Konjugationstabelle aus JSON
    if st.session_state.ollama_konjugation == "tabelle" and hat_strukturierte_konj:
        st.markdown(render_konjugation_tabelle(konj), unsafe_allow_html=True)

    # Ausgabe: Konjugations-Quiz
    if st.session_state.konj_frage:
        zeitform, person, antwort_konj, _ = st.session_state.konj_frage
        st.markdown(f"""
        <div class="karte" style="margin-top:0.8rem">
            <div class="tag">Konjugation Quiz</div><br>
            <div style="font-size:1rem;color:#555">Wie lautet <b>{karte['it']}</b> für</div>
            <div class="wort-de">{person} &nbsp;·&nbsp; {zeitform}</div>
        </div>""", unsafe_allow_html=True)

        if not st.session_state.konj_zeige_antwort:
            if st.button("👁 Antwort zeigen", key="konj_antwort_btn"):
                st.session_state.konj_zeige_antwort = True
                st.rerun()
        else:
            st.markdown(f"""
            <div class="karte" style="margin-top:0">
                <div class="wort-it">{antwort_konj}</div>
            </div>""", unsafe_allow_html=True)
            ka, kb = st.columns(2)
            with ka:
                if st.button("✅ Neue Frage"):
                    st.session_state.konj_frage = zufaellige_konjugations_frage(konj)
                    st.session_state.konj_zeige_antwort = False
                    st.rerun()
            with kb:
                if st.button("❌ Schließen"):
                    st.session_state.konj_frage = None
                    st.session_state.konj_zeige_antwort = False
                    st.rerun()



def seite_statistik():
    vok = st.session_state.vokabular
    if not vok:
        st.info("Kein Vokabular geladen.")
        return

    df = pd.DataFrame([{
        "ID": k["id"],
        "Deutsch": k["de"],
        "Italienisch": k["it"],
        "Kategorie": k.get("kategorie", "?"),
        "Wiederholungen": k["meta"]["wiederholungen"],
        "Nächste Wiederholung": k["meta"]["naechste_wiederholung"],
        "Easiness Factor": k["meta"]["easiness_factor"],
        "Letzte Bewertung": k["meta"]["letzte_bewertung"],
        "Intervall (Tage)": k["meta"]["intervall_tage"],
    } for k in vok])

    heute = str(date.today())
    faellig = (df["Nächste Wiederholung"] <= heute).sum()
    gelernt = (df["Wiederholungen"] > 0).sum()

    c1, c2, c3, c4 = st.columns(4)
    metriken = [
        (len(vok), "Gesamt"),
        (faellig, "Heute fällig"),
        (gelernt, "Schon gelernt"),
        (len(vok) - gelernt, "Noch neu"),
    ]
    for col, (zahl, label) in zip([c1,c2,c3,c4], metriken):
        with col:
            st.markdown(f"""<div class="stat-box"><div class="stat-zahl">{zahl}</div>
            <div class="stat-label">{label}</div></div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Kategorien-Verteilung
    st.subheader("Nach Kategorie")
    kat_counts = df["Kategorie"].value_counts().reset_index()
    kat_counts.columns = ["Kategorie", "Anzahl"]
    st.bar_chart(kat_counts.set_index("Kategorie"))

    # Fortschrittstabelle
    st.subheader("Alle Karten")
    st.dataframe(
        df[["Deutsch", "Italienisch", "Kategorie", "Wiederholungen",
            "Intervall (Tage)", "Nächste Wiederholung", "Letzte Bewertung"]],
        use_container_width=True,
        hide_index=True,
    )


def seite_importieren():
    st.subheader("📂 Vokabular importieren")
    st.markdown("""
    Lade eine JSON-Datei im Format:
    ```json
    [
      {
        "id": "eindeutige_id",
        "de": "das Wort",
        "it": "la parola",
        "kategorie": "Bauwesen",
        "beispiel_it": "Beispielsatz auf Italienisch.",
        "beispiel_de": "Beispielsatz auf Deutsch."
      },
      ...
    ]
    ```
    """)

    import_modus = st.radio(
        "Importmodus",
        ["➕ Nur neue Karten (Lernfortschritt bleibt)", "🔄 Ersetzen (Inhalt + Konjugation aktualisieren, Fortschritt bleibt)"],
        key="import_modus",
    )

    uploaded = st.file_uploader("JSON-Datei hochladen", type=["json"])
    if uploaded:
        try:
            neu = json.load(uploaded)
            if not isinstance(neu, list):
                st.error("❌ Datei muss eine JSON-Liste sein.")
                return

            bestand = st.session_state.vokabular

            if import_modus.startswith("➕"):
                merged, hinzu, ueber = merge_vokabular(bestand, neu)
                st.session_state.vokabular = merged
                speichere_vokabular(merged)
                st.success(f"✅ {hinzu} neue Karten hinzugefügt, {ueber} bereits vorhandene übersprungen.")
            else:
                # Ersetzen: Inhalt (de/it/kategorie/beispiel/konjugation) aktualisieren,
                # aber meta (Lernfortschritt) aus dem Bestand behalten
                bestand_by_id = {k["id"]: k for k in bestand}
                ersetzt = 0
                hinzu = 0
                for karte in neu:
                    kid = karte.get("id")
                    if kid in bestand_by_id:
                        # Inhalt übernehmen, meta behalten
                        alter_meta = bestand_by_id[kid].get("meta", {})
                        bestand_by_id[kid] = {**karte, "meta": alter_meta}
                        ersetzt += 1
                    else:
                        # Neue Karte: meta initialisieren falls fehlend
                        if "meta" not in karte:
                            karte["meta"] = {
                                "intervall_tage": 1,
                                "naechste_wiederholung": str(date.today()),
                                "easiness_factor": 2.5,
                                "wiederholungen": 0,
                                "letzte_bewertung": None,
                            }
                        bestand_by_id[kid] = karte
                        hinzu += 1
                merged = list(bestand_by_id.values())
                st.session_state.vokabular = merged
                speichere_vokabular(merged)
                st.success(f"✅ {ersetzt} Karten aktualisiert, {hinzu} neu hinzugefügt. Lernfortschritt bleibt erhalten.")

        except Exception as e:
            st.error(f"❌ Fehler beim Lesen der Datei: {e}")

    st.markdown("---")
    st.subheader("📤 Aktuelles Vokabular exportieren")
    if st.session_state.vokabular:
        export_str = json.dumps(st.session_state.vokabular, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ Vokabular als JSON herunterladen",
            data=export_str,
            file_name="vokabular_export.json",
            mime="application/json",
        )


def seite_editor():
    st.subheader("✏️ Neue Karte hinzufügen")

    kategorien_vorschlaege = alle_kategorien(st.session_state.vokabular) or [
        "Bauwesen", "Heizung/HVAC", "Alltag", "Essen & Einkaufen", "Grammatik"
    ]

    with st.form("neue_karte"):
        c1, c2 = st.columns(2)
        with c1:
            de = st.text_input("Deutsch *")
        with c2:
            it = st.text_input("Italienisch *")

        kat = st.selectbox("Kategorie", kategorien_vorschlaege + ["── Neue Kategorie ──"])
        neue_kat = ""
        if kat == "── Neue Kategorie ──":
            neue_kat = st.text_input("Neue Kategorie eingeben")

        c3, c4 = st.columns(2)
        with c3:
            bsp_de = st.text_area("Beispielsatz Deutsch", height=80)
        with c4:
            bsp_it = st.text_area("Beispielsatz Italienisch", height=80)

        submitted = st.form_submit_button("➕ Karte hinzufügen", type="primary")

    if submitted:
        if not de or not it:
            st.error("Deutsch und Italienisch sind Pflichtfelder.")
        else:
            finale_kat = neue_kat if neue_kat else kat
            neue_id = f"user_{uuid.uuid4().hex[:8]}"
            neue_karte = {
                "id": neue_id,
                "de": de,
                "it": it,
                "kategorie": finale_kat,
                "beispiel_de": bsp_de,
                "beispiel_it": bsp_it,
                "meta": {
                    "intervall_tage": 1,
                    "naechste_wiederholung": str(date.today()),
                    "easiness_factor": 2.5,
                    "wiederholungen": 0,
                    "letzte_bewertung": None,
                },
            }
            st.session_state.vokabular.append(neue_karte)
            speichere_vokabular(st.session_state.vokabular)
            st.success(f"✅ Karte '{de}' → '{it}' hinzugefügt!")

    # Karten löschen
    st.markdown("---")
    st.subheader("🗑️ Karte löschen")
    vok = st.session_state.vokabular
    if vok:
        optionen = {f"{k['de']} → {k['it']} [{k.get('kategorie','?')}]": k["id"] for k in vok}
        auswahl = st.selectbox("Karte auswählen", list(optionen.keys()))
        if st.button("🗑️ Löschen", type="secondary"):
            del_id = optionen[auswahl]
            st.session_state.vokabular = [k for k in vok if k["id"] != del_id]
            speichere_vokabular(st.session_state.vokabular)
            st.success("Karte gelöscht.")
            st.rerun()

    # ── Ollama Kartengenerator ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🤖 Karte von Ollama generieren lassen")
    st.caption("Stelle eine freie Frage – Ollama erstellt daraus eine fertige Lernkarte.")

    beispiele = [
        "Wann verwendet man 'gli' statt 'le'?",
        "Was ist der Unterschied zwischen 'sapere' und 'conoscere'?",
        "Wie funktioniert der Congiuntivo?",
        "Wann benutzt man 'passato prossimo' vs 'imperfetto'?",
        "Was bedeutet 'ci' in 'ci sono'?",
        "Wie bildet man Adjektive mit -issimo?",
    ]
    st.caption("Beispiele: " + " · ".join(f"_{b}_" for b in beispiele[:3]))

    frage_input = st.text_input(
        "Deine Frage",
        placeholder="z.B. Wann verwendet man 'gli'?",
        key="gen_frage",
    )
    kat_input = st.selectbox(
        "Kategorie für die neue Karte",
        ["Grammatik"] + alle_kategorien(st.session_state.vokabular),
        key="gen_kategorie",
    )

    if "gen_vorschau" not in st.session_state:
        st.session_state.gen_vorschau = None

    if st.button("✨ Karte generieren", type="primary"):
        if not frage_input.strip():
            st.error("Bitte eine Frage eingeben.")
        else:
            with st.spinner("Ollama erstellt die Karte..."):
                st.session_state.gen_vorschau = ollama_generiere_karte(frage_input, kat_input)
            st.rerun()

    # Vorschau der generierten Karte
    if st.session_state.gen_vorschau:
        karte_v = st.session_state.gen_vorschau

        if "_fehler" in karte_v:
            st.error(karte_v["_fehler"])
        else:
            st.markdown("**Vorschau:**")
            st.markdown(f"""
            <div class="karte">
                <div class="tag">{karte_v.get('kategorie','Grammatik')}</div><br>
                <div class="wort-de">{karte_v.get('de','')}</div>
                <div class="wort-it" style="font-size:1.3rem;margin-top:0.3rem">{karte_v.get('it','')}</div>
                <div class="beispiel"><b>🇮🇹</b> {karte_v.get('beispiel_it','')}</div>
                <div class="beispiel"><b>🇩🇪</b> {karte_v.get('beispiel_de','')}</div>
                {"<div class='beispiel' style='color:#3b5bdb'><b>📖</b> " + karte_v.get('erklaerung','') + "</div>" if karte_v.get('erklaerung') else ""}
            </div>""", unsafe_allow_html=True)

            # Felder editierbar machen vor dem Speichern
            with st.expander("✏️ Felder anpassen vor dem Speichern"):
                karte_v["de"]          = st.text_input("Deutsch",       karte_v.get("de",""),          key="gen_de")
                karte_v["it"]          = st.text_input("Italienisch",    karte_v.get("it",""),          key="gen_it")
                karte_v["kategorie"]   = st.text_input("Kategorie",      karte_v.get("kategorie","Grammatik"), key="gen_kat2")
                karte_v["beispiel_de"] = st.text_input("Beispiel DE",    karte_v.get("beispiel_de",""), key="gen_bde")
                karte_v["beispiel_it"] = st.text_input("Beispiel IT",    karte_v.get("beispiel_it",""), key="gen_bit")
                karte_v["erklaerung"]  = st.text_area("Erklärung",       karte_v.get("erklaerung",""),  key="gen_erkl", height=100)

            sa, sb = st.columns(2)
            with sa:
                if st.button("✅ Ins Vokabular übernehmen", type="primary"):
                    neue_id = f"gen_{uuid.uuid4().hex[:8]}"
                    neue_karte = {
                        "id":          neue_id,
                        "de":          karte_v.get("de",""),
                        "it":          karte_v.get("it",""),
                        "kategorie":   karte_v.get("kategorie","Grammatik"),
                        "beispiel_de": karte_v.get("beispiel_de",""),
                        "beispiel_it": karte_v.get("beispiel_it",""),
                        "erklaerung":  karte_v.get("erklaerung",""),
                        "meta": {
                            "intervall_tage": 1,
                            "naechste_wiederholung": str(date.today()),
                            "easiness_factor": 2.5,
                            "wiederholungen": 0,
                            "letzte_bewertung": None,
                        },
                    }
                    st.session_state.vokabular.append(neue_karte)
                    speichere_vokabular(st.session_state.vokabular)
                    st.session_state.gen_vorschau = None
                    st.success(f"✅ Karte '{neue_karte['de']}' gespeichert!")
                    st.rerun()
            with sb:
                if st.button("🔄 Neu generieren"):
                    with st.spinner("Ollama versucht es nochmal..."):
                        st.session_state.gen_vorschau = ollama_generiere_karte(frage_input, kat_input)
                    st.rerun()


# ─── Ollama Kartengenerator ───────────────────────────────────────────────────

def ollama_generiere_karte(frage: str, kategorie: str) -> dict | None:
    """
    Sendet eine freie Frage an Ollama und erhält eine fertige Lernkarte als JSON zurück.
    """
    try:
        import urllib.request
        import streamlit as _st
        model   = _st.session_state.get("ollama_model_aktiv", OLLAMA_MODEL)
        timeout = _st.session_state.get("ollama_timeout", 60)

        system = """Sei un insegnante di italiano esperto. L'utente fa una domanda grammaticale o lessicale.
Il tuo compito è creare UNA scheda di vocabolario/grammatica in formato JSON.

Rispondi SOLO con un oggetto JSON valido, senza testo prima o dopo, senza ```json```.
Formato esatto:
{
  "de": "Kurze deutsche Beschreibung/Regel (max 60 Zeichen)",
  "it": "Italiano: die Antwort / Regel auf Italienisch",
  "kategorie": "Grammatik",
  "beispiel_it": "Esempio frase in italiano.",
  "beispiel_de": "Beispielsatz auf Deutsch.",
  "erklaerung": "Ausführliche Erklärung auf Deutsch (2-4 Sätze), mit konkreten Beispielen."
}

Regeln:
- "de" und "it" sind kurz (Kartenformat)
- "erklaerung" ist ausführlich auf Deutsch
- Kategorie immer "Grammatik" ausser se è chiaramente altro
- Nessun testo fuori dal JSON"""

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": frage},
            ],
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            text = data["message"]["content"].strip()
            # JSON aus Antwort extrahieren (robust gegen Markdown-Fences)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            karte = json.loads(text.strip())
            # Pflichtfelder sicherstellen
            karte.setdefault("kategorie", kategorie or "Grammatik")
            karte.setdefault("beispiel_it", "")
            karte.setdefault("beispiel_de", "")
            karte.setdefault("erklaerung", "")
            return karte
    except json.JSONDecodeError as e:
        return {"_fehler": f"Ollama hat kein gültiges JSON zurückgegeben: {e}"}
    except Exception as e:
        return {"_fehler": f"Ollama nicht erreichbar: {e}"}


# ─── Fortschritt ──────────────────────────────────────────────────────────────

def seite_fortschritt():
    t = lade_tracking()
    vok = st.session_state.vokabular
    heute = str(date.today())

    # ── Wochenziel einstellen ─────────────────────────────────────────────────
    st.subheader("🎯 Wochenziel")
    ziel = st.slider("Karten pro Woche", 10, 100, t.get("wochenziel", 20), 5,
                     key="wochenziel_slider")
    if ziel != t.get("wochenziel", 20):
        t["wochenziel"] = ziel
        speichere_tracking(t)

    karten_woche = karten_diese_woche(t)
    prozent = min(100, int(karten_woche / ziel * 100))
    streak = streak_berechnen(t)
    heute_count = t["tage"].get(heute, {}).get("bewertet", 0)

    # ── Top-Metriken ──────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    metriken = [
        (f"{karten_woche} / {ziel}", "Diese Woche"),
        (f"{prozent}%", "Wochenziel"),
        (f"{streak} 🔥", "Tage in Folge"),
        (f"{heute_count}", "Heute"),
    ]
    for col, (zahl, label) in zip([m1, m2, m3, m4], metriken):
        with col:
            st.markdown(f"""<div class="stat-box">
                <div class="stat-zahl">{zahl}</div>
                <div class="stat-label">{label}</div>
            </div>""", unsafe_allow_html=True)

    # ── Wochenfortschrittsbalken ──────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    farbe = "#27ae60" if prozent >= 100 else "#c0392b" if prozent < 40 else "#e67e22"
    st.markdown(f"""
    <div style="background:#e8ddd0;border-radius:20px;height:22px;overflow:hidden;margin-bottom:6px">
      <div style="width:{prozent}%;background:{farbe};height:100%;border-radius:20px;
                  transition:width 0.4s ease;display:flex;align-items:center;
                  justify-content:flex-end;padding-right:8px">
        <span style="color:white;font-size:0.75rem;font-weight:700">{prozent}%</span>
      </div>
    </div>
    <div style="font-size:0.82rem;color:#888;margin-bottom:1.5rem">
      {karten_woche} von {ziel} Karten diese Woche
    </div>""", unsafe_allow_html=True)

    if prozent >= 100:
        st.success("🎉 **Wochenziel erreicht! Ottimo lavoro!**")
    elif prozent >= 70:
        st.info(f"💪 Fast geschafft – noch {ziel - karten_woche} Karten!")
    else:
        st.warning(f"📚 Noch {ziel - karten_woche} Karten bis zum Wochenziel.")

    # ── Aktivität der letzten 4 Wochen ────────────────────────────────────────
    st.markdown("---")
    st.subheader("📅 Aktivität (letzte 28 Tage)")

    tage_html = ""
    for i in range(27, -1, -1):
        tag = str(date.today() - timedelta(days=i))
        count = t["tage"].get(tag, {}).get("bewertet", 0)
        if count == 0:
            farbe_tag = "#e8ddd0"
        elif count < 5:
            farbe_tag = "#a8d5a2"
        elif count < 15:
            farbe_tag = "#5cb85c"
        else:
            farbe_tag = "#27ae60"
        tage_html += f'<div title="{tag}: {count} Karten" style="width:18px;height:18px;border-radius:3px;background:{farbe_tag};display:inline-block;margin:2px"></div>'

    st.markdown(f"""
    <div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:0.5rem">{tage_html}</div>
    <div style="font-size:0.78rem;color:#aaa">
      ⬜ 0 &nbsp; 🟩 1–4 &nbsp; 🟢 5–14 &nbsp; 🟫 15+
    </div>""", unsafe_allow_html=True)

    # ── Fortschritt pro Kategorie ─────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Fortschritt pro Kategorie")
    st.caption("'Beherrscht' = mind. 3 Wiederholungen mit Easiness Factor ≥ 2.0")

    fortschritt = kategorie_fortschritt(vok)
    if not fortschritt:
        st.info("Noch keine Karten bewertet.")
        return

    for kat, (gut, total) in fortschritt.items():
        pct = int(gut / total * 100) if total > 0 else 0
        farbe_kat = "#27ae60" if pct >= 80 else "#e67e22" if pct >= 40 else "#c0392b"
        st.markdown(f"""
        <div style="margin-bottom:0.9rem">
          <div style="display:flex;justify-content:space-between;margin-bottom:3px">
            <span style="font-weight:600;font-size:0.9rem">{kat}</span>
            <span style="font-size:0.85rem;color:#888">{gut} / {total} &nbsp;·&nbsp; {pct}%</span>
          </div>
          <div style="background:#e8ddd0;border-radius:10px;height:14px;overflow:hidden">
            <div style="width:{pct}%;background:{farbe_kat};height:100%;border-radius:10px"></div>
          </div>
        </div>""", unsafe_allow_html=True)


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Italiano Trainer",
        page_icon="🇮🇹",
        layout="centered",
    )
    apply_style()
    init_state()

    st.markdown('<div class="main-title">🇮🇹 Italiano Trainer</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Spaced Repetition • SM-2 Algorithmus • Ollama Integration</div>',
                unsafe_allow_html=True)
    st.markdown("---")

    seite = st.sidebar.radio(
        "Navigation",
        ["📚 Lernen", "🏆 Fortschritt", "📊 Statistik", "📂 Importieren", "✏️ Editor"],
        label_visibility="collapsed",
    )

    # Vokabular-Info in Sidebar
    st.sidebar.markdown("---")
    n = len(st.session_state.vokabular)
    heute = str(date.today())
    faellig = sum(1 for k in st.session_state.vokabular
                  if k["meta"].get("naechste_wiederholung", heute) <= heute)
    st.sidebar.markdown(f"**{n}** Karten gesamt  \n**{faellig}** heute fällig")

    # Mini-Fortschritts-Widget in Sidebar
    t = lade_tracking()
    karten_w = karten_diese_woche(t)
    ziel_w   = t.get("wochenziel", 20)
    pct_w    = min(100, int(karten_w / ziel_w * 100))
    streak   = streak_berechnen(t)
    farbe_w  = "#27ae60" if pct_w >= 100 else "#e67e22" if pct_w >= 50 else "#c0392b"
    st.sidebar.markdown("---")
    if karten_w > 0 or streak > 0:
        streak_txt = f"🔥 {streak} Tage  |  " if streak > 0 else ""
        st.sidebar.markdown(f"**{streak_txt}Woche: {karten_w}/{ziel_w}**")
        st.sidebar.markdown(f"""
        <div style="background:#e0d5c8;border-radius:8px;height:8px;overflow:hidden">
          <div style="width:{pct_w}%;background:{farbe_w};height:100%;border-radius:8px"></div>
        </div>""", unsafe_allow_html=True)
    else:
        st.sidebar.markdown("_Noch keine Aktivität diese Woche_")

    # Lernmodus: nur fällige oder alle
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Lernmodus**")
    lernmodus = st.sidebar.radio(
        "Lernmodus",
        ["📅 Nur fällige Karten", "📖 Alle Karten (Review)"],
        key="lernmodus",
        label_visibility="collapsed",
    )
    st.session_state.lernmodus_alle = (lernmodus == "📖 Alle Karten (Review)")

    # Ollama Einstellungen
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Ollama**")
    ollama_modelle = ["gemma3:4b", "gemma3:12b", "gemma3:27b", "llama3.2:3b", "mistral-nemo:12b", "qwen2.5:7b"]
    aktuelles_model = st.sidebar.selectbox(
        "Modell",
        ollama_modelle,
        index=ollama_modelle.index(OLLAMA_MODEL) if OLLAMA_MODEL in ollama_modelle else 0,
        key="ollama_model_select",
    )
    st.session_state.ollama_model_aktiv = aktuelles_model
    ollama_timeout = st.sidebar.slider("Timeout (Sek.)", 15, 120, 60, 5, key="ollama_timeout")

    if seite == "📚 Lernen":
        seite_lernen()
    elif seite == "🏆 Fortschritt":
        seite_fortschritt()
    elif seite == "📊 Statistik":
        seite_statistik()
    elif seite == "📂 Importieren":
        seite_importieren()
    elif seite == "✏️ Editor":
        seite_editor()


if __name__ == "__main__":
    main()
