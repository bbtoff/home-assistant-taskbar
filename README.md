# HA Taskbar

Affiche des **capteurs** et des **boutons Home Assistant** directement sur la **barre des tâches de Windows 11**, dans une zone libre (à gauche ou à droite des icônes).

![HA Taskbar sur la barre des tâches](docs/screenshots/barre.png)

*Lumière allumée à 70 % (en jaune), prise éteinte, thermostat, consommation et scène, sur fond transparent à côté du widget météo de Windows. Les captures utilisent des données de démonstration.*

- Valeurs en temps réel : température, consommation, état d'une lumière…
- Boutons cliquables : allumer/éteindre une lumière ou une prise, lancer une scène ou un script…
- **Appui long** sur un élément : une carte de contrôle s'ouvre, comme dans Home Assistant (luminosité, couleur, consigne de chauffage, volume, historique 24 h…)
- Icônes intégrées à Windows 11, qui changent de couleur selon l'état (jaune = allumé)
- Fenêtre de réglages graphique avec aperçu en direct : rien à éditer à la main

Un **programme d'installation** est fourni : rien d'autre à installer, pas même Python. Depuis les sources, il suffit de Python et de sa bibliothèque standard (tkinter, ctypes, urllib).

---

## Sommaire

1. [Prérequis](#prérequis)
2. [Installation](#installation)
3. [Premier lancement](#premier-lancement)
4. [Utilisation au quotidien](#utilisation-au-quotidien)
5. [Les réglages en détail](#les-réglages-en-détail)
6. [Fichier de configuration](#fichier-de-configuration)
7. [Comment ça marche](#comment-ça-marche)
8. [Structure du projet](#structure-du-projet)
9. [Limites connues](#limites-connues)
10. [Dépannage](#dépannage)

---

## Prérequis

- **Windows 11** (fonctionne aussi sous Windows 10, avec les icônes Segoe MDL2)
- Uniquement pour lancer depuis les sources : **Python 3.8 ou plus récent** (testé avec 3.10), avec tkinter. C'est le cas par défaut avec l'installeur de python.org.
- Un **Home Assistant** joignable depuis le PC, et un **jeton d'accès longue durée**

### Créer le jeton d'accès Home Assistant

1. Dans Home Assistant, clique sur **ton profil** (en bas à gauche).
2. Ouvre l'onglet **Sécurité**.
3. Tout en bas, dans **Jetons d'accès longue durée**, clique sur **Créer un jeton**.
4. Donne-lui un nom (par exemple « HA Taskbar ») puis copie le jeton. Il ne sera plus affiché ensuite.

---

## Installation

### Avec le programme d'installation (recommandé)

1. Télécharge `HATaskbar-Setup-<version>.exe` depuis la page [**Releases**](https://github.com/bbtoff/home-assistant-taskbar/releases) du dépôt.
2. Lance-le. Aucun droit administrateur n'est demandé : le programme s'installe pour ton compte, dans `%LOCALAPPDATA%\Programs\HA Taskbar`.
3. Options proposées : **lancer au démarrage de Windows** (cochée) et **icône sur le Bureau**.

Une fois installé, HA Taskbar apparaît dans le menu Démarrer et se désinstalle depuis **Paramètres → Applications → Applications installées**. La désinstallation propose aussi d'effacer les réglages, jeton compris.

Pour une mise à jour, lance simplement le nouveau programme d'installation : il ferme HA Taskbar, remplace les fichiers et garde tes réglages.

> Le programme n'est pas signé numériquement : au premier lancement, Windows SmartScreen peut afficher « Windows a protégé votre PC ». Clique sur **Informations complémentaires**, puis **Exécuter quand même**.

### Depuis les sources

```powershell
git clone https://github.com/bbtoff/home-assistant-taskbar.git
cd home-assistant-taskbar
pythonw ha_taskbar.py
```

`pythonw` lance le programme sans fenêtre de console. Pour voir les éventuelles erreurs, utilise `python` à la place.

### Construire le programme d'installation

```powershell
winget install -e --id JRSoftware.InnoSetup --scope user   # une seule fois
powershell -ExecutionPolicy Bypass -File build.ps1
```

`build.ps1` installe PyInstaller dans un environnement virtuel dédié (`%LOCALAPPDATA%\HATaskbar-build`) et crée `HATaskbar.exe`. Il le passe ensuite à Inno Setup, qui produit `dist\HATaskbar-Setup-<version>.exe`. Le numéro de version vient de `__version__` dans [`ha_core.py`](ha_core.py).

---

## Premier lancement

Au premier lancement, la fenêtre de **Réglages** s'ouvre toute seule :

1. **Onglet Connexion** : saisis l'adresse de Home Assistant (ex. `http://homeassistant.local:8123`) et colle le jeton, puis clique sur **Tester la connexion**. Le nom et la version de ton Home Assistant s'affichent, ainsi que le nombre d'entités.

   ![Onglet Connexion](docs/screenshots/reglages-connexion.png)

2. **Onglet Éléments** : clique sur **➕ Ajouter des entités…**, cherche tes entités (par nom ou par type), puis double-clique pour les ajouter à la barre.

   ![Ajout d'entités](docs/screenshots/ajout-entites.png)

3. Clique sur **OK**. La barre apparaît sur la barre des tâches.

Pour lancer HA Taskbar à chaque démarrage, coche **Lancer HA Taskbar au démarrage de Windows** dans l'onglet Connexion.

---

## Utilisation au quotidien

| Action | Effet |
|---|---|
| **Clic** sur un bouton | Action selon le type : allume/éteint une lumière, une prise ou un ventilateur, lance une scène ou un script, appuie sur un bouton… |
| **Appui long** (½ seconde) | Ouvre la [carte de contrôle](#carte-de-contrôle-appui-long) de l'élément |
| **Clic** sur un capteur | Ouvre directement sa carte, puisqu'un capteur n'a pas d'action |
| **Molette** sur une lumière | Luminosité +/− 10 % |
| **Clic droit** n'importe où | Menu : Réglages…, Rafraîchir, Recharger la config, Quitter |
| **● HA** en rouge | Home Assistant ne répond pas. Clic droit pour voir l'erreur, clic gauche pour ouvrir les réglages. |

La barre se masque automatiquement quand une application passe en plein écran (jeu, vidéo).

### Carte de contrôle (appui long)

Un appui long sur un élément ouvre une carte juste au-dessus de la barre des tâches, dans l'esprit de la fenêtre de détail de Home Assistant. Son contenu dépend du type d'entité :

<p>
  <img src="docs/screenshots/carte-lumiere.png" alt="Carte d'une lumière" width="24%">
  <img src="docs/screenshots/carte-thermostat.png" alt="Carte d'un thermostat" width="24%">
  <img src="docs/screenshots/carte-media.png" alt="Carte d'un lecteur multimédia" width="24%">
  <img src="docs/screenshots/carte-capteur.png" alt="Carte d'un capteur" width="24%">
</p>

| Type d'entité | Contenu de la carte |
|---|---|
| Lumière | Interrupteur, luminosité, température du blanc et couleurs, selon ce que gère l'ampoule |
| Thermostat | Consigne avec − / + (ou molette), modes (arrêt, chauffage, auto…) et préréglages (éco, confort…) |
| Volet | Ouvrir / Stop / Fermer, position et inclinaison |
| Lecteur multimédia | Titre et artiste, précédent / lecture-pause / suivant, volume, source |
| Ventilateur | Interrupteur, vitesse, modes |
| Prise, interrupteur, automatisation | Interrupteur |
| Serrure | Verrouiller / Déverrouiller |
| Nombre, liste de choix | Curseur ou boutons de choix |
| Scène, script, bouton | Bouton d'activation |
| Capteur et autres | Valeur en grand |

Toutes les cartes, sauf celles des scènes, scripts et boutons, affichent l'**historique des dernières 24 h**. C'est une courbe pour une valeur numérique, ou une frise colorée pour un état allumé/éteint. Au survol, la valeur et l'heure s'affichent. Le lien **Ouvrir dans Home Assistant** ouvre l'historique complet dans le navigateur.

Les curseurs n'envoient la commande qu'au relâchement de la souris, pour ne pas inonder Home Assistant de requêtes. La consigne du thermostat est envoyée 0,7 s après le dernier clic sur − / +.

Le **titre** de la carte se change avec le crayon **✎** à côté (ou un double-clic dessus). **Entrée** enregistre et **Échap** annule. Un titre vide remet le nom de l'entité dans Home Assistant. Le titre est enregistré dans ta config (`card_title`) et se modifie aussi dans l'onglet Éléments des réglages. Il ne change rien dans Home Assistant.

La carte se ferme avec **Échap**, ou par un clic n'importe où en dehors.

#### Thèmes de la carte

Dans **Réglages → Apparence → Carte de contrôle**, choisis un thème et ses couleurs (comme la barre, toujours sombre ou toujours clair). Un aperçu se met à jour à chaque changement, et le bouton **Ouvrir la carte sur la barre** montre le vrai résultat.

<p>
  <img src="docs/screenshots/theme-ha-dark.png" alt="Thème Home Assistant, sombre" width="24%">
  <img src="docs/screenshots/theme-ocean-dark.png" alt="Thème Océan, sombre" width="24%">
  <img src="docs/screenshots/theme-crepuscule-light.png" alt="Thème Crépuscule, clair" width="24%">
  <img src="docs/screenshots/theme-windows-light.png" alt="Thème Windows 11, clair" width="24%">
</p>

| Thème | Particularité |
|---|---|
| Comme la barre (défaut) | Gris neutre, accent = couleur « Actif / allumé » de la barre |
| Windows 11 | Gris neutre, accent = couleur d'accentuation choisie dans Windows |
| Home Assistant | Couleurs de l'interface de Home Assistant, boutons très arrondis |
| Océan, Forêt, Crépuscule | Ambiances colorées |
| Contraste élevé | Noir/blanc et jaune ou bleu vif, angles droits |

Chaque thème existe en version **sombre** et **claire**.

**Créer ses propres thèmes** : le bouton **Thèmes personnalisés…** crée et ouvre `card_themes.json`, placé dans le même dossier que `config.json`. Il contient un exemple à copier :

```json
{
  "mon_theme": {
    "name": "Mon thème",
    "radius": 8,
    "dark":  { "bg": "#0f1e2b", "surface": "#17304a", "surface_h": "#1f3d5c", "border": "#24486b",
               "fg": "#e6f1ff", "dim": "#8aa4bf", "knob": "#17304a", "accent": "#2ec4b6" },
    "light": { "bg": "#f2f8fc", "surface": "#dcebf5", "surface_h": "#cde1ef", "border": "#c2d8e8",
               "fg": "#0f2a3f", "dim": "#4f6b82", "knob": "#ffffff", "accent": "#0f8b8d" }
  }
}
```

| Clé | Rôle |
|---|---|
| `bg` | Fond de la carte |
| `surface` / `surface_h` | Fond des boutons, au repos et au survol |
| `border` | Contour de la carte |
| `fg` / `dim` | Texte principal / texte secondaire |
| `knob` | Bouton rond des curseurs |
| `accent` | Couleur active (curseurs, interrupteur, choix sélectionné). `"bar"` reprend la couleur de la barre, `"system"` celle de Windows. |
| `radius` | Arrondi des boutons, en pixels (0 à 16) |

Une clé absente reprend la valeur du thème par défaut. Après avoir enregistré le fichier, clique sur **↻** pour recharger la liste.

---

## Les réglages en détail

### Onglet Connexion
- **Adresse** et **jeton** de Home Assistant
- **Vérifier le certificat HTTPS** : à décocher pour un certificat auto-signé
- **Rafraîchissement** : intervalle de lecture des états, en secondes (5 par défaut). Après un clic, la mise à jour est immédiate.
- **Lancer au démarrage de Windows** : ajoute ou retire l'entrée `HATaskbar` dans `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

### Onglet Éléments

![Onglet Éléments](docs/screenshots/reglages-elements.png)

- **Ajouter des entités…** : parcourt toutes les entités, avec une recherche multi-mots et un filtre par type. Les entités déjà présentes sont grisées (✔).
- **▲ ▼** pour l'ordre, **Dupliquer**, **Supprimer**
- Pour chaque élément :
  - **Libellé** et **Icône** : automatique selon le type, au choix parmi 45, ou aucune
  - **Valeur affichée** : l'état de l'entité ou un de ses attributs (ex. `current_temperature` d'un thermostat)
  - **Unité** et **Décimales**
  - **Action au clic** : automatique, aucune, ou n'importe quel service (ex. `light.turn_on`)
  - **Données (JSON)** : paramètres envoyés au service (ex. `{"entity_id": "light.salon", "brightness_pct": 30}`)
  - **Titre de la carte** : titre affiché sur la carte d'appui long. Vide = nom de l'entité dans Home Assistant.

Le bouton **Changer…** à côté de l'icône ouvre le choix parmi 45 icônes Windows 11 :

![Choix d'une icône](docs/screenshots/choix-icone.png)

Actions automatiques au clic :

| Type d'entité | Action |
|---|---|
| `light`, `switch`, `input_boolean`, `fan`, `cover`, `automation` | `toggle` |
| `script`, `scene` | `turn_on` |
| `button`, `input_button` | `press` |
| `media_player` | `media_play_pause` |
| `sensor`, `binary_sensor`, … | aucune (affichage seul) |

Pour les scènes, boutons et scripts, la barre affiche « Activer », « Appuyer » ou « Lancer » à la place de l'état. Home Assistant y met en effet la date du dernier déclenchement, ce qui n'a pas d'intérêt ici.

### Onglet Apparence

![Onglet Apparence](docs/screenshots/reglages-apparence.png)

- **Position** : côté gauche ou droit de la barre des tâches, et **décalage** en pixels depuis le bord. Le curseur déplace la barre en direct.
- **Disposition** : libellé au-dessus de la valeur, ou les deux sur une ligne :

  ![Disposition sur une ligne](docs/screenshots/barre-une-ligne.png)
- **Thème de la barre** : **Suivre Windows** (par défaut), **Toujours sombre** ou **Toujours clair**. La barre a deux jeux de couleurs, un pour le mode sombre et un pour le mode clair. Elle bascule toute seule, en 2 secondes environ, quand tu changes le mode de Windows dans *Paramètres → Personnalisation → Couleurs*. Le choix « Couleurs à modifier » indique quel jeu tu édites.
- **Fond transparent** (activé par défaut) : on voit le fond de la barre des tâches de Windows derrière les boutons. Comme les icônes de Windows restent visibles à travers, garde la barre dans une zone libre. Le survol affiche un rectangle de la couleur « Survol ».
- **Police**, **taille**, **opacité**, **afficher les icônes**, **masquer en plein écran**
- **Couleurs** : fond, valeurs, libellés, actif/allumé, survol, erreur, pour chacun des deux modes. Le bouton **Couleurs par défaut** remet celles d'origine.
- **Carte de contrôle** : thème et couleurs de la carte d'appui long (voir [Thèmes de la carte](#thèmes-de-la-carte)).

Tous les changements sont **prévisualisés en direct** sur la barre. **Appliquer**/**OK** enregistre, **Annuler** revient à l'état précédent.

---

## Fichier de configuration

Les réglages sont stockés dans `config.json`, créé automatiquement :
- version installée : `%APPDATA%\HATaskbar\config.json`
- depuis les sources : à côté du script. Ce fichier **n'est pas versionné**, car il contient ton jeton (voir `.gitignore`).

Un exemple est fourni dans [`config.example.json`](config.example.json).

Format d'un élément :

```json
{
  "entity_id": "climate.thermostat",
  "label": "Chauffage",
  "card_title": "Chauffage du salon",
  "icon": "flame",
  "attribute": "current_temperature",
  "unit": "°C",
  "decimals": 1,
  "service": "climate.set_preset_mode",
  "data": { "entity_id": "climate.thermostat", "preset_mode": "eco" }
}
```

Seul `entity_id` est obligatoire. `icon` peut valoir `"auto"` (par défaut), `"none"` ou une clé de `ICONS` dans [`ha_core.py`](ha_core.py). `service` peut valoir `"none"` pour désactiver le clic.

---

## Comment ça marche

Windows 11 ne permet plus d'ajouter des « deskbands » (barres d'outils) à la barre des tâches. HA Taskbar contourne cela :

1. Une **petite fenêtre sans bordure**, « toujours au premier plan », est posée **par-dessus** la barre des tâches. Elle reprend exactement sa hauteur et sa position, grâce à l'API Win32 `FindWindow("Shell_TrayWnd")`.
2. La barre des tâches repasse devant à chaque clic. La fenêtre se remet donc au premier plan **dès qu'une fenêtre devient active** (hook `EVENT_SYSTEM_FOREGROUND`), et en plus toutes les 0,4 s.
3. La fenêtre est de type « outil » et « non activable » : elle n'apparaît ni dans Alt+Tab ni dans la barre des tâches, et ne vole pas le focus.
4. Un **thread** interroge l'API REST de Home Assistant (`GET /api/states`, une seule requête pour toutes les entités) à intervalle régulier. Les clics appellent `POST /api/services/<domaine>/<service>`. La carte de contrôle lit l'historique avec `GET /api/history/period/…`.
5. Pour éviter tout scintillement, un élément n'est redessiné que si sa valeur change, et sa largeur ne rétrécit jamais.
6. **Fond transparent** : la couleur de fond est déclarée « transparente » (`-transparentcolor`). Windows laisse alors passer les clics à travers les pixels transparents. Une seconde fenêtre presque invisible (opacité 1 %), placée juste sous la barre, récupère ces clics et les transmet au bouton situé sous la souris. Tout le rectangle d'un bouton reste ainsi cliquable.

---

## Structure du projet

| Fichier | Rôle |
|---|---|
| [`ha_taskbar.py`](ha_taskbar.py) | Point d'entrée : la barre (fenêtre, positionnement, boutons, rafraîchissement) |
| [`card_ui.py`](card_ui.py) | Carte de contrôle (appui long) : curseurs, interrupteur, modes, historique 24 h |
| [`settings_ui.py`](settings_ui.py) | Fenêtre de réglages, sélecteur d'entités, sélecteur d'icônes |
| [`ha_core.py`](ha_core.py) | Commun : config, client Home Assistant, icônes, actions par défaut, démarrage auto |
| `config.example.json` | Exemple de configuration |
| `config.json` | Ta configuration (créée automatiquement, ignorée par git) |
| [`build.ps1`](build.ps1) | Construit l'exe (PyInstaller) puis le programme d'installation (Inno Setup) |
| [`installer/ha_taskbar.iss`](installer/ha_taskbar.iss) | Script Inno Setup : raccourcis, démarrage auto, désinstallation |
| [`assets/`](assets/) | Icône du programme |
| [`tools/make_icon.py`](tools/make_icon.py) | Génère l'icône (`python tools/make_icon.py`) |

---

## Limites connues

- Seule la barre des tâches de l'**écran principal** est gérée.
- Avec la barre des tâches en **masquage automatique**, la fenêtre ne suit pas l'animation.
- En fond transparent, le contour du texte est lissé sur la couleur « Fond ». Garde une couleur proche de ta barre des tâches (`#202020` en thème sombre, ou le thème clair pour une barre claire), sinon un léger liseré peut apparaître.
- Une mise à jour de Windows peut modifier le comportement de la barre des tâches.
- Rafraîchissement par interrogation périodique (pas de WebSocket), ce qui suffit pour un affichage à quelques secondes près.

---

## Dépannage

| Symptôme | Solution |
|---|---|
| **● HA** rouge, « HTTP 401 » | Jeton invalide ou révoqué : recrée-le dans Home Assistant |
| « Connexion impossible » | Vérifie l'adresse (http/https, port 8123) et que le PC joint Home Assistant |
| Erreur de certificat | Décoche **Vérifier le certificat HTTPS** |
| La barre recouvre des icônes | Ajuste le **décalage** dans l'onglet Apparence |
| « HA Taskbar est déjà lancé » | Une instance tourne déjà : clic droit sur la barre → Réglages |
| Rien ne s'affiche | Lance avec `python ha_taskbar.py` (et non `pythonw`) pour voir les erreurs dans la console |

---

## À propos de ce projet

Je ne suis pas développeur 😄 J'ai apporté les idées, les tests et les retours au fil de l'eau. Toute la partie technique (code, programme d'installation, documentation et captures) a été réalisée par **Claude**, l'assistant IA d'Anthropic, à partir de mes demandes.
