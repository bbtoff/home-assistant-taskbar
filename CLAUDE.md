# HA Taskbar : règles de travail

Ce dépôt contient **deux applications** qui partagent un numéro de version, une page de présentation et
une page de releases :
- **Windows** (Python, tkinter) : à la racine (`ha_taskbar.py`, `ha_core.py`, `*_ui.py`, `installer/`, `tests/`…).
- **macOS** (Swift, AppKit + SwiftUI) : dans `macos/` uniquement.

Deux agents peuvent y travailler en même temps, un par plateforme. Ces règles évitent qu'ils se gênent.

## Langue

- Parler **en français** et **tutoyer** l'utilisateur, comme dans l'interface.
- Les textes de l'interface sont en français. Windows : traduction anglaise dans `i18n_en.py`.

## Qui touche quoi

| Partie | Fichiers | Qui |
| --- | --- | --- |
| Windows | racine (`*.py`, `installer/`, `tests/`, `build.ps1`, `assets/`) | agent Windows |
| macOS | `macos/` | agent Mac |
| Partagé | `README.md`, `README.en.md`, `docs/`, `.github/workflows/release.yml`, `CLAUDE.md` | les deux, avec précaution |

- Ne pas modifier le code de l'autre plateforme. Si une fonction doit exister des deux côtés, la faire
  sur sa plateforme et le signaler à l'utilisateur pour l'autre agent (un plan comme `macos/PLAN-1.11.md`
  aide beaucoup).
- Les deux versions doivent garder le **même comportement** et les **mêmes clés** dans le fichier de
  réglages JSON (ex. `zone`, `camera`, `panel_title`…), pour que l'import / export reste compatible.

## Branches et fusion

- Toujours partir d'un `main` **à jour** (`git fetch origin main`) avant de commencer, et surtout
  avant de toucher un fichier partagé.
- Travailler sur sa branche, puis ouvrir une pull request vers `main`.
- **Fusionner dans `main` ne publie rien.** Une nouveauté terminée et testée peut être fusionnée tout
  de suite : elle partira avec la prochaine version commune.
- En cas de conflit sur un fichier partagé : garder les deux contributions, ne jamais écraser celle
  de l'autre plateforme.

## Version et publication

**Ne rien publier sans que l'utilisateur dise explicitement « publie ».** Pas de release, pas de tag,
pas de case « publish » cochée dans un workflow.

Windows et Mac sortent **avec le même numéro de version**. Pour préparer la version `vX.Y.Z` :

1. Mettre le même numéro aux deux endroits :
   - `ha_core.py` : `__version__ = "X.Y.Z"`
   - `macos/Sources/HATaskbar/Version.swift` : `let appVersion = "X.Y.Z"`
2. Écrire les notes :
   - `docs/notes/vX.Y.Z.md` : obligatoire, notes de la release (Windows, et Mac si besoin).
   - `macos/notes/vX.Y.Z.md` : facultatif, paragraphe Mac en français, puis une ligne `---en---`, puis
     la ligne anglaise (format de `macos/notes/v1.11.0.md`).
3. Fusionner dans `main`.
4. Seulement quand l'utilisateur dit « publie » : Actions → **Release** → tag `vX.Y.Z`, case
   **publish**. Le workflow vérifie que les deux numéros correspondent au tag, construit Windows et Mac,
   et ajoute les empreintes SHA-256 aux notes.

Si une seule plateforme doit être corrigée dans une release **déjà publiée** : le workflow **macOS**
(entrée `release_tag`) remplace uniquement les fichiers Mac et leurs empreintes. Le faire seulement à la
demande de l'utilisateur.

Les applications installées cherchent leurs mises à jour dans les releases de **ce dépôt** : ne pas le
renommer ni déplacer les fichiers vers un autre dépôt.

## Tests avant fusion

- **Windows** : workflow « Windows (tests) » (`tests/test_token.py`, compilation de tous les modules).
- **macOS** : workflow « macOS » (`./macos/build.sh`, `macos/Tests/ui-test.sh`, `macos/Tests/update-test.sh`).
  Captures : workflow « macOS (captures) » avec le mode démo (`--demo …`).
- Après chaque fonction : compiler, lancer l'application, faire une capture et la montrer à l'utilisateur.

## Présentation (README)

- `README.md` (français) et `README.en.md` (anglais) restent **identiques sur le fond** : modifier
  les deux.
- Captures et GIF dans `docs/screenshots/` (préfixe `mac-` pour macOS, `en/` pour les captures anglaises).
- Pas d'historique des versions sur la présentation : il est dans les releases.

## Sécurité

- Ne jamais committer de jeton Home Assistant ni de vrai fichier de réglages (seulement `config.example.json`).
- Windows chiffre le jeton avec DPAPI (`token_protected`). Le Mac le garde dans le trousseau.
