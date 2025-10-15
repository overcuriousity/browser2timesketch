#!/usr/bin/env python3
"""
Browser History to Timesketch CSV Converter

Converts browser history from major browser engines to Timesketch-compatible CSV format.
Supports: Gecko (Firefox), Chromium (Chrome/Edge/Brave/etc.), WebKit (Safari)
"""

import sqlite3
import csv
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List


class BrowserDetectionError(Exception):
    """Raised when browser type cannot be detected"""
    pass


class DatabaseValidationError(Exception):
    """Raised when database validation fails"""
    pass


class TimestampValidationError(Exception):
    """Raised when timestamp validation fails"""
    pass


def validate_sqlite_database(db_path: str) -> None:
    """
    Validate that the file is a SQLite database and is accessible.
    
    Args:
        db_path: Path to database file
        
    Raises:
        DatabaseValidationError: If validation fails
    """
    path = Path(db_path)
    
    if not path.exists():
        raise DatabaseValidationError(f"Database file not found: {db_path}")
    
    if not path.is_file():
        raise DatabaseValidationError(f"Path is not a file: {db_path}")
    
    # Try to open as SQLite database
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()
        # Check if it's a valid SQLite database by querying sqlite_master
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        conn.close()
    except sqlite3.DatabaseError as e:
        raise DatabaseValidationError(f"Not a valid SQLite database: {db_path}. Error: {e}")
    except sqlite3.OperationalError as e:
        raise DatabaseValidationError(f"Cannot access database (may be locked or corrupted): {db_path}. Error: {e}")


def detect_browser_type(db_path: str) -> str:
    """
    Auto-detect browser type by examining database schema.
    
    Args:
        db_path: Path to database file
        
    Returns:
        Detected browser type: 'gecko', 'chromium', or 'webkit'
        
    Raises:
        BrowserDetectionError: If browser type cannot be determined
    """
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()
        
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        conn.close()
        
        # Check for Gecko/Firefox tables
        if 'moz_historyvisits' in tables and 'moz_places' in tables:
            return 'gecko'
        
        # Check for Chromium tables
        if 'visits' in tables and 'urls' in tables:
            return 'chromium'
        
        # Check for WebKit/Safari tables
        if 'history_visits' in tables and 'history_items' in tables:
            return 'webkit'
        
        raise BrowserDetectionError(
            f"Cannot determine browser type. Found tables: {', '.join(sorted(tables))}\n"
            f"Expected one of:\n"
            f"  - Gecko/Firefox: moz_historyvisits, moz_places\n"
            f"  - Chromium: visits, urls\n"
            f"  - WebKit/Safari: history_visits, history_items"
        )
        
    except sqlite3.Error as e:
        raise BrowserDetectionError(f"Error reading database schema: {e}")


def validate_timestamp(unix_microseconds: int, browser_type: str) -> None:
    """
    Validate that a timestamp is within reasonable bounds.
    
    Args:
        unix_microseconds: Timestamp in Unix microseconds
        browser_type: Browser type for error messages
        
    Raises:
        TimestampValidationError: If timestamp is unreasonable
    """
    if unix_microseconds <= 0:
        return  # Allow 0 for missing timestamps
    
    # Convert to seconds for validation
    timestamp_seconds = unix_microseconds / 1000000
    
    # Check if timestamp is reasonable (between 1990 and 2040)
    min_date = datetime(1990, 1, 1)
    max_date = datetime(2040, 1, 1)
    min_seconds = min_date.timestamp()
    max_seconds = max_date.timestamp()
    
    if timestamp_seconds < min_seconds:
        dt = datetime.utcfromtimestamp(timestamp_seconds)
        raise TimestampValidationError(
            f"Timestamp appears too old: {dt.strftime('%Y-%m-%d %H:%M:%S')} (before 1990). "
            f"This may indicate a timestamp conversion error for {browser_type}."
        )
    
    if timestamp_seconds > max_seconds:
        dt = datetime.utcfromtimestamp(timestamp_seconds)
        raise TimestampValidationError(
            f"Timestamp appears to be in the future: {dt.strftime('%Y-%m-%d %H:%M:%S')} (after 2040). "
            f"This may indicate a timestamp conversion error for {browser_type}."
        )


