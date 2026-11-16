# Security

Please report security problems privately via GitHub's *Report a vulnerability* (Security tab) instead of a public issue.

The integration logs in to Jellyfin with a user name and password and only ever acts as that user. It stores the resulting access token in Home Assistant's config entry, like the official Jellyfin integration does.
