# Browser History to Timesketch Converter

Converts browser history from the three major browser engines to Timesketch-compatible CSV format.

## Supported Browser Engines

- **Gecko** - Firefox and derivatives (Waterfox, LibreWolf, etc.)
- **Chromium** - All Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi, Arc, etc.)
- **WebKit** - Safari

## Why Only Three Types?

All Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi, etc.) use **identical database schemas**. There's no need to handle them differently - they all use the same History database format with the same table structures and timestamp formats. The only difference is the file location, which you provide as input.

Similarly, all Gecko-based browsers (Firefox forks) use the same places.sqlite format.

## Usage

```bash
python browser2timesketch.py -b <browser_engine> -i <database_path> -o <output.csv>
```

### Arguments

- `-b, --browser`: Browser engine type
  - `firefox` or `gecko` - For Firefox and Firefox-based browsers
  - `chromium` - For all Chromium-based browsers
  - `safari` or `webkit` - For Safari
- `-i, --input`: Path to browser history database file
- `-o, --output`: Output CSV file path (optional, default: browser_history_timesketch.csv)
- `--browser-name`: Custom browser name for the data_type field (optional)

## Database File Locations

### How to Find Your Profile Path

#### Gecko / Firefox
1. Open Firefox
2. Type `about:support` in the address bar and press Enter
3. Look for **Profile Folder** or **Profile Directory**
4. Click "Open Folder" / "Open Directory" button, or note the path shown
5. The `places.sqlite` file is in this directory

Alternative: Type `about:profiles` to see all profiles and their locations.

#### Chromium (Chrome/Edge/Brave/Opera/Vivaldi/etc.)
1. Open your Chromium-based browser
2. Type `chrome://version/` in the address bar and press Enter
3. Look for **Profile Path** - this shows the full path to your profile directory
4. The `History` file (no extension) is in this directory

Note: For browsers based on Chromium, use the same URL even if it's not Chrome:
- Edge: `edge://version/`
- Brave: `brave://version/`
- Opera: `opera://about/`
- Vivaldi: `vivaldi://about/`

#### WebKit / Safari
Safari's history database is always at the same location on macOS:
`~/Library/Safari/History.db`

To view in Finder:
1. Open Finder
2. Press `Cmd + Shift + G` (Go to Folder)
3. Type `~/Library/Safari/`
4. Press Enter

### Standard Profile Locations

If you prefer to navigate directly to the standard locations:

### Gecko / Firefox

**Database file:** `places.sqlite`

- **Linux:** `~/.mozilla/firefox/<profile>/places.sqlite`
- **macOS:** `~/Library/Application Support/Firefox/Profiles/<profile>/places.sqlite`
- **Windows:** `%APPDATA%\Mozilla\Firefox\Profiles\<profile>\places.sqlite`

### Chromium (Chrome/Edge/Brave/Opera/Vivaldi/etc.)

**Database file:** `History` (no file extension)

All Chromium browsers use the same database format. Only the location differs:

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

### WebKit / Safari

**Database file:** `History.db`

- **macOS:** `~/Library/Safari/History.db`

## Examples

### Firefox (or any Gecko-based browser)
```bash
# Linux
python browser2timesketch.py -b firefox -i ~/.mozilla/firefox/xyz123.default/places.sqlite -o firefox_history.csv

# macOS
python browser2timesketch.py -b gecko -i "~/Library/Application Support/Firefox/Profiles/xyz123.default/places.sqlite" -o firefox_history.csv

# Windows
python browser2timesketch.py -b firefox -i "C:\Users\YourUser\AppData\Roaming\Mozilla\Firefox\Profiles\xyz123.default\places.sqlite" -o firefox_history.csv
```

### Chrome (or any Chromium-based browser)
```bash
# Linux - Chrome
python browser2timesketch.py -b chromium -i ~/.config/google-chrome/Default/History -o chrome_history.csv

# macOS - Chrome
python browser2timesketch.py -b chromium -i "~/Library/Application Support/Google/Chrome/Default/History" -o chrome_history.csv

# Windows - Chrome
python browser2timesketch.py -b chromium -i "C:\Users\YourUser\AppData\Local\Google\Chrome\User Data\Default\History" -o chrome_history.csv

# Linux - Brave with custom label
python browser2timesketch.py -b chromium --browser-name "Brave" -i ~/.config/BraveSoftware/Brave-Browser/Default/History -o brave_history.csv

# Windows - Edge
python browser2timesketch.py -b chromium -i "C:\Users\YourUser\AppData\Local\Microsoft\Edge\User Data\Default\History" -o edge_history.csv
```

### Safari
```bash
# macOS
python browser2timesketch.py -b safari -i ~/Library/Safari/History.db -o safari_history.csv

# Or using the webkit alias
python browser2timesketch.py -b webkit -i ~/Library/Safari/History.db -o safari_history.csv
```

## Output Format

The script generates a CSV file with Timesketch-compatible fields:

| Field | Description | All Browsers |
|-------|-------------|--------------|
| `timestamp` | Unix timestamp in microseconds | ✓ |
| `datetime` | ISO 8601 formatted datetime | ✓ |
| `timestamp_desc` | Description of timestamp | ✓ |
| `message` | Human-readable event description | ✓ |
| `url` | The visited URL | ✓ |
| `title` | Page title | ✓ |
| `data_type` | Source identifier | ✓ |
| `visit_type` | Type of visit | Gecko, Chromium |
| `visit_duration_us` | Visit duration in microseconds | Chromium only |
| `total_visits` | Total visits to this URL | Chromium only |
| `typed_count` | Times URL was typed | Chromium only |

## Browser Engine Details

### Timestamp Formats

Each browser engine uses a different timestamp format:

- **Gecko (Firefox):** Microseconds since Unix epoch (1970-01-01 00:00:00 UTC)
- **Chromium:** Microseconds since Windows epoch (1601-01-01 00:00:00 UTC)
- **WebKit (Safari):** Seconds since Cocoa epoch (2001-01-01 00:00:00 UTC)

The script automatically converts all timestamps to Unix microseconds for Timesketch.

### Database Schemas

- **Gecko:** Uses `moz_historyvisits` and `moz_places` tables in `places.sqlite`
- **Chromium:** Uses `visits` and `urls` tables in `History` database
- **WebKit:** Uses `history_visits` and `history_items` tables in `History.db`

## Important Notes

1. **Close the browser** before running the script to avoid database lock errors
2. **Copy the database file** to a temporary location if you want to avoid potential issues
3. **Handle output carefully** - the CSV contains your complete browsing history
4. Different browsers may have multiple profiles - make sure you're pointing to the correct profile directory
5. On Windows, use quotes around paths that contain spaces

## Troubleshooting

### Database is locked
- Close the browser completely
- Copy the database file to a temporary location and run the script on the copy

### File not found
- Verify the profile directory name (the random string like `xyz123.default`)
- Check that the browser has been used and has history
- On macOS, use tab completion or check the exact path

### Permission denied
- Run with appropriate permissions
- On Linux/macOS, check file permissions with `ls -l`
- On Windows, run as Administrator if needed

## Requirements

- Python 3.6 or higher
- No external dependencies (uses only standard library)

## Privacy and Security

This tool exports your complete browsing history. The output file contains:
- All visited URLs
- Page titles
- Visit timestamps
- Visit types and patterns

Handle the output files appropriately and delete them when no longer needed.