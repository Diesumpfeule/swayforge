# Anleitung: Python lernen mit swayforge (ohne Tutorials)

> **Du willst nur die Sprache lernen? Geh nach [basics/](basics/README.md).**
>
> **Zu kompliziert? Lies zuerst [START-HIER.md](START-HIER.md).** Das hier ist die ausführliche Fassung für später.

Für dich, später, in Ruhe. Du musst nichts auf einmal verstehen. Es geht darum, **kleine Dinge zu
ändern und zu sehen, was passiert**. Das ist Lernen, auch wenn es sich nicht so anfühlt.

---

## 0. Die Spielregeln (lies das zuerst)

1. **Nur Mini-Schritte.** Ein Schritt = eine Änderung = starten = ansehen. Nie 3 Dinge auf einmal.
2. **Kaputt ist normal.** Wenn etwas nicht läuft, hast du nichts falsch gemacht, du hast etwas
   herausgefunden. Mach die letzte Änderung rückgängig (`Strg+Z`) und das Programm läuft wieder.
3. **Fehlermeldungen von UNTEN lesen.** Die letzte Zeile sagt, *was* los ist (z. B. `NameError: name
   'x' is not defined` = "x kenne ich nicht"). Die Zeilen darüber sagen, *wo* (Dateiname + Zeilennummer).
4. **Speicherpunkte.** Wenn ein Schritt klappt: `git add -A && git commit -m "Schritt 1"`. Dann kannst
   du immer zurück (`git checkout -- datei.py` wirft deine letzten Änderungen weg).
5. **20 Minuten reichen.** Besser jedes Wochenende 20 Minuten als einmal 4 Stunden und dann frustriert.
6. **Nicht verstehen ist okay.** Du musst Code nicht komplett lesen können. Du suchst nur die EINE
   Stelle, die du ändern willst. Der Rest darf erst mal Magie bleiben.

---

## 1. Vorbereitung (einmalig, 10 Minuten)

```bash
cd ~/swayforge                      # oder wo dein Klon liegt: git pull holt den neuesten Stand
git pull
sudo dnf install python3-textual    # falls Textual fehlt (oder: pip install --user textual)
python3 extras/learn/themeswitcher.py
```

Du siehst eine Liste mit Themes. Mit `↑`/`↓` bewegen, `q` beendet. **Wenn das klappt, hast du schon
gewonnen.** Wenn nicht: Fehlermeldung kopieren und mir schicken.

Editor: nimm, was du kennst (`nano`, `micro`, Kate, Geany). Mit `nano extras/learn/themeswitcher.py`
geht es sofort.

---

## 2. Wie du die Datei "liest" (ohne alles zu verstehen)

Öffne `themeswitcher.py`. Sie hat nur 4 Teile:

| Teil | Was es ist | Aussehen |
|---|---|---|
| `import …` oben | Werkzeuge holen | Zeilen mit `import` / `from` |
| `class ThemeSwitcher(App)` | die App selbst | alles Eingerückte darunter |
| `compose` | **was auf dem Bildschirm steht** (Liste, Vorschau, Fusszeile) | `yield …` = "zeig das" |
| `on_list_view_highlighted` | **was passiert, wenn man in der Liste wandert** | Funktion mit `def` |

Merksätze:
- `def name(self, …):` = eine **Funktion**, ein benannter Block von Anweisungen.
- Die Einrückung (4 Leerzeichen) sagt, was zusammengehört. Python ist da streng.
- Funktionen, die mit `on_` beginnen, ruft Textual selbst auf, wenn etwas passiert (Ereignisse).
- `self.query_one("#preview", Static)` = "gib mir das Ding mit der ID `preview`".
- `.update("…")` = "ändere den Text darin".

---

## 3. Aufwärmen: Experimente (ohne etwas zu bauen)

Jedes Experiment: ändern, speichern, `python3 extras/learn/themeswitcher.py`, ansehen, ggf. zurück.

