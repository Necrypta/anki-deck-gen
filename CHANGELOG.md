# Changelog

Each pull request adds a line under **Unreleased**. Releasing moves those lines under a new version heading, and that section becomes the GitHub Release notes.

## [Unreleased]

- Every pull request gets a downloadable test build, linked in a PR comment.
- Test builds show a "Test build" badge and their label (e.g. `PR #4 · a1b2c3d`) in the sidebar, window title and Settings.
- Test and dev builds save to `%APPDATA%\AnkiDeckGenerator-test`, separate from the installed release.
- Tagged versions publish a Windows installer (per-user, Start-menu shortcut, uninstaller, in-place upgrades) and a portable `.exe` on GitHub Releases.

## [0.1.0]

- First version: card editor (Basic, Reversed, Cloze, Custom), live KaTeX preview with physics macros, block and delimited text import, `.apkg` export, autosave, light/dark theme, CLI.
