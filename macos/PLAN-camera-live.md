# Caméra en direct : à faire aussi sur Mac

Fait sur Windows (`camera_live.py`, branche `windows/camera-live`). Même comportement attendu sur Mac.

## Ce que fait Windows

- **Fenêtre caméra quand on sonne** et **caméra dans la carte** : lecture du flux
  `GET /api/camera_proxy_stream/<camera>` (en-tête `Authorization: Bearer <jeton>`), au lieu d'une photo
  `camera_proxy` redemandée à intervalle régulier.
- La réponse est en `multipart/x-mixed-replace` : une suite de JPEG. Découpage avec `Content-Length` quand
  la partie en donne un, sinon du début `FF D8` à la fin `FF D9` de chaque JPEG.
- Au plus 10 images par seconde affichées : les images en trop sont sautées.
- Si le flux ne marche pas (erreur HTTP, réponse sans `multipart`, rien en 10 s), ou pour une entité `image.*` :
  retour aux photos comme avant (1 s pour la sonnette, 2 s dans la carte), et nouvel essai du flux après 60 s.
- Flux coupé après avoir marché : reconnexion tout de suite.
- **Panneau : inchangé** (une photo toutes les 3 s), car il peut montrer plusieurs caméras à la fois.

## Mesuré sur le Home Assistant de l'utilisateur

- Reolink, Frigate et Synology : Home Assistant envoie une image toutes les 0,5 s (2 images/s), contre 1 image/s
  (sonnette) et 1 image toutes les 2 s (carte) avant.
- `?interval=` plus petit que 0,5 est refusé par Home Assistant (400 Bad Request) : ne pas l'envoyer.
- Une caméra qui fournit elle-même du MJPEG peut aller plus vite.
- Pas de son.

## Sur Mac

`URLSession` avec un délégué `dataTask(…didReceive data:)` pour lire le flux au fil de l'eau, même découpage,
`NSImage(data:)` pour chaque JPEG, mise à jour de l'image sur le fil principal.
