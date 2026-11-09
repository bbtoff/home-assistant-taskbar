# Sécurité

## Versions suivies

Seule la **dernière version** publiée dans les [Releases](https://github.com/bbtoff/home-assistant-taskbar/releases) reçoit des corrections. La mise à jour automatique d'HA Taskbar la propose dès sa sortie.

## Signaler une faille

Merci de **ne pas ouvrir d'issue publique** pour une faille de sécurité.

Utilise plutôt le signalement privé de GitHub : onglet **Security** du dépôt, puis **Report a vulnerability**. Seul le mainteneur voit ton message.

Indique si possible :
- la version d'HA Taskbar et de Windows ;
- ce que la faille permet de faire ;
- comment la reproduire.

HA Taskbar est maintenu sur mon temps libre : je réponds dès que possible, en général sous quelques jours. Une fois la correction publiée, je peux te citer dans les notes de version si tu le souhaites.

## Ce qui est concerné

- Le programme HA Taskbar et son programme d'installation
- La mise à jour automatique (téléchargement et vérification)
- La conservation du jeton d'accès Home Assistant

Les failles de Home Assistant lui-même sont à signaler au [projet Home Assistant](https://www.home-assistant.io/security/).

Ce que fait HA Taskbar (connexions réseau, fichiers, registre) est décrit dans la section [Sécurité et confidentialité](README.md#-sécurité-et-confidentialité) du README.
