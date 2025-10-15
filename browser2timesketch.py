#!/usr/bin/env python3
"""
Browser History to Timesketch CSV Converter

Converts browser history from major browser engines to Timesketch-compatible CSV format.
Supports: Gecko (Firefox), Chromium (Chrome/Edge/Brave/etc.), WebKit (Safari)
"""

import sqlite3
import csv
import argparse
from datetime import datetime, timedelta
from pathlib import Path


def convert_gecko_timestamp(gecko_timestamp):
    """
    Convert Gecko/Firefox timestamp (microseconds since Unix epoch) to ISO format.
    Firefox stores timestamps as microseconds since 1970-01-01 00:00:00 UTC.
    
    Args:
        gecko_timestamp: Gecko timestamp in microseconds
        
    Returns:
        tuple: (microseconds, ISO formatted datetime string)
    """
    if gecko_timestamp is None:
        return 0, ""
    
    # Convert microseconds to seconds
    timestamp_seconds = gecko_timestamp / 1000000
    dt = datetime.utcfromtimestamp(timestamp_seconds)
    return gecko_timestamp, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def convert_chromium_timestamp(chromium_timestamp):
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
    
    dt = datetime.utcfromtimestamp(timestamp_seconds)
    return unix_microseconds, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def convert_webkit_timestamp(webkit_timestamp):
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
    
    dt = datetime.utcfromtimestamp(timestamp_seconds)
    return unix_microseconds, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def extract_chromium_history(db_path, output_csv, browser_name=None):
    """
    Extract browser history from Chromium-based browsers and convert to Timesketch CSV.
    Works with all Chromium-based browsers: Chrome, Edge, Brave, Chromium, Opera, Vivaldi, etc.
    
    Args:
        db_path: Path to Chromium History database
        output_csv: Path to output CSV file
        browser_name: Optional custom name for data_type field (default: "Chromium")
    """
    
    if browser_name is None:
        browser_name = "Chromium"
    
    # Check if database exists
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Chromium database not found: {db_path}")
    
    # Connect to Chromium SQLite database
    conn = sqlite3.connect(db_path)
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
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Transition type mapping (Chromium transition types)
    # Core types (bits 0-7)
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
    
    # Write to Timesketch CSV format
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'timestamp',
            'datetime',
            'timestamp_desc',
            'message',
            'url',
            'title',
            'visit_type',
            'visit_duration_us',
            'total_visits',
            'typed_count',
            'data_type'
        ]
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in results:
            chromium_timestamp = row[0]
            url = row[1] or ""
            title = row[2] or "(No title)"
            transition = row[3]
            visit_duration = row[4] or 0
            visit_count = row[5] or 0
            typed_count = row[6] or 0
            last_visit = row[7]
            
            # Extract core transition type (lower 8 bits)
            core_transition = transition & 0xFF
            transition_name = transition_types.get(core_transition, f"Unknown({core_transition})")
            
            # Convert timestamp
            unix_microseconds, iso_datetime = convert_chromium_timestamp(chromium_timestamp)
            
            # Construct message
            message = f"Visited: {title}"
            
            writer.writerow({
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
    
    print(f"Successfully converted {len(results)} history entries from {browser_name}")
    print(f"Output saved to: {output_csv}")


def extract_gecko_history(db_path, output_csv, browser_name=None):
    """
    Extract browser history from Gecko-based browsers (Firefox) and convert to Timesketch CSV.
    Works with Firefox and Firefox derivatives (Waterfox, LibreWolf, etc.)
    
    Args:
        db_path: Path to Gecko places.sqlite database
        output_csv: Path to output CSV file
        browser_name: Optional custom name for data_type field (default: "Firefox")
    """
    
    if browser_name is None:
        browser_name = "Firefox"
    
    # Check if database exists
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Gecko database not found: {db_path}")
    
    # Connect to Firefox SQLite database
    conn = sqlite3.connect(db_path)
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
    
    cursor.execute(query)
    results = cursor.fetchall()
    
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
    
    # Write to Timesketch CSV format
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        # Timesketch expected fields
        fieldnames = [
            'timestamp',
            'datetime',
            'timestamp_desc',
            'message',
            'url',
            'title',
            'visit_type',
            'data_type'
        ]
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in results:
            timestamp_us = row[0]  # Firefox timestamp in microseconds
            url = row[1] or ""
            title = row[2] or "(No title)"
            description = row[3] or ""
            visit_type_id = row[4]
            from_visit = row[5]
            
            visit_type_name = visit_types.get(visit_type_id, f"Unknown({visit_type_id})")
            
            # Convert timestamp
            unix_microseconds, iso_datetime = convert_gecko_timestamp(timestamp_us)
            
            # Construct message
            message = f"Visited: {title}"
            if description:
                message += f" - {description}"
            
            writer.writerow({
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
    
    print(f"Successfully converted {len(results)} history entries from {browser_name}")
    print(f"Output saved to: {output_csv}")


def extract_webkit_history(db_path, output_csv, browser_name=None):
    """
    Extract browser history from WebKit-based browsers (Safari) and convert to Timesketch CSV.
    
    Args:
        db_path: Path to Safari History.db database
        output_csv: Path to output CSV file
        browser_name: Optional custom name for data_type field (default: "Safari")
    """
    
    if browser_name is None:
        browser_name = "Safari"
    
    # Check if database exists
    if not Path(db_path).exists():
        raise FileNotFoundError(f"WebKit database not found: {db_path}")
    
    # Connect to Safari SQLite database
    conn = sqlite3.connect(db_path)
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
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Write to Timesketch CSV format
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'timestamp',
            'datetime',
            'timestamp_desc',
            'message',
            'url',
            'title',
            'data_type'
        ]
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in results:
            webkit_timestamp = row[0]
            url = row[1] or ""
            title = row[2] or row[3] or "(No title)"  # Use visit_title as fallback
            
            # Convert timestamp
            unix_microseconds, iso_datetime = convert_webkit_timestamp(webkit_timestamp)
            
            # Construct message
            message = f"Visited: {title}"
            
            writer.writerow({
                'timestamp': unix_microseconds,
                'datetime': iso_datetime,
                'timestamp_desc': 'Visit Time',
                'message': message,
                'url': url,
                'title': title,
                'data_type': f'{browser_name.lower()}:history:visit'
            })
    
    conn.close()
    
    print(f"Successfully converted {len(results)} history entries from {browser_name}")
    print(f"Output saved to: {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert browser history to Timesketch CSV format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Browser Engine Types:
  gecko, firefox      - Gecko-based browsers (Firefox, Waterfox, LibreWolf, etc.)
  chromium            - Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi, etc.)
  webkit, safari      - WebKit-based browsers (Safari)

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
  # Firefox
  python browser_to_timesketch.py -b firefox -i ~/.mozilla/firefox/xyz.default/places.sqlite -o output.csv
  
  # Any Chromium browser (Chrome, Edge, Brave, etc.)
  python browser_to_timesketch.py -b chromium -i ~/.config/google-chrome/Default/History -o output.csv
  
  # Chromium browser with custom label
  python browser_to_timesketch.py -b chromium --browser-name "Brave" -i ~/.config/BraveSoftware/Brave-Browser/Default/History -o output.csv
  
  # Safari (macOS)
  python browser_to_timesketch.py -b safari -i ~/Library/Safari/History.db -o output.csv

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

Note: Close the browser before running this script to avoid database lock issues.
You may want to copy the database file to a temporary location first.
        """
    )
    
    parser.add_argument(
        '-b', '--browser',
        required=True,
        choices=['gecko', 'firefox', 'chromium', 'webkit', 'safari'],
        help='Browser engine type (firefox and gecko are aliases, safari and webkit are aliases)'
    )
    
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to browser history database'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='browser_history_timesketch.csv',
        help='Output CSV file path (default: browser_history_timesketch.csv)'
    )
    
    parser.add_argument(
        '--browser-name',
        default=None,
        help='Custom browser name for the data_type field (e.g., "Chrome", "Brave", "Edge")'
    )
    
    args = parser.parse_args()
    
    try:
        # Normalize browser type
        browser_type = args.browser.lower()
        
        if browser_type in ['gecko', 'firefox']:
            extract_gecko_history(args.input, args.output, args.browser_name)
        elif browser_type == 'chromium':
            extract_chromium_history(args.input, args.output, args.browser_name)
        elif browser_type in ['webkit', 'safari']:
            extract_webkit_history(args.input, args.output, args.browser_name)
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())