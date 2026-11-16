# Jellyfin Plus

A Home Assistant integration for controlling a Jellyfin player (TV, Android TV, …) from a dashboard or tablet. It is built on the official Jellyfin integration and adds what is missing for actually *watching* something.

*Deutsch weiter unten.* The labels the integration adds in the media browser (*Weiterschauen*, *Naechste Folge*, track choices) are German.

## What it adds

| | |
|---|---|
| **Continue watching** and **Next up** | appear first in the media browser |
| **Pick audio and subtitle track before playing** | an episode or movie opens a choice of track combinations and only then plays. The choice is applied a second time once playback runs, because some clients (Samsung/Tizen) ignore it in the play command. |
| **Resume instead of starting at 0:00** | play starts at the saved position |
| **Episode numbers and watched state** | number, check mark, percentage or `(4 offen)` |
| **Libraries sorted by date added** | instead of alphabetically |
| **Search per library** | the search field in a library only searches that library |
| **Seeking that sticks** | your own seek wins over the next poll instead of jumping back |
| **Light, cached thumbnails** | 360 px webp with the image tag instead of 600 px jpg: about 35 KB instead of several hundred per poster, cached by the browser for a year, no access token in image URLs |
| **Players only for real players** | sessions that can't be remote-controlled (Seerr, API tools, Home Assistant itself) don't become media players. Optionally only selected clients become players. |

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → `https://github.com/tsapZ/jellyfin-plus`, type *Integration*.
2. Install **Jellyfin Plus**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Jellyfin Plus*. Enter the server URL, your Jellyfin **user name and password** (no admin API key needed – the integration only acts as that user).
4. Optional: *Configure* → **Only these clients become players**, e.g. `Jellyfin for Tizen`. Otherwise every phone and browser where Jellyfin was open becomes a player.

Do not run it next to the official Jellyfin integration with the same user – every session would appear twice.

**Your TV app must be able to be remote-controlled.** It shows up as a media player only while it is open and reports remote control to the server. With Jellyfin 12, the Samsung/Tizen app 1.1.0 opens its websocket with the old `?api_key=` parameter and is rejected (403) – then it never becomes a player. A reverse proxy can rewrite `/socket?api_key=` to `?ApiKey=`.

## Versions

The integration is generated from the official one at a specific Home Assistant version (`version` in `manifest.json`). A weekly workflow regenerates it against the latest Home Assistant release and opens an issue if a modification no longer applies. Tested: Home Assistant 2026.9.3 and 2026.11.1, Jellyfin 12.4. Release `v2026.11.1` needs HA ≥ 2026.11; on older HA install `v2026.9.3`.

## For AI agents and contributors

Read [`AGENTS.md`](AGENTS.md) before changing anything. Short version: **never edit `custom_components/` by hand** – change `tools/baue_integration.py` and regenerate.

---

## Deutsch

Eine Home-Assistant-Integration, um einen Jellyfin-Player (Fernseher, Android TV …) vom Dashboard oder Tablet aus zu steuern – aufgebaut auf der offiziellen Jellyfin-Integration, ergänzt um Weiterschauen/Nächste Folge, Ton- und Untertitelwahl vor dem Abspielen, Fortsetzen statt bei 0:00, Folgennummern und Gesehen-Stand, Sortierung nach Neuzugang, Suche je Bibliothek und Springen, das hält.

**Einrichten:** HACS → Benutzerdefinierte Repositories → dieses Repo (Typ *Integration*) → installieren → HA neu starten → Integration *Jellyfin Plus* hinzufügen mit Server-Adresse, **Benutzername und Passwort** (kein Admin-Schlüssel nötig). Unter *Konfigurieren* lässt sich festlegen, welche Clients Spieler werden (z. B. `Jellyfin for Tizen`).

**Die TV-App muss sich fernsteuern lassen** und offen sein. Die Samsung-App 1.1.0 wird von Jellyfin 12 beim Websocket abgewiesen (alter Parameter `api_key`); ein Reverse-Proxy kann ihn auf `ApiKey` umschreiben.

## License

Apache License 2.0, derived from Home Assistant's Jellyfin integration – see [`NOTICE`](NOTICE).