def convert_gecko_timestamp(gecko_timestamp: Optional[int]) -> Tuple[int, str]:
    """
    Convert Gecko/Firefox timestamp (microseconds since Unix epoch) to ISO format.
    Firefox stores timestamps as microseconds since 1970-01-01 00:00:00 UTC.
    
    Args:
        gecko_timestamp: Gecko timestamp in microseconds
        
    Returns:
        tuple: (microseconds, ISO formatted datetime string)
    """
    if gecko_timestamp is None or gecko_timestamp == 0:
        return 0, ""
    
    # Validate
    validate_timestamp(gecko_timestamp, "Gecko/Firefox")
    
    # Convert microseconds to seconds
    timestamp_seconds = gecko_timestamp / 1000000
    dt = datetime.utcfromtimestamp(timestamp_seconds)
    return gecko_timestamp, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def convert_chromium_timestamp(chromium_timestamp: Optional[int]) -> Tuple[int, str]:
    """
    Convert Chromium timestamp to Unix microseconds and ISO format.
    Chromium stores timestamps as microseconds since 1601-01-01 00:00:00 UTC (Windows epoch).
    
    Args:
        chromium_timestamp: Chromium timestamp in microseconds since 1601
        
    Returns:
        tuple: (Unix microseconds, ISO formatted datetime string)
    """
    if chromium_timestamp is None or chromium_timestamp == 0:
        return 0, ""
    
    # Chromium epoch: January 1, 1601
    # Unix epoch: January 1, 1970
    # Difference: 11644473600 seconds
    chromium_epoch_offset = 11644473600
    
    # Convert to Unix timestamp (seconds since 1970)
    timestamp_seconds = (chromium_timestamp / 1000000) - chromium_epoch_offset
    
    # Convert to Unix microseconds for Timesketch
    unix_microseconds = int(timestamp_seconds * 1000000)
    
    # Validate
    validate_timestamp(unix_microseconds, "Chromium")
    
    dt = datetime.utcfromtimestamp(timestamp_seconds)
    return unix_microseconds, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def convert_webkit_timestamp(webkit_timestamp: Optional[float]) -> Tuple[int, str]:
    """
    Convert WebKit/Safari timestamp to Unix microseconds and ISO format.
    Safari stores timestamps as seconds (with decimal) since 2001-01-01 00:00:00 UTC (Cocoa/Core Data epoch).
    
    Args:
        webkit_timestamp: WebKit timestamp in seconds since 2001
        
    Returns:
        tuple: (Unix microseconds, ISO formatted datetime string)
    """
    if webkit_timestamp is None or webkit_timestamp == 0:
        return 0, ""
    
    # WebKit/Cocoa epoch: January 1, 2001
    # Unix epoch: January 1, 1970
    # Difference: 978307200 seconds
    webkit_epoch_offset = 978307200
    
    # Convert to Unix timestamp (seconds since 1970)
    timestamp_seconds = webkit_timestamp + webkit_epoch_offset
    
    # Convert to Unix microseconds for Timesketch
    unix_microseconds = int(timestamp_seconds * 1000000)
    
    # Validate
    validate_timestamp(unix_microseconds, "WebKit/Safari")
    
    dt = datetime.utcfromtimestamp(timestamp_seconds)
    return unix_microseconds, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def write_timesketch_csv(output_csv: str, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    """
    Write history data to Timesketch-compatible CSV format.
    
    Args:
        output_csv: Path to output CSV file
        fieldnames: List of CSV field names
        rows: List of row dictionaries to write
    """
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in rows:
            writer.writerow(row)


def connect_database_readonly(db_path: str) -> sqlite3.Connection:
    """
    Connect to database in read-only mode to avoid lock issues.
    
    Args:
        db_path: Path to database file
        
    Returns:
        SQLite connection object
        
    Raises:
        sqlite3.OperationalError: If database is locked or inaccessible
    """
    try:
        # Use URI with read-only mode to avoid locking issues
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        return conn
    except sqlite3.OperationalError as e:
        raise sqlite3.OperationalError(
            f"Cannot open database (it may be locked by the browser): {db_path}\n"
            f"Please close {db_path.split('/')[-2] if '/' in db_path else 'the browser'} "
            f"and try again, or copy the database file to a temporary location.\n"
            f"Original error: {e}"
        )


def validate_browser_schema(conn: sqlite3.Connection, expected_tables: List[str], browser_name: str) -> None:
    """
    Validate that required tables exist in the database.
    
    Args:
        conn: Database connection
        expected_tables: List of required table names
        browser_name: Browser name for error messages
        
    Raises:
        DatabaseValidationError: If required tables are missing
    """
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}
    
    missing_tables = set(expected_tables) - existing_tables
    if missing_tables:
        raise DatabaseValidationError(
            f"Database does not appear to be a valid {browser_name} history database.\n"
            f"Missing required tables: {', '.join(missing_tables)}\n"
            f"Found tables: {', '.join(sorted(existing_tables))}"
        )


