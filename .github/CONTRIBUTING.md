# Contributing

Thanks for helping. Before you change anything, read [AGENTS.md](../AGENTS.md) – it applies to humans and AI agents alike.

- **Never edit `custom_components/jellyfin_plus/` by hand.** It is generated. Change `tools/baue_integration.py` and regenerate:
  `JFP_ZIEL=custom_components/jellyfin_plus python3 tools/baue_integration.py <HA-version>`
- Every change to the official integration is a named, asserted replacement in the generator. Put the reason next to it.
- Test on a real Home Assistant before opening a pull request: media browser root, a library, track choice, play, resume, search in a library.
- Nothing specific to one installation (host names, device lists) – make it an option instead.
