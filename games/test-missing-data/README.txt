Test fixture for tools/test/verify.mjs.
References in these files are broken on purpose (unknown league, territory,
club, missing logo, a view whose map does not exist) and teams.json is
intentionally missing. The map must still load and degrade gracefully.
