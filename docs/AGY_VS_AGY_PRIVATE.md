# AGY (öffentlich) vs. agy-private 0.8.1

Dieses Dokument beschreibt, was Anwender bei **Einbindung und Nutzung** anders
machen müssen, wenn sie von der internen Entwicklungsversion
`dev/agy-private` (Stand **0.8.1**) auf das **öffentliche Paket** `agy`
(PyPI, **1.0.0**) wechseln.

## Rollen der beiden Repositories

| | **agy** (öffentlich) | **agy-private** (intern) |
|---|---|---|
| Zweck | PyPI-Paket, Templates, Tests, öffentliche Doku | Entwicklung, interne Notizen, Language Server, IDE-Extension |
| Version | `1.0.0` | `0.8.1` |
| Paket-Layout | `src/agy`, `src/flowsy` | `agy/`, `flowsy/` im Repo-Root |
| Distribution | PyPI (`pip install agy`) | Git-Checkout / lokaler Pfad |
| Lizenz | MIT | kein explizites PyPI-Metadatum |

**Wichtig:** Der Python-Import bleibt in beiden Fällen `import agy`. Flows,
Templates und Anwendungscode müssen in der Regel **nicht** umgeschrieben werden —
nur die **Installations- und Projekt-Konfiguration** ändert sich.

---

## 1. Installation

### agy-private 0.8.1 (bisher üblich)

```bash
# Global (CLI)
uv tool install "agy @ git+ssh://git@github.com/MaximilianVogel/agy.git"

# Im Projekt
uv add "agy @ git+ssh://git@github.com/MaximilianVogel/agy.git"

# Oder lokaler Checkout des Privat-Repos
uv add --editable ../agy-private
```

Zusätzliche Integrationen wurden in der Doku oft so beschrieben:

```bash
uv sync --extra atlassian          # Jira
uv sync --extra atlassian --extra email   # Jira + Email (in Doku erwähnt)
```

In `agy-private` 0.8.1 ist **`atlassian` tatsächlich ein Optional-Extra** in
`pyproject.toml`. Das Extra **`email` existiert dort nicht** — Email-Integration
steckt bereits in den Core-Dependencies. Die `--extra email`-Hinweise in älterer
Doku sind veraltet.

### Öffentliches agy (neu)

```bash
# Global (CLI)
uv tool install agy
# oder: pip install agy

# Im Projekt
uv add agy
# oder in pyproject.toml: dependencies = ["agy>=1.0.0"]
```

**Kein Git-SSH-Zugang nötig.** Email **und** Jira (`atlassian-python-api`) sind
im Core-Paket enthalten — ein einfaches `uv sync` reicht:

```bash
uv sync
```

---

## 2. Projekt-`pyproject.toml` nach `agy init`

### agy-private — generierte Templates

Die Templates in `agy-private` enthalten typischerweise:

```toml
[project]
dependencies = ["agy"]

[tool.uv.sources]
agy = { git = "ssh://git@github.com/MaximilianVogel/agy.git" }
```

### Öffentliches agy — generierte Templates

```toml
[project]
dependencies = ["agy>=1.0.0"]
```

**Kein** `[tool.uv.sources]`-Block — PyPI ist die Standardquelle.

### Migration in bestehenden Projekten

1. Git-Source-Eintrag entfernen:

   ```toml
   # entfernen:
   [tool.uv.sources]
   agy = { git = "ssh://git@github.com/MaximilianVogel/agy.git" }
   ```

2. Dependency anpassen:

   ```toml
   dependencies = ["agy>=1.0.0"]
   ```

3. Lockfile neu auflösen:

   ```bash
   uv lock --upgrade-package agy
   uv sync
   ```

`[tool.agy.llm]` und Provider-Blöcke in Template-`pyproject.toml` bleiben
unverändert.

---

## 3. CLI und IDE-Tooling

| Funktion | agy-private 0.8.1 | öffentliches agy |
|---|---|---|
| `agy init --template …` | ja | ja (gleiche Template-Namen) |
| `agy install-language-server` | ja | **nein** |
| `agy-language-server` (Binary) | ja (Extra `language_server`) | **nicht im Paket** |
| VS Code / Cursor Extension (`.vscode-extension/`) | im Privat-Repo | **nicht exportiert** |

Wer bisher `agy install-language-server` nutzte, braucht dafür weiterhin den
Checkout von `agy-private` oder eine manuelle Extension-Installation aus diesem
Repo. Für reine Flow-Ausführung ist das **nicht** erforderlich.

---

## 4. Nutzung im Anwendungscode — was gleich bleibt

