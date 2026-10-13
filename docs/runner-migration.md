# Selbst gehostete Tools-Runner

Die CI verwendet nach dem Organisationsumzug den isolierten Tools-Pool auf
`githubrunner-hetzner`. Die Organisationsgruppe ist auf die 15 umgezogenen
Tool-Repositories beschränkt. zSYNC behält seine sechs bestehenden Runner;
damit sind alle 16 umgezogenen Repositories versorgt.

Linux-x64-Runner im neuen Pool tragen das eindeutige Label `zebroo-tools`.
Gimera und zodoo verwenden für externe Fork-PRs weiterhin GitHub-hosted Runner.
Ihre internen Jobs bekommen je Job ein eigenes Home-, pipx- und Temp-Verzeichnis.
Bake/Prebuild verlangen auf self-hosted zusätzlich einen separaten Docker-Dienst
(`DOCKER_HOST` und nach Prüfung `ZEBROO_DOCKER_ISOLATED=1`). Es wird kein
Docker-Socket des Hosts in diese Umgebung durchgereicht.

Aktivierung erst nach zweiter Prüfung des Runner-Rollouts in Ticket 5697 und
erfolgreichen Smokejobs. YAML, Runner-Auswahl, Job-Isolation und bestehende Hooks
werden lokal geprüft; Laufzeittests auf dem neuen Pool fehlen bis zur Einrichtung.
Keinen Release oder Versionsverteilungsjob zur bloßen Verifikation auslösen.
Rückweg: die neuen Dienste stoppen, Gruppenfreigabe zurücknehmen und diese
Workflowänderung über einen Revert-PR zurücknehmen. Bestehende zSYNC-Runner
bleiben erhalten.
