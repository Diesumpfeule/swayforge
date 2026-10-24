# START HIER – Python lernen, ganz einfach

Die lange ANLEITUNG.md ist erst für später. **Mach nur das hier.** Du brauchst nichts zu verstehen,
nur Schritt für Schritt abtippen und schauen, was passiert.

Du brauchst zwei Terminal-Fenster (kitty): **Fenster A** zum Schreiben, **Fenster B** zum Starten.
Neues Fenster in Sway: `Super+Enter` (bei dir evtl. anders, sonst einfach das Terminal nochmal starten).

---

## Teil 1: Das Programm zum Laufen bringen (5 Minuten)

**Fenster B** – diese 3 Zeilen nacheinander einfügen (jede mit Enter):

```
cd ~/swayforge
git pull
sudo dnf install python3-textual
```

- `cd ~/swayforge` = "geh in den Ordner swayforge". (Liegt er woanders, schreib dort den richtigen Pfad.)
- `git pull` = "hol die neueste Version".
- Die dritte Zeile installiert das Werkzeug, das die Terminal-App zeichnet. Passwort eingeben, `j` oder `y` bestätigen.

Dann starten:

```
python3 extras/learn/themeswitcher.py
```

**Das solltest du sehen:** links eine Liste mit Theme-Namen, rechts ein Feld. Mit Pfeil hoch/runter wechselt der Text rechts.
Beenden mit `q`. **Wenn du das siehst, hast du den schwersten Teil geschafft.**

Klappt es nicht? Kopier die **letzte Zeile** der Fehlermeldung und schick sie mir. Das reicht.

---

## Teil 2: Deine erste Änderung (5 Minuten)

**Fenster A** – Datei zum Bearbeiten öffnen:

```
cd ~/swayforge
nano extras/learn/themeswitcher.py
```

Du siehst jetzt den Text der Datei. Mit den Pfeiltasten wandern. So bedienst du nano:
- Speichern: `Strg+O`, dann `Enter`
- Beenden: `Strg+X`
- Rückgängig: `Alt+U`

**Ändere genau EINE Sache.** Geh mit den Pfeiltasten zu Zeile 28. Dort steht:

```
    BINDINGS = [("q", "quit", "Quit")]
```

Ersetze das Wort `Quit` ganz am Ende durch `Beenden` (nur das Wort in den Anführungszeichen):

```
    BINDINGS = [("q", "quit", "Beenden")]
```

Speichern (`Strg+O`, Enter). Nano kannst du offen lassen.

**Fenster B** – nochmal starten:

```
python3 extras/learn/themeswitcher.py
```

**Das solltest du sehen:** unten in der Leiste steht jetzt `Beenden` statt `Quit`.
Du hast gerade Python-Code geändert und das Ergebnis gesehen. Das ist das ganze Prinzip.

---

## Teil 3: Noch drei kleine Änderungen

Immer gleich: ändern → speichern (Fenster A) → neu starten (Fenster B) → schauen.

1. **Liste breiter machen.** Zeile 25: `ListView { width: 32; }` → ersetze `32` durch `50`.
2. **Vorschau-Text ändern.** Zeile 43: `f"{theme.label}\n\n({theme_id})"` → schreib vor `{theme.label}` das Wort `Hallo ` .
   Dann steht rechts z. B. `Hallo Catppuccin Mocha`.
3. **Hintergrund rot machen.** Zeile 26, in der Klammer nach `padding: 1 2;` ergänzen: ` background: red;`
   Dann ist das Feld rechts rot. Danach wieder löschen.

Ging etwas kaputt? Im nano `Alt+U` drücken, bis es wieder läuft. Oder alles zurücksetzen (Fenster B):

```
git checkout -- extras/learn/themeswitcher.py
```

---

## Fehlermeldung? So liest du sie

Schau nur auf die **letzte Zeile**. Beispiele:
- `SyntaxError` = irgendwo fehlt ein Zeichen (Anführungszeichen, Klammer). Schau die Zeile an, die darüber steht.
- `NameError: name 'x' is not defined` = du hast ein Wort falsch geschrieben.
- `IndentationError` = die Einrückung (Leerzeichen am Zeilenanfang) stimmt nicht.

Schick mir die letzte Zeile und sag, **was du zuletzt geändert hast**. Dann sage ich dir die Stelle.

---

## Danach

Wenn Teil 1 bis 3 geklappt haben, bist du bereit für den ersten echten Schritt: **Farben in der Vorschau zeigen**.
Sag mir einfach "weiter", dann erkläre ich ihn dir hier im Chat in kleinen Häppchen. Die lange ANLEITUNG.md
brauchst du dafür nicht.
