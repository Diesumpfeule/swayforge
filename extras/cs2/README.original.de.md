```
  ___ ___ ___    ___ _         _
 / __/ __|_  )  / __| |_  __ _| |_
| (__\__ \/ /  | (__| ' \/ _` |  _|
 \___|___/___|  \___|_||_\__,_|\__|
        Übersetzer  →  Deutsch
```

# CS2 Chat-Übersetzer für Linux

Übersetzt den Chat in Counter-Strike 2 live auf Deutsch und zeigt ihn als
durchsichtiges Overlay direkt über dem Spiel-Chat an.

- Startet automatisch, sobald CS2 läuft, und beendet sich mit dem Spiel
- Overlay ohne Rahmen, immer im Vordergrund, Mausklicks gehen durch
- Teamfarben: CT blau, T orange, Allchat grün
- Originaltext klein darunter (abschaltbar)
- Nachrichten blenden nach 15 Sekunden aus, das leere Overlay ist unsichtbar
- Zwei Übersetzungsdienste (Google, MyMemory), automatischer Wechsel bei Sperre
- Keine Zusatzpakete nötig außer Tkinter

---

## Ist das VAC-sicher?

Das Tool greift **nicht** ins Spiel ein. Es liest nur die Textdatei `console.log`,
die CS2 mit der offiziellen Startoption `-condebug` selbst schreibt. Es liest
keinen Spielspeicher, verändert keine Spieldateien, schleust keinen Code ein und
drückt keine Tasten. Das Overlay ist ein ganz normales eigenes Fenster.

Eine offizielle Garantie gibt Valve für kein Drittprogramm. Tools nach diesem
Prinzip werden aber seit Jahren offen benutzt.

**Datenschutz:** Chatnachrichten werden zum Übersetzen an Google bzw. MyMemory
geschickt. Sonst verlässt nichts deinen PC.

---

## Inhalt

| Datei | Zweck |
|---|---|
| `cs2_chat_uebersetzer.py` | Das eigentliche Programm |
| `installieren.sh` | Installiert alles und richtet den Autostart ein |
| `deinstallieren.sh` | Entfernt alles wieder |
| `README.md` | Diese Anleitung |

---

## Installation

**1. Tkinter installieren** (für das Overlay-Fenster):

```bash
sudo dnf install python3-tkinter        # Fedora
sudo apt install python3-tk             # Debian / Ubuntu / Mint
sudo pacman -S tk                       # Arch
```

**2. Steam-Startoption setzen:**
CS2 → Rechtsklick → *Eigenschaften* → *Allgemein* → *Startoptionen*:

```
-condebug
```

Nur das, kein Startskript davor.

**3. Installieren:** Im entpackten Ordner:

```bash
bash installieren.sh
```

**4. Grafikmodus:** In CS2 unter *Video* den Anzeigemodus auf
**„Vollbild im Fenster“** stellen. Über echtem Vollbild kann kein Overlay liegen.

**5. Position einstellen** (einmalig, während CS2 läuft):

```bash
python3 ~/.local/share/cs2-chat-uebersetzer/cs2_chat_uebersetzer.py --verschieben
```

Das Beispiel-Overlay mit der Maus über den CS2-Chat ziehen und mit `Esc`
schließen. Die Position wird gespeichert.

Fertig. Ab jetzt einfach CS2 über Steam starten. Beim Start erscheint kurz das Logo,
dann ist der Übersetzer bereit.

---

## Wie es funktioniert

```
Anmeldung am PC
  └─ Wächter startet (Autostart, verbraucht fast nichts)
       └─ wartet, bis ein Prozess „cs2“ läuft
            └─ startet den Übersetzer
                 └─ liest neue Zeilen aus console.log
                      └─ erkennt Chatzeilen  →  übersetzt  →  zeigt sie im Overlay
       └─ CS2 geschlossen  →  Übersetzer wird beendet
