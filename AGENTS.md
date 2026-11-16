# AGENTS.md – read this before changing anything

For Claude Code, Codex and any other agent working on this repository (and for humans).

## The one rule

**`custom_components/jellyfin_plus/` is generated output. Never edit it by hand.**

Every change goes into `tools/baue_integration.py`, then regenerate:

```bash
JFP_ZIEL=custom_components/jellyfin_plus python3 tools/baue_integration.py <HA-version>   # e.g. 2026.9.3
rm -rf custom_components/jellyfin_plus/__pycache__
```

A hand edit is lost the next time anyone regenerates – which happens on every Home Assistant update.

## How the generator works

1. Downloads the official integration (`homeassistant/components/jellyfin/*`) from `home-assistant/core` at exactly the given version.
2. Applies a list of **named text replacements**. Each one is `assert ALT in t` followed by `t.replace(ALT, NEU, 1)`. If Home Assistant changed the code around a replacement, the matching assert fails **with a name** – that is the signal, not a bug in your environment.
3. Writes manifest (`version` = the HA version the template came from), translations (de/en), icons, then compiles every file.

The comments inside the generator are German and explain *why* each change exists, including measurements on real devices. Keep that style: the reason belongs next to the change.

## What is changed compared to the official integration

| Change | Where (generated file) |
|---|---|
| Domain `jellyfin_plus`, own app name, own manifest | `const.py`, `manifest.json` |
| Episodes carry their number, Continue/Next-up show season+episode | `browse_media.py`, `_beschriftung` |
| Watched state in the title | `browse_media.py`, `_beschriftung` |
| Episode/movie expands to a choice of audio/subtitle tracks before playing; id format `jfp|<ItemId>|<Audio>|<Subtitle>` | `browse_media.py`, `build_track_response`, `zerlege_wahl` |
| Continue watching / Next up in the root | `browse_media.py`, `build_root_response` |
| Libraries sorted by date added | `browse_media.py`, `get_media_info` |
| Every folder reports `can_search`, search uses the folder as `parentId` | `browse_media.py`, `build_item_response`, `search_items` |
| `play_media` passes the tracks and sets them again once playback runs (Tizen ignores them in the play command) | `media_player.py` |
| Resume at the saved position | `media_player.py`, `play_media` |
| Own seek wins over the next poll for 15 s | `media_player.py`, `media_seek`, `_sprung_halten` |
| Only remote-controllable sessions become players; option `clients` narrows to named clients | `coordinator.py`, `config_flow.py` |

## Updating to a new Home Assistant version

1. Run the generator with the new version.
2. If an assert fails: diff the official integration between the old and new version (`homeassistant/components/jellyfin/` on GitHub), adapt **ALT** (and if needed **NEU**) of that replacement. Check whether Home Assistant now does natively what the replacement did – then drop the replacement instead of fighting it (example: HA 2026.11 added `can_search` and folder-scoped search on its own).
3. Regenerate, then test on a real Home Assistant: media browser root, a library, an episode with track choice, play, resume, search inside a library, seek.
4. Release: tag = HA version the template came from (`v2026.9.3`), `gh release create`. HACS shows updates from releases.

The weekly workflow `.github/workflows/vorlage-pruefen.yml` does step 1 against the latest HA release and opens an issue when it fails.

## Known open point

- **HA 2026.11** changed `browse_media.py` (`item_payload`, search), switched `config_flow.py` from `voluptuous` to `probatio` and added reconfigure. Three replacements need adapting. Until then the release is generated from 2026.9.3.

## Where this comes from

Maintained alongside a private Home Assistant setup. Changes made there are mirrored here: whoever changes the generator in one place updates the other. Do not add anything specific to one installation (host names, device lists) to the generator – make it an option instead (see `clients`).