def extract_chromium_history(db_path: str, output_csv: str, browser_name: Optional[str] = None) -> int:
    """
    Extract browser history from Chromium-based browsers and convert to Timesketch CSV.
    Works with all Chromium-based browsers: Chrome, Edge, Brave, Chromium, Opera, Vivaldi, etc.
    
    Args:
        db_path: Path to Chromium History database
        output_csv: Path to output CSV file
        browser_name: Optional custom name for data_type field (default: "Chromium")
        
    Returns:
        Number of entries processed
        
    Raises:
        DatabaseValidationError: If database validation fails
        sqlite3.Error: If database query fails
    """
    if browser_name is None:
        browser_name = "Chromium"
    
    # Connect to database
    conn = connect_database_readonly(db_path)
    
    # Validate schema
    validate_browser_schema(conn, ['visits', 'urls'], browser_name)
    
    cursor = conn.cursor()
    
    # Query to extract history visits with URL information
    query = """
    SELECT 
        visits.visit_time,
        urls.url,
        urls.title,
        visits.transition,
        visits.visit_duration,
        urls.visit_count,
        urls.typed_count,
        urls.last_visit_time
    FROM visits
    JOIN urls ON visits.url = urls.id
    ORDER BY visits.visit_time
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error as e:
        conn.close()
        raise sqlite3.Error(f"Error querying {browser_name} history: {e}")
    
    # Transition type mapping (Chromium transition types)
    transition_types = {
        0: "Link",
        1: "Typed",
        2: "Auto_Bookmark",
        3: "Auto_Subframe",
        4: "Manual_Subframe",
        5: "Generated",
        6: "Start_Page",
        7: "Form_Submit",
        8: "Reload",
        9: "Keyword",
        10: "Keyword_Generated"
    }
    
    rows = []
    validation_errors = []
    
    for idx, row in enumerate(results):
        chromium_timestamp = row[0]
        url = row[1] or ""
        title = row[2] or "(No title)"
        transition = row[3]
        visit_duration = row[4] or 0
        visit_count = row[5] or 0
        typed_count = row[6] or 0
        
        # Extract core transition type (lower 8 bits)
        core_transition = transition & 0xFF
        transition_name = transition_types.get(core_transition, f"Unknown({core_transition})")
        
        # Convert timestamp
        try:
            unix_microseconds, iso_datetime = convert_chromium_timestamp(chromium_timestamp)
        except TimestampValidationError as e:
            validation_errors.append(f"Entry {idx + 1}: {e}")
            if len(validation_errors) <= 3:  # Only store first few errors
                continue
            else:
                break  # Too many errors, likely a systematic issue
        
        # Construct message
        message = f"Visited: {title}"
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Visit Time',
            'message': message,
            'url': url,
            'title': title,
            'visit_type': transition_name,
            'visit_duration_us': visit_duration,
            'total_visits': visit_count,
            'typed_count': typed_count,
            'data_type': f'{browser_name.lower()}:history:visit'
        })
    
    conn.close()
    
    # Report validation errors if any
    if validation_errors:
        print(f"Warning: Found {len(validation_errors)} timestamp validation errors:", file=sys.stderr)
        for error in validation_errors[:3]:
            print(f"  {error}", file=sys.stderr)
        if len(validation_errors) > 3:
            print(f"  ... and {len(validation_errors) - 3} more errors", file=sys.stderr)
        print(f"Continuing with {len(rows)} valid entries...", file=sys.stderr)
    
    # Write CSV
    fieldnames = [
        'timestamp', 'datetime', 'timestamp_desc', 'message',
        'url', 'title', 'visit_type', 'visit_duration_us',
        'total_visits', 'typed_count', 'data_type'
    ]
    write_timesketch_csv(output_csv, fieldnames, rows)
    
    return len(rows)


def extract_gecko_history(db_path: str, output_csv: str, browser_name: Optional[str] = None) -> int:
    """
    Extract browser history from Gecko-based browsers (Firefox) and convert to Timesketch CSV.
    Works with Firefox and Firefox derivatives (Waterfox, LibreWolf, etc.)
    
    Args:
        db_path: Path to Gecko places.sqlite database
        output_csv: Path to output CSV file
        browser_name: Optional custom name for data_type field (default: "Firefox")
        
    Returns:
        Number of entries processed
        
    Raises:
        DatabaseValidationError: If database validation fails
        sqlite3.Error: If database query fails
    """
    if browser_name is None:
        browser_name = "Firefox"
    
    # Connect to database
    conn = connect_database_readonly(db_path)
    
    # Validate schema
    validate_browser_schema(conn, ['moz_historyvisits', 'moz_places'], browser_name)
    
    cursor = conn.cursor()
    
    # Query to extract history visits with URL information
    query = """
    SELECT 
        moz_historyvisits.visit_date as timestamp,
        moz_places.url,
        moz_places.title,
        moz_places.description,
        moz_historyvisits.visit_type,
        moz_historyvisits.from_visit
    FROM moz_historyvisits
    JOIN moz_places ON moz_historyvisits.place_id = moz_places.id
    ORDER BY moz_historyvisits.visit_date
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error as e:
        conn.close()
        raise sqlite3.Error(f"Error querying {browser_name} history: {e}")
    
    # Visit type mapping (Firefox visit types)
    visit_types = {
        1: "Link",
        2: "Typed",
        3: "Bookmark",
        4: "Embed",
        5: "Redirect_Permanent",
        6: "Redirect_Temporary",
        7: "Download",
        8: "Framed_Link",
        9: "Reload"
    }
    
    rows = []
    validation_errors = []
    
    for idx, row in enumerate(results):
        timestamp_us = row[0]
        url = row[1] or ""
        title = row[2] or "(No title)"
        description = row[3] or ""
        visit_type_id = row[4]
        
        visit_type_name = visit_types.get(visit_type_id, f"Unknown({visit_type_id})")
        
        # Convert timestamp
        try:
            unix_microseconds, iso_datetime = convert_gecko_timestamp(timestamp_us)
        except TimestampValidationError as e:
            validation_errors.append(f"Entry {idx + 1}: {e}")
            if len(validation_errors) <= 3:
                continue
            else:
                break
        
        # Construct message
        message = f"Visited: {title}"
        if description:
            message += f" - {description}"
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Visit Time',
            'message': message,
            'url': url,
            'title': title,
            'visit_type': visit_type_name,
            'data_type': f'{browser_name.lower()}:history:visit'
        })
    
    conn.close()
    
    # Report validation errors if any
    if validation_errors:
        print(f"Warning: Found {len(validation_errors)} timestamp validation errors:", file=sys.stderr)
        for error in validation_errors[:3]:
            print(f"  {error}", file=sys.stderr)
        if len(validation_errors) > 3:
            print(f"  ... and {len(validation_errors) - 3} more errors", file=sys.stderr)
        print(f"Continuing with {len(rows)} valid entries...", file=sys.stderr)
    
    # Write CSV
    fieldnames = [
        'timestamp', 'datetime', 'timestamp_desc', 'message',
        'url', 'title', 'visit_type', 'data_type'
    ]
    write_timesketch_csv(output_csv, fieldnames, rows)
    
    return len(rows)