```

---

## Optionen

Manuell starten, z. B. zum Testen:

```bash
python3 ~/.local/share/cs2-chat-uebersetzer/cs2_chat_uebersetzer.py [Optionen]
```

| Option | Wirkung | Standard |
|---|---|---|
| `--verschieben` | Overlay mit der Maus positionieren | |
| `--x 20 --y 400` | Position direkt in Pixeln angeben | gespeichert |
| `--breite 600` | Breite des Overlays | 520 |
| `--schrift 14` | Schriftgröße | 12 |
| `--zeilen 8` | Max. gleichzeitig sichtbare Nachrichten | 6 |
| `--dauer 20` | Sekunden, bis eine Nachricht verschwindet | 15 |
| `--alpha 0.5` | Transparenz (0.2 = sehr durchsichtig, 1.0 = deckend) | 0.7 |
| `--ohne-original` | Grauen Originaltext ausblenden | |
| `--lang en` | Andere Zielsprache | de |
| `--verlauf 0` | Alte Nachrichten beim Start (0 = keine) | 5 |
| `--fenster` | Normales Fenster statt Overlay | |
| `--terminal` | Nur Terminal-Ausgabe, kein Fenster | |
| `--alles` | Prüfmodus: zeigt **jede** neue Logzeile | |
| `--log "PFAD"` | Pfad zur `console.log` (in Anführungszeichen!) | automatisch |

Damit Optionen auch beim automatischen Start gelten, trägst du sie im Wächter ein:
`~/.local/bin/cs2-uebersetzer-waechter`, Zeile mit `--verlauf 0`. Hänge sie dort an,
z. B. `--verlauf 0 --schrift 14 --ohne-original`.

---

## Selbst anpassen

Alles in `cs2_chat_uebersetzer.py`:

| Was | Wo |
|---|---|
| Logo | `LOGO = r"""` oben in der Datei (das `r` muss bleiben!) |
| Wie lange das Logo bleibt | `LOGO_SEKUNDEN = 4` |
| Hintergrundfarbe | `BG = "#0b0b0b"` in `run_overlay` |
| Teamfarben | `colors = {"CT": ..., "T": ...}` in `run_overlay` |
| Standard-Transparenz | `"--alpha"` … `default=0.7` in `main` |

Nach Änderungen erst prüfen, ob die Datei noch fehlerfrei ist:

```bash
python3 -m py_compile cs2_chat_uebersetzer.py
```

Keine Ausgabe heißt alles okay. Danach `bash installieren.sh` erneut ausführen.

Eigene ASCII-Logos erzeugen: `sudo dnf install figlet`, dann `figlet -f small "Text"`.
Im Overlay unbedingt eine Monospace-Schrift verwenden, sonst verschiebt sich das Logo.

> Hinweis: Die Transparenz gilt für das ganze Overlay inklusive Schrift.
> Tkinter kann unter Linux den Hintergrund nicht separat durchsichtig machen.

---

## Fehlersuche

Alle Meldungen landen in:

```bash
cat ~/.cache/cs2_chat_uebersetzer.log
```

| Problem | Lösung |
|---|---|
| Keine Zeile „CS2 erkannt“ im Log | Läuft der Wächter? `pgrep -af waechter`. Sonst `bash installieren.sh` erneut ausführen oder neu anmelden. |
| „Warte auf console.log“ | `-condebug` fehlt in den Startoptionen, oder CS2 liegt in einer anderen Steam-Bibliothek → mit `--log "PFAD"` angeben. Datei suchen: `find / -name console.log -path "*csgo*" 2>/dev/null` |
| Overlay erscheint nicht | Anzeigemodus auf „Vollbild im Fenster“ stellen. Ist `python3-tkinter` installiert? |
| Overlay liegt hinter dem Spiel | Manche Wayland-Desktops ignorieren „immer oben“. CS2 läuft meist über XWayland, dann klappt es. Sonst `--fenster` probieren. |
| „Übersetzung fehlgeschlagen“ | Dienst hat dich kurz gesperrt (passiert öfter mit VPN). Das Tool wechselt automatisch und versucht es nach 1 Minute erneut. |
| Nachrichten werden nicht erkannt | Mit `--alles --terminal` starten, im Spiel schreiben und schauen, wie die Zeile in der Log aussieht. |
| CS2 startet nicht mehr | In den Startoptionen darf **nur** `-condebug` stehen. |

---

## Deinstallieren

```bash
bash deinstallieren.sh
```

Danach in Steam `-condebug` aus den Startoptionen entfernen, wenn du es nicht mehr brauchst.
