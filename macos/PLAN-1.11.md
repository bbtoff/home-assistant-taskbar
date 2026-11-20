# Passation : version Mac 1.11.0 (parité avec Windows)

Ce fichier est destiné à la session Claude Code qui tourne sur le Mac. La version Windows 1.11.0 est
terminée et testée. Le travail consiste à porter ses nouveautés dans l'app Swift (`macos/`).

**Consignes de l'utilisateur**
- Ne rien publier : pas de release ni de tag sans sa demande explicite (« publie »).
- Parler en français et le tutoyer, comme dans l'interface.
- Après chaque fonction : `swift build`, lancer l'app, faire une capture et lui montrer.
- Le code Windows de référence est en Python à la racine du dépôt. Chaque section ci-dessous indique
  les fichiers à lire.

## Format de configuration (identique à Windows)

Ces clés existent déjà dans le `config.json` de Windows. Les ajouter à `Config.swift` avec
`CodingKeys` en snake_case, comme les autres.

| Clé | Où | Valeur |
|---|---|---|
| `zone` | élément | `"panel"` : l'élément est dans le panneau, pas dans la barre des menus. Absent, `"left"` ou `"right"` : il reste dans la barre. |
| `camera` | élément | `camera.*` ou `image.*` : aperçu dans la carte de l'élément. |
| `camera` | règle de notification | Ouvre la fenêtre caméra quand la règle se déclenche. |
| `panel_title` | global | Titre du panneau. Vide = « Maison ». |
| `panel_by_area` | global | `true` par défaut : éléments regroupés par pièce. |
| `panel_opacity` | global | De 0,5 à 1. |
| `panel_width`, `panel_height` | global | En points. Absents = taille par défaut (largeur 360). |

## 1. Panneau, en priorité

C'est la fonction la plus utile sur Mac : avec l'encoche, la barre des menus a peu de place.

Référence Windows : [panel_ui.py](../panel_ui.py).

- Une icône « Maison » dans la barre des menus. Un clic ouvre un `NSPanel` ou un popover juste en
  dessous.
- **En-tête** :
  - le titre ;
  - un point vert « En direct » et le nombre d'éléments allumés ;
  - un bouton d'opacité, qui affiche un curseur de 50 à 100 % appliqué en direct et enregistré dans
    `panel_opacity` ;
  - un bouton Réglages.
- **Recherche** : un champ qui filtre les éléments par nom ou `entity_id` (mots sans accents).
- **Liste** :
  - une carte arrondie par pièce, avec le nom de la pièce en titre ; les éléments sans pièce vont
    dans « Autres », en dernier ;
  - chaque ligne : pastille ronde (icône, colorée si allumé), nom, sous-titre (phrase d'état de la
    carte, ou « Modifié il y a … » pour un capteur), valeur à droite ;
  - un interrupteur pour les domaines « toggle » ;
  - des boutons +/− pour un climatiseur ou un chauffe-eau ;
  - un curseur sous la ligne pour la luminosité, la vitesse d'un ventilateur, la position d'un volet
    ou le volume ;
  - l'image d'une caméra rafraîchie toutes les 3 s.
- **Gestes** :
  - clic = action de l'élément ; appui long = carte ;
  - clic droit = Ouvrir la carte / Modifier / Mettre dans la barre / Taille par défaut.
- **Taille** :
  - les bords haut, gauche et droit se tirent pour agrandir le panneau, et la taille est enregistrée ;
  - double-clic sur un bord = taille par défaut ;
  - plusieurs colonnes quand c'est assez large (colonne de 320 pt minimum), en équilibrant la
    hauteur ; une seule pièce se coupe en colonnes.
- **Réordonner** :
  - glisser un élément dans sa pièce ;
  - glisser le titre d'une pièce pour déplacer toutes ses lignes ;
  - le nouvel ordre est enregistré dans `items`.
- **Pied** : « Réglages » et « Ouvrir dans Home Assistant ↗ ».
- **Fermeture** : Échap, ou un clic en dehors.
- **Réglages** : la liste des éléments en 3 parties (barre gauche, barre droite, panneau) avec
  glisser-déposer, comme dans [settings_ui.py](../settings_ui.py) (`refresh_tree`, `ZONES`). Sur Mac,
  2 parties suffisent : barre des menus et panneau.

## 2. Minuteurs `timer.*`

Référence : `timer_remaining`, `fmt_hms` et `_hms` dans [ha_core.py](../ha_core.py), `_b_timer` dans
[card_ui.py](../card_ui.py).

- Attributs utilisés : `finishes_at` (ISO), `remaining` et `duration` (« H:MM:SS »). L'état vaut
  `active`, `paused` ou `idle`.
