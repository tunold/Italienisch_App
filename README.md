# 🇮🇹 Italiano Trainer

Ein persönlicher Vokabel- und Grammatiktrainer für Italienisch, gebaut mit Streamlit und dem SM-2 Spaced-Repetition-Algorithmus.

## Features

- **SM-2 Spaced Repetition** – bewährter Algorithmus (wie Anki): Karten die du gut kennst kommen seltener, schwierige öfter
- **Strukturierte Konjugationstabellen** – alle Verben mit Presente, Passato Prossimo, Imperfetto, Futuro direkt aus JSON
- **Konjugations-Quiz** – zufällige Person + Zeitform zum aktiven Üben
- **Ollama Integration** *(lokal)* – KI-Erklärungen mit lokalem LLM (gemma3, mistral, qwen2.5 etc.)
- **Cache** – Ollama-Antworten werden in der JSON gespeichert und sind offline abrufbar
- **Import/Export** – Vokabular-Pakete als JSON laden, Fortschritt exportieren
- **Wochenziel & Streak** – Motivation durch Fortschrittsanzeige und Aktivitäts-Heatmap
- **Fortschritt pro Kategorie** – Balkendiagramm wie viel % beherrscht
- **Kartengenerator** *(lokal mit Ollama)* – freie Grammatikfragen → fertige Lernkarte

## Vokabular-Pakete

| Datei | Inhalt |
|---|---|
| `vokabular_basis.json` | Bauwesen, HVAC, Alltag, Essen (Starterpaket) |
| `vokabular_verben.json` | 25 wichtige Verben mit strukturierter Konjugation |
| `vokabular_verben2.json` | 25 weitere Verben (verb_026–050) |
| `vokabular_verbindungswoerter.json` | Konnektoren: tuttavia, quindi, oppure... |
| `vokabular_adj_adv.json` | Adjektive & Adverbien inkl. bene/buono/bello |
| `vokabular_alltag2.json` | Erweitertes Alltagsvokabular |
| `vokabular_einkaufen.json` | Einkaufen, Restaurant, Markt |
| `vokabular_nuetzliche_saetze.json` | Nützliche Redewendungen und Sätze |
| `vokabular_grammatik_*.json` | Grammatikkarten (Präpositionen, Artikel, Zeitformen...) |
| `vokabular_position_dimostrativi.json` | alto/basso, sopra/sotto, qui/lì, questo/quello |

## Setup (lokal)

```bash
# Repository klonen
git clone https://github.com/DEIN-USERNAME/italiano-trainer
cd italiano-trainer

# Abhängigkeiten installieren
pip install -r requirements.txt

# Startvokabular laden (nur beim ersten Mal)
cp vokabular_basis.json vokabular.json

# App starten
streamlit run app.py
```

## Ollama (optional, nur lokal)

Die App funktioniert vollständig ohne Ollama – nur KI-Erklärungen sind dann deaktiviert.

```bash
# Ollama installieren: https://ollama.com
ollama pull gemma3:12b
ollama serve
```

Empfohlene Modelle für M4 MacBook Air:

| Modell | RAM | Qualität |
|---|---|---|
| `gemma3:4b` | ~3 GB | gut, sehr schnell |
| `gemma3:12b` | ~8 GB | beste Qualität |
| `qwen2.5:7b` | ~5 GB | gut für Mehrsprachigkeit |

## Deployment auf Streamlit Cloud

1. Repository auf GitHub hochladen (inkl. `vokabular.json`)
2. Auf [share.streamlit.io](https://share.streamlit.io) einloggen
3. Repository verbinden → `app.py` als Hauptdatei
4. Deploy

> **Hinweis:** Ollama läuft nur lokal. Auf Streamlit Cloud sind KI-Funktionen deaktiviert (🔴 in der Sidebar). Alle anderen Funktionen (SM-2, Konjugationstabellen, Quiz, Import/Export, Fortschritt) laufen vollständig.

> **Hinweis:** Streamlit Cloud hat kein persistentes Dateisystem – `vokabular.json` und `tracking.json` werden bei jedem Neustart zurückgesetzt. Für persistenten Fortschritt empfiehlt sich lokales Deployment oder regelmäßiger Export über **📂 Importieren → ⬇️ Vokabular herunterladen**.

## Vokabular erweitern

JSON-Dateien über **📂 Importieren** laden. Zwei Modi:
- **➕ Nur neue Karten** – Lernfortschritt bleibt erhalten
- **🔄 Ersetzen** – Inhalt aktualisieren, Fortschritt bleibt

Format:
```json
[
  {
    "id": "eindeutige_id",
    "de": "das Wort",
    "it": "la parola",
    "kategorie": "Bauwesen",
    "beispiel_it": "Esempio.",
    "beispiel_de": "Beispiel.",
    "erklaerung": "Optionale Erklärung (erscheint auf der Antwortkarte)."
  }
]
```

## SM-2 Bewertungsskala

| | Bedeutung | Wirkung |
|---|---|---|
| 😵 0 | Vergessen | Reset → morgen wieder |
| 😕 2 | Schwer | Reset → morgen wieder |
| 🙂 4 | Gut | Intervall wächst |
| 😎 5 | Sofort | Intervall wächst stärker |

Beispiel-Intervall bei Note 4: `1 → 6 → 15 → 38 → 96 Tage`

## Stack

- [Streamlit](https://streamlit.io) · [Pandas](https://pandas.pydata.org) · [Ollama](https://ollama.com) *(optional)* · SM-2 Algorithmus · JSON
