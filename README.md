# Browser History to Timesketch Converter

Converts browser history from Firefox, Chrome, Safari, and all Chromium-based browsers to Timesketch-compatible CSV format.

## Requirements

- Python 3.6+
- No external dependencies (standard library only)

## Usage

### Simple (Auto-detect browser type)
```bash
python browser2timesketch.py -i <database_path>
```

### With Options
```bash
python browser2timesketch.py [OPTIONS] -i <database_path>
```

## Command-Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `-i`, `--input` | Yes | Path to browser history database file |
| `-b`, `--browser` | No | Browser type: `firefox`, `chromium`, `safari`, or `auto` (default: auto) |
| `-o`, `--output` | No | Output CSV file path (default: auto-generated) |
| `--browser-name` | No | Custom browser name for data_type field (e.g., "Brave", "Edge") |

## Finding Browser Database Files

### Firefox (all platforms)

1. Open Firefox
2. Type `about:support` in address bar
3. Look for **Profile Folder** or **Profile Directory**
4. Click **Open Folder** button
5. Find `places.sqlite` in that folder

**Standard locations:**
- **Linux:** `~/.mozilla/firefox/<profile>/places.sqlite`
- **macOS:** `~/Library/Application Support/Firefox/Profiles/<profile>/places.sqlite`
- **Windows:** `%APPDATA%\Mozilla\Firefox\Profiles\<profile>\places.sqlite`

### Chrome, Edge, Brave, Opera, Vivaldi (all Chromium browsers)

1. Open your browser
2. Type `chrome://version/` in address bar
   - For Edge: `edge://version/`
   - For Brave: `brave://version/`
   - For Opera: `opera://about/`
   - For Vivaldi: `vivaldi://about/`
3. Look for **Profile Path**
4. Find `History` file (no extension) in that folder

**Standard locations:**

**Google Chrome:**
- **Linux:** `~/.config/google-chrome/Default/History`
- **macOS:** `~/Library/Application Support/Google/Chrome/Default/History`
- **Windows:** `%LOCALAPPDATA%\Google\Chrome\User Data\Default\History`

**Microsoft Edge:**
- **Linux:** `~/.config/microsoft-edge/Default/History`
- **macOS:** `~/Library/Application Support/Microsoft Edge/Default/History`
- **Windows:** `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History`

**Brave:**
- **Linux:** `~/.config/BraveSoftware/Brave-Browser/Default/History`
- **macOS:** `~/Library/Application Support/BraveSoftware/Brave-Browser/Default/History`
- **Windows:** `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\History`

**Opera:**
- **Linux:** `~/.config/opera/Default/History`
- **macOS:** `~/Library/Application Support/com.operasoftware.Opera/History`
- **Windows:** `%APPDATA%\Opera Software\Opera Stable\History`

**Vivaldi:**
- **Linux:** `~/.config/vivaldi/Default/History`
- **macOS:** `~/Library/Application Support/Vivaldi/Default/History`
- **Windows:** `%LOCALAPPDATA%\Vivaldi\User Data\Default\History`

### Safari (macOS only)

**Location:** `~/Library/Safari/History.db`

**To open in Finder:**
1. Press `Cmd + Shift + G`
2. Type `~/Library/Safari/`
3. Press Enter

## Examples

### Auto-detect (simplest)
```bash
python browser2timesketch.py -i ~/.mozilla/firefox/abc123.default/places.sqlite
python browser2timesketch.py -i ~/.config/google-chrome/Default/History
python browser2timesketch.py -i ~/Library/Safari/History.db
```

### Specify browser type
```bash
python browser2timesketch.py -b firefox -i places.sqlite -o firefox.csv
python browser2timesketch.py -b chromium -i History -o chrome.csv
python browser2timesketch.py -b safari -i History.db -o safari.csv
```

### With custom browser name
```bash
python browser2timesketch.py --browser-name "Brave" -i ~/.config/BraveSoftware/Brave-Browser/Default/History
```

## Notes

- Close your browser before running to avoid database locks (or the script will use read-only mode)
- Output contains complete browsing history - handle securely
- On Windows, use quotes around paths with spaces