- **Barre des menus** : compte à rebours rafraîchi chaque seconde, avec « ⏸ » en pause.
- **Clic** : `timer.start`, ou `timer.pause` s'il est en cours.
- **Carte** :
  - grand compte à rebours et barre de progression ;
  - boutons Démarrer / Pause / Reprendre, Annuler, Terminer ;
  - « Démarrer pour » 1, 5, 10, 15, 30 ou 60 min, qui appelle `timer.start` avec
    `duration: "HH:MM:00"`.

## 3. Photos et pochettes

Référence : `picture_of` et `HomeAssistant.picture` dans [ha_core.py](../ha_core.py),
[pictures.py](../pictures.py).

- Source : attribut `entity_picture_local` ou `entity_picture`.
  - Un chemin relatif se lit sur l'adresse de HA avec le jeton.
  - Une adresse externe se lit sans le jeton.
  - Lecture limitée à 8 Mo, avec un cache.
- Rien pour une caméra, une image, une entité indisponible ou un lecteur à l'arrêt.
- **Carte** :
  - personne ou traceur : photo ronde de 44 pt à la place de l'icône ;
  - autres entités : coins arrondis ;
  - lecteur : grande pochette au-dessus du titre.
- **Panneau** : la photo remplace la pastille. Le sous-titre d'un lecteur est « Titre · Artiste ».

## 4. Aperçu caméra dans la carte

- `GET /api/camera_proxy/<id>` (ou `/api/image_proxy/<id>` pour `image.*`), avec le jeton.
- L'aperçu est rafraîchi chaque seconde tant que la carte est ouverte.
- La caméra vient de l'élément lui-même (domaine `camera` ou `image`), sinon de sa clé `camera`.

## 5. Fenêtre caméra quand on sonne

Référence : [doorbell_ui.py](../doorbell_ui.py).

- Une règle de notification qui a `camera` ouvre une fenêtre flottante en haut à droite, sous la
  barre des menus. Elle ne prend pas le focus (`NSPanel` `nonactivatingPanel`).
- Contenu :
  - une cloche, le texte de la notification et ✕ ;
  - l'image rafraîchie chaque seconde ; un clic sur l'image ouvre la carte de la caméra ;
  - le nom de la caméra, « Garder ouverte » et « se ferme dans N s ».
- Elle se ferme seule après 60 s.
- Une seule fenêtre à la fois : une nouvelle sonnerie de la même caméra remet le texte et le délai à
  zéro.
- Elle respecte la pause des notifications et la plage horaire sans notification. Le bouton
  « Tester » de la règle l'ouvre quand même.
- Pour une entité `event.*`, `button.*` ou `input_button.*`, le message par défaut est `{name}`, pas
  « {name} : {state} », pour ne pas afficher une date brute.
- Réglages → règle : un champ « Afficher la caméra », avec « (aucune) » et les `camera.*` / `image.*`.

## 6. Assist

Référence : `converse` dans [ha_core.py](../ha_core.py), `ask` dans [palette.py](../palette.py).

- `POST /api/conversation/process` avec `{"text": …, "conversation_id": …}`.
- La réponse est dans `response.speech.plain.speech`. Une erreur se reconnaît à
  `response.response_type == "error"`. Garder le `conversation_id` renvoyé pour continuer la
  conversation.
- Sur Mac, il n'y a pas de palette. Mettre Assist dans le champ de recherche du panneau :
  - une phrase de 2 mots ou plus ajoute la ligne « Demander à Assist : « … » » ;
  - Entrée sur cette ligne, ou ⌘↩, envoie la question ;
  - la réponse s'affiche sous le champ.

## 7. Autocomplétion de l'entité dans les Réglages

Référence : [autocomplete.py](../autocomplete.py).

- Dès qu'on tape, une liste de 8 suggestions : nom, pièce et `entity_id`. Tous les mots tapés doivent
  se trouver quelque part dans ces trois textes, en ignorant les accents.
- Ordre de tri :
  1. l'`entity_id` commence par le texte ;
  2. le nom commence par le texte ;
  3. un mot commence par le texte ;
  4. le reste.
- Une entité qui n'existe plus affiche « Entité inconnue. Tu voulais dire « camera.xxx » ? ». Un clic
  la remplace.
  - Recherche : même domaine, ressemblance de 0,6 au moins (comme `difflib`).
  - Sinon, un seul résultat qui partage un mot d'au moins 3 lettres.

## Ordre conseillé

1. Panneau (sections 1 et 6)
2. Minuteurs
3. Photos
4. Caméra dans la carte
5. Fenêtre caméra
6. Autocomplétion

Ensuite, mettre `Version.swift` à 1.11.0. Ne rien publier.