def extract_webkit_history(db_path: str, output_csv: str, browser_name: Optional[str] = None) -> int:
    """
    Extract browser history from WebKit-based browsers (Safari) and convert to Timesketch CSV.
    
    Args:
        db_path: Path to Safari History.db database
        output_csv: Path to output CSV file
        browser_name: Optional custom name for data_type field (default: "Safari")
        
    Returns:
        Number of entries processed
        
    Raises:
        DatabaseValidationError: If database validation fails
        sqlite3.Error: If database query fails
    """
    if browser_name is None:
        browser_name = "Safari"
    
    # Connect to database
    conn = connect_database_readonly(db_path)
    
    # Validate schema
    validate_browser_schema(conn, ['history_visits', 'history_items'], browser_name)
    
    cursor = conn.cursor()
    
    # Query to extract history visits with URL information
    query = """
    SELECT 
        history_visits.visit_time,
        history_items.url,
        history_items.title,
        history_visits.title as visit_title
    FROM history_visits
    JOIN history_items ON history_visits.history_item = history_items.id
    ORDER BY history_visits.visit_time
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error as e:
        conn.close()
        raise sqlite3.Error(f"Error querying {browser_name} history: {e}")
    
    rows = []
    validation_errors = []
    
    for idx, row in enumerate(results):
        webkit_timestamp = row[0]
        url = row[1] or ""
        title = row[2] or row[3] or "(No title)"
        
        # Convert timestamp
        try:
            unix_microseconds, iso_datetime = convert_webkit_timestamp(webkit_timestamp)
        except TimestampValidationError as e:
            validation_errors.append(f"Entry {idx + 1}: {e}")
            if len(validation_errors) <= 3:
                continue
            else:
                break
        
        # Construct message
        message = f"Visited: {title}"
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Visit Time',
            'message': message,
            'url': url,
            'title': title,
            'data_type': f'{browser_name.lower()}:history:visit'
        })
    
    conn.close()
    
    # Report validation errors if any
    if validation_errors:
        print(f"Warning: Found {len(validation_errors)} timestamp validation errors:", file=sys.stderr)
        for error in validation_errors[:3]:
            print(f"  {error}", file=sys.stderr)
        if len(validation_errors) > 3:
            print(f"  ... and {len(validation_errors) - 3} more errors", file=sys.stderr)
        print(f"Continuing with {len(rows)} valid entries...", file=sys.stderr)
    
    # Write CSV
    fieldnames = [
        'timestamp', 'datetime', 'timestamp_desc', 'message',
        'url', 'title', 'data_type'
    ]
    write_timesketch_csv(output_csv, fieldnames, rows)
    
    return len(rows)


def generate_default_output_filename(browser_type: str, input_path: str) -> str:
    """
    Generate a sensible default output filename based on browser type and input.
    
    Args:
        browser_type: Browser type (gecko, chromium, webkit)
        input_path: Input database path
        
    Returns:
        Generated output filename
    """
    # Extract browser name from path if possible
    path_lower = input_path.lower()
    
    browser_names = {
        'firefox': 'firefox',
        'chrome': 'chrome',
        'edge': 'edge',
        'brave': 'brave',
        'opera': 'opera',
        'vivaldi': 'vivaldi',
        'safari': 'safari',
    }
    
    detected_name = None
    for name_key, name_value in browser_names.items():
        if name_key in path_lower:
            detected_name = name_value
            break
    
    if detected_name:
        return f"{detected_name}_history_timesketch.csv"
    else:
        return f"{browser_type}_history_timesketch.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Convert browser history to Timesketch CSV format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Browser Engine Types:
  gecko, firefox      - Gecko-based browsers (Firefox, Waterfox, LibreWolf, etc.)
  chromium            - Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi, etc.)
  webkit, safari      - WebKit-based browsers (Safari)
  auto                - Auto-detect browser type from database schema

All Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi) use identical database 
schemas and can be processed with the "chromium" option. Use --browser-name to customize 
the label in the output if needed.

HOW TO FIND YOUR PROFILE PATH:
  Firefox:
    1. Open Firefox and type: about:support
    2. Look for "Profile Folder" or "Profile Directory"
    3. Click "Open Folder" button or note the path
    4. The places.sqlite file is in this directory
    
  Chromium browsers (Chrome/Edge/Brave/etc.):
    1. Open browser and type: chrome://version/
       (or edge://version/, brave://version/, etc.)
    2. Look for "Profile Path" - this shows the full path
    3. The History file (no extension) is in this directory
    
  Safari:
    Always at: ~/Library/Safari/History.db

Example usage:
  # Auto-detect browser type
  python browser2timesketch.py -i ~/.mozilla/firefox/xyz.default/places.sqlite
  
  # Firefox with custom output
  python browser2timesketch.py -b firefox -i ~/.mozilla/firefox/xyz.default/places.sqlite -o firefox.csv
  
  # Any Chromium browser (Chrome, Edge, Brave, etc.)
  python browser2timesketch.py -b chromium -i ~/.config/google-chrome/Default/History -o output.csv
  
  # Chromium browser with custom label
  python browser2timesketch.py -b chromium --browser-name "Brave" -i ~/.config/BraveSoftware/Brave-Browser/Default/History
  
  # Safari (macOS)
  python browser2timesketch.py -b safari -i ~/Library/Safari/History.db

Database Locations:
  Gecko/Firefox:
    Linux:   ~/.mozilla/firefox/<profile>/places.sqlite
    macOS:   ~/Library/Application Support/Firefox/Profiles/<profile>/places.sqlite
    Windows: %APPDATA%\\Mozilla\\Firefox\\Profiles\\<profile>\\places.sqlite
  
  Chromium (Chrome/Edge/Brave/Opera/Vivaldi):
    Chrome Linux:   ~/.config/google-chrome/Default/History
    Chrome macOS:   ~/Library/Application Support/Google/Chrome/Default/History
    Chrome Windows: %LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\History
    
    Edge Windows:   %LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\History
    Edge macOS:     ~/Library/Application Support/Microsoft Edge/Default/History
    
    Brave Linux:    ~/.config/BraveSoftware/Brave-Browser/Default/History
    Brave macOS:    ~/Library/Application Support/BraveSoftware/Brave-Browser/Default/History
    Brave Windows:  %LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\Default\\History
  
  WebKit/Safari:
    macOS:   ~/Library/Safari/History.db

Note: The script uses read-only mode to avoid database lock issues, but closing 
the browser is still recommended for best results.
        """
    )
    
    parser.add_argument(
        '-b', '--browser',
        choices=['gecko', 'firefox', 'chromium', 'webkit', 'safari', 'auto'],
        default='auto',
        help='Browser engine type (default: auto-detect)'
    )
    
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to browser history database'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Output CSV file path (default: auto-generated based on browser type)'
    )
    
    parser.add_argument(
        '--browser-name',
        help='Custom browser name for the data_type field (e.g., "Chrome", "Brave", "Edge")'
    )
    
    args = parser.parse_args()
    
    try:
        # Validate database file
        print(f"Validating database: {args.input}")
        validate_sqlite_database(args.input)
        print("✓ Database is valid SQLite file")
        
        # Detect or validate browser type
        browser_type = args.browser.lower()
        
        if browser_type == 'auto':
            print("Auto-detecting browser type...")
            browser_type = detect_browser_type(args.input)
            print(f"✓ Detected browser type: {browser_type}")
        else:
            # Normalize aliases
            if browser_type == 'firefox':
                browser_type = 'gecko'
            elif browser_type == 'safari':
                browser_type = 'webkit'
            
            # Validate that the database matches the specified type
            detected_type = detect_browser_type(args.input)
            if detected_type != browser_type:
                print(f"Warning: You specified '{args.browser}' but database appears to be '{detected_type}'", 
                      file=sys.stderr)
                response = input("Continue anyway? [y/N]: ")
                if response.lower() != 'y':
                    return 1
        
        # Generate output filename if not provided
        if args.output:
            output_csv = args.output
        else:
            output_csv = generate_default_output_filename(browser_type, args.input)
            print(f"Using output filename: {output_csv}")
        
        # Extract history based on browser type
        print(f"Extracting history from {browser_type} database...")
        
        if browser_type == 'gecko':
            num_entries = extract_gecko_history(args.input, output_csv, args.browser_name)
        elif browser_type == 'chromium':
            num_entries = extract_chromium_history(args.input, output_csv, args.browser_name)
        elif browser_type == 'webkit':
            num_entries = extract_webkit_history(args.input, output_csv, args.browser_name)
        else:
            raise ValueError(f"Unknown browser type: {browser_type}")
        
        print(f"\n✓ Successfully converted {num_entries} history entries")
        print(f"✓ Output saved to: {output_csv}")
        return 0
        
    except DatabaseValidationError as e:
        print(f"Database Validation Error: {e}", file=sys.stderr)
        return 1
    except BrowserDetectionError as e:
        print(f"Browser Detection Error: {e}", file=sys.stderr)
        return 1
    except TimestampValidationError as e:
        print(f"Timestamp Validation Error: {e}", file=sys.stderr)
        print("This indicates a systematic problem with timestamp conversion.", file=sys.stderr)
        return 1
    except sqlite3.Error as e:
        print(f"Database Error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"File Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())