---
name: version
description: Bump project version and record what changed. Updates VERSION file and appends to CHANGELOG.md in knowledge/versions/.
allowed-tools: Read, Write, Bash
argument-hint: -patch | -minor | -major
---

# Version Management

## Usage

- `version -patch` - Bump patch version (0.1.0 → 0.1.1) for bug fixes
- `version -minor` - Bump minor version (0.1.0 → 0.2.0) for new features
- `version -major` - Bump major version (0.1.0 → 1.0.0) for breaking changes
- `version` (no args) - Show current version

## Instructions

### Show Current Version (No Args)

```bash
cat VERSION 2>/dev/null || echo "No VERSION file found"
```

Display:
```
Current version: 0.1.0

Usage:
  version -patch  → 0.1.1 (bug fixes)
  version -minor  → 0.2.0 (new features)
  version -major  → 1.0.0 (breaking changes)
```

### Bump Version

1. **Read current version:**
   ```bash
   cat VERSION
   ```
   If no VERSION file, start at 0.1.0

2. **Parse and increment:**
   - `-patch`: X.Y.Z → X.Y.(Z+1)
   - `-minor`: X.Y.Z → X.(Y+1).0
   - `-major`: X.Y.Z → (X+1).0.0

3. **Ask what changed:**
   ```
   Bumping 0.1.0 → 0.2.0

   What changed? (I'll add this to the changelog)
   ```

4. **Wait for user response** describing changes

5. **Update VERSION file:**
   ```bash
   echo "0.2.0" > VERSION
   ```

6. **Ensure CHANGELOG.md exists:**
   ```bash
   mkdir -p .claude/knowledge/versions
   ```

   If new file, create header:
   ```markdown
   # Changelog

   All notable changes to this project.

   Format based on [Keep a Changelog](https://keepachangelog.com/).

   ```

7. **Prepend new version entry** (newest at top, after header):
   ```markdown
   ## [0.2.0] - YYYY-MM-DD

   ### Added
   - [New feature 1]
   - [New feature 2]

   ### Changed
   - [Change 1]

   ### Fixed
   - [Bug fix 1]

   ```

8. **Confirm:**
   ```
   Version bumped: 0.1.0 → 0.2.0

   Updated:
   - VERSION
   - .claude/knowledge/versions/CHANGELOG.md

   Changes recorded:
   - Added: Intelligent folder inference for model downloads
   - Changed: ModelDownloader UI improvements
   ```

## Changelog Categories

Use appropriate sections based on what changed:

- **Added** - New features
- **Changed** - Changes to existing functionality
- **Deprecated** - Features that will be removed
- **Removed** - Features that were removed
- **Fixed** - Bug fixes
- **Security** - Security fixes

## Example

```
User: version -minor

Claude: Bumping 0.1.0 → 0.2.0

What changed?

User: Added intelligent folder inference for model downloads.
      Updated ModelDownloader to highlight files needing selection.

Claude: Version bumped: 0.1.0 → 0.2.0

Updated:
- VERSION
- .claude/knowledge/versions/CHANGELOG.md

Changes recorded:
### Added
- Intelligent folder inference for model downloads

### Changed
- ModelDownloader highlights files needing folder selection
```

## CHANGELOG.md Format Example

```markdown
# Changelog

All notable changes to this project.

## [0.2.0] - 2024-01-16

### Added
- Intelligent folder inference for model downloads
- Local file path support in File Sync tab

### Changed
- ModelDownloader highlights files needing folder selection

## [0.1.0] - 2024-01-10

### Added
- Initial model download functionality
- Basic file sync tab
```