1. In `CSS` die Zahl bei `ListView { width: 32; }` ändern auf `50`. → Liste wird breiter.
2. `("q", "quit", "Quit")` zu `("q", "quit", "Beenden")`. → Fusszeile ändert sich.
3. In `on_list_view_highlighted` den Text im `update(...)` ändern, z. B. `f"Hallo {theme.label}!"`.
4. Zu `#preview { … }` im CSS `background: red;` hinzufügen. → Vorschau wird rot. Wieder entfernen.
5. `print(theme.colors)` ist nicht sichtbar in einer TUI. Setze stattdessen testweise
   `self.query_one("#preview", Static).update(str(theme.colors))`. → Du siehst, was ein Theme enthält.

Nach Experiment 5 weisst du: ein Theme hat `colors`, ein Wörterbuch (dict) wie
`{"base": "#1e1e2e", "accent": "#89b4fa", …}`. Das brauchst du gleich.

---

## 4. Theme-Switcher: die Schritte

### Schritt 1: Farben in der Vorschau zeigen
**Ziel:** Statt nur dem Namen siehst du bunte Kästchen.
**Idee:** Textual kann Text einfärben. `[on #ff0000]    [/]` malt 4 Zeichen mit rotem Hintergrund.
Die Farben holst du aus `theme.colors["accent"]` usw.
**Prüfen:** Wenn du durch die Liste gehst, ändern sich die Farben.

<details><summary>Lösung (erst probieren, dann ansehen)</summary>

```python
blocks = "\n".join(f"[on {theme.colors[k]}]        [/] {k}"
                   for k in ("base", "surface", "text", "accent", "red", "green"))
self.query_one("#preview", Static).update(f"{theme.label}\n\n{blocks}")
```
Die Zeile mit `for k in (…)` ist eine Schleife: für jeden Farbnamen eine Textzeile bauen.
`"\n".join(...)` klebt die Zeilen mit Zeilenumbruch zusammen.
</details>

### Schritt 2: Mit Enter anwenden
**Ziel:** `Enter` schaltet das Theme wirklich um.
**Idee:** Neue Funktion `on_list_view_selected(self, event: ListView.Selected)`. Sie bekommt wie
`…highlighted` die Zeile in `event.item`. Das Umschalten macht der Befehl, den du im Terminal kennst:
`swayforge theme NAME`. Aus Python startest du Befehle mit `subprocess.run([...])`.
**Wichtig:** oben `import subprocess` ergänzen. `capture_output=True` verhindert, dass der Befehl in
deine TUI hineinschreibt. Mit `self.notify("…")` zeigst du eine Meldung.
**Prüfen:** Enter auf einem Theme → Leiste und Farben wechseln.

<details><summary>Lösung</summary>

```python
def on_list_view_selected(self, event: ListView.Selected) -> None:
    theme_id = event.item.id.removeprefix("t-")
    r = subprocess.run(["swayforge", "theme", theme_id], capture_output=True, text=True)
    self.notify(f"Switched to {theme_id}" if r.returncode == 0 else r.stderr or "failed")
```
`returncode == 0` heisst "Befehl hat geklappt".
</details>

### Schritt 3: Tasten `j` und `k`
**Ziel:** Hoch/runter wie in vim.
**Idee:** In `BINDINGS` steht eine Liste `(Taste, Aktion, Beschriftung)`. Die Aktion `down` ruft die
Funktion `action_down` auf. Die schreibst du selbst und lässt die Liste sich bewegen:
`self.query_one(ListView).action_cursor_down()`. Für `k` genauso mit `…_up`.

<details><summary>Lösung</summary>

```python
BINDINGS = [("q", "quit", "Quit"), ("j", "down", "Down"), ("k", "up", "Up")]

def action_down(self) -> None:
    self.query_one(ListView).action_cursor_down()

def action_up(self) -> None:
    self.query_one(ListView).action_cursor_up()
```
</details>