Diese Teile sind zwischen 0.8.1 (private) und 1.0.0 (öffentlich) **identisch**
in der Anwender-Perspektive:

### Flow-Definition (`.flowsy`)

- `context_in`, `nodes`, `actions`, `edges`
- Contrib-Actions: `classify`, `respond`, `extract`, `end`, `run_flow`,
  `run_flow_batch`, `load_files_text`, `search_emails`, `search_files`, …
- Final-Edge-Shorthand (`- ziel_node` als letzte Kante)
- Stochastische Nodes mit `requests:` und Agent-Objekt aus `context_in`

### Python-API

```python
from agy import Flow, FlowExecutor, ActionType
from agy.integrations.email import Email, MockEmailAccount, GraphEmailAccount, ...
from agy.integrations.jira import JiraClient, JiraIssue
```

### Ausführungsmuster

```python
# Validierung (einmalig, gern mit Klassen statt Instanzen)
Flow.validate("mein_flow.flowsy", context_in={"email": Email}, action_types=[...])

# Ausführung
flow = Flow.from_flowsy("mein_flow.flowsy")
result = await flow.run(context_in={"email": email}, action_types=[...])
```

### Projektlayout nach `agy init`

Unverändert: `main.py`, `objects/`, `prompts/`, `data/`, `*_flow.flowsy`,
`.env.example`.

Custom-Funktionen weiterhin als `ActionType(object_name="global_function", ...)`
registrieren.

---

## 5. Was sich in der Praxis ändert (Checkliste)

### Einbindung

- [ ] Git-SSH-Dependency durch `agy` von PyPI ersetzen
- [ ] `uv sync --extra atlassian` entfällt — Jira ist im Core
- [ ] `uv sync --extra email` entfällt (war in 0.8.1 ohnehin kein echtes Extra)
- [ ] Globale Installation: `uv tool install agy` statt Git-URL

### Nutzung

- [ ] **Keine** Änderung an `.flowsy`-Dateien nötig (sofern keine privaten Module)
- [ ] **Keine** Änderung an `from agy import …` / `agy.integrations.*`
- [ ] `objects/`-Code im eigenen Projekt bleibt projektlokal (nicht Teil des Pakets)
- [ ] Stochastische Agenten implementieren `run(request, **kwargs)` (seit 0.8.x)

### IDE (optional)

- [ ] Language Server / Extension: nur noch über `agy-private` oder manuelle VSIX

---

## 6. Typische Migrations-Szenarien

### Szenario A: Template-Projekt aus `agy init`

```bash
cd mein_altes_projekt
# pyproject.toml: Git-Source raus, dependencies = ["agy>=1.0.0"]
uv lock --upgrade-package agy
uv sync
uv run python main.py
```

### Szenario B: Library in bestehender Codebase

```diff
 [project]
 dependencies = [
-    "agy @ git+ssh://git@github.com/MaximilianVogel/agy.git",
+    "agy>=1.0.0",
 ]
```

### Szenario C: Language Server weiter nutzen

Für Autocomplete und Go-to-Definition im Editor weiterhin `agy-private` verwenden
oder die Extension manuell installieren. Die Flow-Ausführung selbst läuft über
das PyPI-Paket.

---

## 7. Versionsstand und Kompatibilität

- **agy-private 0.8.1** und **öffentliches agy 1.0.0** sind funktional auf
  demselben Feature-Stand (RecordSet, stochastische Nodes, Sub-Flows, Email/Jira).
- Die öffentliche Version **1.0.0** ist vor allem der **PyPI-Release-Sprung** mit
  vereinfachter Dependency-Story (Integrationen im Core), nicht ein Breaking
  API-Redesign.
- Empfehlung für neue Projekte: `agy>=1.0.0`.

Bei Unsicherheit nach dem Wechsel einmal validieren:

```python
from agy import Flow

result = Flow.validate("mein_flow.flowsy", context_in={...}, action_types=[...])
assert result.is_valid, result.errors
```

---

## Kurzfassung

| Frage | agy-private 0.8.1 | öffentliches agy |
|---|---|---|
| Woher installieren? | Git / lokaler Pfad | PyPI |
| Jira extra? | `uv sync --extra atlassian` | in Core enthalten |
| Email extra? | Doku ja, pyproject nein | in Core enthalten |
| Import | `agy` | `agy` |
| Flows ändern? | — | in der Regel nein |
| Language Server? | `agy install-language-server` | nicht enthalten |

**Fazit:** Anwender tauschen primär die **Dependency-Quelle** und vereinfachen
`uv sync`. Flows, Integrations-Imports und das Projektlayout nach `agy init`
bleiben gleich.