### Schritt 4: Aktuelles Theme markieren
**Ziel:** Hinter dem aktiven Theme steht ein `*` oder `(aktiv)`.
**Idee:** Das aktive Theme steht in den Einstellungen:
`from swayforge import settings` und dann `settings.get(settings.load(), "theme.name")`.
Beim Bauen der Liste (`compose`) prüfst du für jedes Theme: `if t.id == aktuell`.
**Tipp:** Erst in einem kleinen Test im Terminal ausprobieren:
`python3 -c "from swayforge import settings; print(settings.get(settings.load(), 'theme.name'))"`.

### Schritt 5: Shortcut in Sway
**Ziel:** Eine Taste öffnet den Switcher in einem kleinen schwebenden Fenster.
In `~/.config/sway/custom.conf` (siehe `docs/CUSTOMIZING.md`):
```
bindsym $mod+Shift+t exec kitty --class themeswitcher python3 /PFAD/ZU/swayforge/extras/learn/themeswitcher.py
for_window [app_id="themeswitcher"] floating enable, resize set 700 450
```
Danach Sway neu laden (die Taste dafür zeigt dir `swayforge keys`).
Statt `kitty` nimm dein Terminal (`foot` braucht `--app-id`).

### Schritt 6: Extras, wenn du Lust hast
Suchfeld, Favoriten, `Esc` beendet, nach Enter das Fenster schliessen (`self.exit()`), Vorschau
aller Farben (`theme.colors` hat ~17 Einträge), Hell-/Dunkel-Anzeige (`theme.dark`).

---

## 5. Widget-Board: die Schritte

Datei `extras/learn/widgets.py`. Starten: `python3 extras/learn/widgets.py`.

### Verstehen (5 Minuten)
`class Clock(Static)` ist **ein Widget**. `on_mount` läuft einmal beim Start. `set_interval(1, self.tick)`
ruft `tick` jede Sekunde auf. `tick` setzt mit `self.update(…)` den Text. Das ist alles.

### Widget 1: Eigenes Datum (Aufwärmen)
Kopiere die ganze Klasse `Clock`, nenne sie `DateWidget`, ändere `border_title` und den Text so,
dass nur das Datum drin steht (`strftime("%d.%m.%Y")`). Ergänze in `Board.compose` unter `yield Clock()`
die Zeile `yield DateWidget()`.

### Widget 2: Zähler zum Klicken
Statt `Static` nimm `Button`. Eine Zahl `self.count = 0` merken, bei `on_button_pressed` hochzählen
und die Beschriftung `self.label = str(self.count)` ändern.

### Widget 3: Akku oder RAM
Daten holst du aus Dateien oder Befehlen:
- Akku: `Path("/sys/class/power_supply/BAT0/capacity").read_text()` (Name kann `BAT1` sein)
- RAM: `/proc/meminfo` (Zeilen `MemTotal`, `MemAvailable`)
Zuerst im Terminal ausprobieren (`cat /proc/meminfo`), dann in `tick` einlesen.

### Weitere Ideen
Uptime (`/proc/uptime`), Speicherplatz (`shutil.disk_usage("/")`), Todo-Liste in einer Datei,
"Spielt gerade" (`playerctl metadata title`), Netzwerk, Wetter-Text (`curl wttr.in`).

---

## 6. Wenn du feststeckst

Schick mir: **die Fehlermeldung (komplett kopiert)** und **welchen Schritt du machst**.
Ich erkläre dir, was sie bedeutet, und gebe dir einen Hinweis statt der Lösung, wenn du das willst.
Sag einfach "nur ein Hinweis" oder "zeig mir die Lösung".

## 7. Wann bist du "fertig"?
Wenn du deinen Theme-Switcher per Taste benutzt und dir 2–3 Widgets selbst gebaut hast, hast du
Funktionen, Schleifen, Dictionaries, Dateien, Befehle starten und Ereignisse benutzt. Das ist der
Kern von Python, und zwar an deinem eigenen Projekt.
