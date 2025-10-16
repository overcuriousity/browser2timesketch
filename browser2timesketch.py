#!/usr/bin/env python3
"""
Browser History to Timesketch CSV Converter - Comprehensive Edition

Extracts ALL timestamped browser events to Timesketch-compatible CSV format.
Browser-agnostic output with consistent event naming across all browsers.

Supports:
- Firefox/Gecko: visits, bookmarks, downloads, form history, annotations, 
  page metadata, input history, keywords, origins
- Chrome/Chromium/Edge/Brave: visits, downloads, searches, autofill, 
  favicons, media history, site engagement
- Safari/WebKit: visits, bookmarks, downloads, reading list, top sites

Output format: Timesketch-compatible CSV with browser-agnostic event types
"""

import sqlite3
import csv
import argparse
import sys
from datetime import datetime, timezone
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
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        conn.close()
        
        if 'moz_historyvisits' in tables and 'moz_places' in tables:
            return 'gecko'
        
        if 'visits' in tables and 'urls' in tables:
            return 'chromium'
        
        if 'history_visits' in tables and 'history_items' in tables:
            return 'webkit'
        
        raise BrowserDetectionError(
            f"Cannot determine browser type. Found tables: {', '.join(sorted(tables))}"
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
        return
    
    timestamp_seconds = unix_microseconds / 1000000
    
    min_date = datetime(1990, 1, 1)
    max_date = datetime(2040, 1, 1)
    min_seconds = min_date.timestamp()
    max_seconds = max_date.timestamp()
    
    if timestamp_seconds < min_seconds:
        dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        raise TimestampValidationError(
            f"Timestamp appears too old: {dt.strftime('%Y-%m-%d %H:%M:%S')} (before 1990). "
            f"This may indicate a timestamp conversion error for {browser_type}."
        )
    
    if timestamp_seconds > max_seconds:
        dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        raise TimestampValidationError(
            f"Timestamp appears to be in the future: {dt.strftime('%Y-%m-%d %H:%M:%S')} (after 2040). "
            f"This may indicate a timestamp conversion error for {browser_type}."
        )


def convert_gecko_timestamp(gecko_timestamp: Optional[int]) -> Tuple[int, str]:
    """Convert Gecko/Firefox timestamp to Unix microseconds and ISO format."""
    if gecko_timestamp is None or gecko_timestamp == 0:
        return 0, ""
    
    validate_timestamp(gecko_timestamp, "Gecko/Firefox")
    
    timestamp_seconds = gecko_timestamp / 1000000
    dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
    return gecko_timestamp, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def convert_chromium_timestamp(chromium_timestamp: Optional[int]) -> Tuple[int, str]:
    """Convert Chromium timestamp to Unix microseconds and ISO format."""
    if chromium_timestamp is None or chromium_timestamp == 0:
        return 0, ""
    
    chromium_epoch_offset = 11644473600
    timestamp_seconds = (chromium_timestamp / 1000000) - chromium_epoch_offset
    unix_microseconds = int(timestamp_seconds * 1000000)
    
    validate_timestamp(unix_microseconds, "Chromium")
    
    dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
    return unix_microseconds, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def convert_webkit_timestamp(webkit_timestamp: Optional[float]) -> Tuple[int, str]:
    """Convert WebKit/Safari timestamp to Unix microseconds and ISO format."""
    if webkit_timestamp is None or webkit_timestamp == 0:
        return 0, ""
    
    webkit_epoch_offset = 978307200
    timestamp_seconds = webkit_timestamp + webkit_epoch_offset
    unix_microseconds = int(timestamp_seconds * 1000000)
    
    validate_timestamp(unix_microseconds, "WebKit/Safari")
    
    dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
    return unix_microseconds, dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def write_timesketch_csv(output_csv: str, rows: List[Dict[str, Any]]) -> None:
    """
    Write history data to Timesketch-compatible CSV format with dynamic fields.
    
    Args:
        output_csv: Path to output CSV file
        rows: List of row dictionaries to write
    """
    if not rows:
        return
    
    # Collect all unique fields from all rows
    all_fields = set()
    for row in rows:
        all_fields.update(row.keys())
    
    # Define standard field order (these come first)
    standard_fields = ['timestamp', 'datetime', 'timestamp_desc', 'message', 'data_type']
    
    # Build fieldnames list with standard fields first, then alphabetically sorted remainder
    fieldnames = [f for f in standard_fields if f in all_fields]
    remaining_fields = sorted(all_fields - set(standard_fields))
    fieldnames.extend(remaining_fields)
    
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for row in rows:
            writer.writerow(row)


def connect_database_readonly(db_path: str) -> sqlite3.Connection:
    """Connect to database in read-only mode to avoid lock issues."""
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        return conn
    except sqlite3.OperationalError as e:
        raise sqlite3.OperationalError(
            f"Cannot open database (it may be locked by the browser): {db_path}\n"
            f"Please close the browser and try again, or copy the database file.\n"
            f"Original error: {e}"
        )


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.cursor()
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        return column_name in columns
    except sqlite3.Error:
        return False


# ============================================================================
# CHROMIUM EXTRACTORS
# ============================================================================

def extract_chromium_visits(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract visit events from Chromium database with resolved foreign keys."""
    cursor = conn.cursor()
    
    query = """
    SELECT 
        visits.visit_time,
        urls.url,
        urls.title,
        visits.transition,
        visits.visit_duration,
        urls.visit_count,
        urls.typed_count,
        visits.segment_id,
        visits.incremented_omnibox_typed_score,
        urls.hidden,
        from_urls.url as from_url,
        from_urls.title as from_title,
        opener_urls.url as opener_url,
        opener_urls.title as opener_title
    FROM visits
    JOIN urls ON visits.url = urls.id
    LEFT JOIN visits from_visits ON visits.from_visit = from_visits.id
    LEFT JOIN urls from_urls ON from_visits.url = from_urls.id
    LEFT JOIN visits opener_visits ON visits.opener_visit = opener_visits.id
    LEFT JOIN urls opener_urls ON opener_visits.url = opener_urls.id
    ORDER BY visits.visit_time
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    transition_types = {
        0: "Link", 1: "Typed", 2: "Auto_Bookmark", 3: "Auto_Subframe",
        4: "Manual_Subframe", 5: "Generated", 6: "Start_Page",
        7: "Form_Submit", 8: "Reload", 9: "Keyword", 10: "Keyword_Generated"
    }
    
    rows = []
    for row in results:
        (chromium_timestamp, url, title, transition, visit_duration,
         visit_count, typed_count, segment_id, incremented_typed, hidden,
         from_url, from_title, opener_url, opener_title) = row
        
        try:
            unix_microseconds, iso_datetime = convert_chromium_timestamp(chromium_timestamp)
        except TimestampValidationError:
            continue
        
        core_transition = transition & 0xFF
        transition_name = transition_types.get(core_transition, f"Unknown({core_transition})")
        
        # Build row with only useful fields
        row_data = {
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Visit Time',
            'message': f"Visited: {title or '(No title)'}",
            'data_type': 'browser:page:visit',
            'browser': browser_name,
            'url': url or "",
            'title': title or "(No title)",
            'visit_type': transition_name,
            'visit_duration_us': visit_duration or 0,
            'total_visits': visit_count or 0,
            'typed_count': typed_count or 0,
            'typed_in_omnibox': bool(incremented_typed),
            'hidden': bool(hidden)
        }
        
        # Add optional fields only if present
        if from_url:
            row_data['from_url'] = from_url
            if from_title:
                row_data['from_title'] = from_title
        
        if opener_url:
            row_data['opener_url'] = opener_url
            if opener_title:
                row_data['opener_title'] = opener_title
        
        # Add session ID only if non-zero
        if segment_id and segment_id != 0:
            row_data['session_id'] = segment_id
        
        rows.append(row_data)
    
    return rows


def extract_chromium_downloads(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract download events from Chromium database."""
    if not table_exists(conn, 'downloads'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        id,
        guid,
        current_path,
        target_path,
        start_time,
        received_bytes,
        total_bytes,
        state,
        danger_type,
        interrupt_reason,
        end_time,
        opened,
        last_access_time,
        referrer,
        tab_url,
        mime_type
    FROM downloads
    ORDER BY start_time
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    download_states = {
        0: "In Progress",
        1: "Complete",
        2: "Cancelled",
        3: "Interrupted",
        4: "Dangerous"
    }
    
    rows = []
    for row in results:
        (dl_id, guid, current_path, target_path, start_time, received_bytes,
         total_bytes, state, danger_type, interrupt_reason, end_time, opened,
         last_access_time, referrer, tab_url, mime_type) = row
        
        try:
            start_us, start_iso = convert_chromium_timestamp(start_time)
            end_us, end_iso = convert_chromium_timestamp(end_time) if end_time else (0, "")
            access_us, access_iso = convert_chromium_timestamp(last_access_time) if last_access_time else (0, "")
        except TimestampValidationError:
            continue
        
        state_name = download_states.get(state, f"Unknown({state})")
        filename = Path(target_path).name if target_path else "(unknown)"
        
        # Download start event
        rows.append({
            'timestamp': start_us,
            'datetime': start_iso,
            'timestamp_desc': 'Download Started',
            'message': f"Download started: {filename} ({mime_type or 'unknown type'})",
            'data_type': 'browser:download:start',
            'browser': browser_name,
            'download_id': dl_id,
            'filename': filename,
            'file_path': target_path or "",
            'file_size_bytes': total_bytes or 0,
            'mime_type': mime_type or "",
            'download_state': state_name,
            'referrer_url': referrer or "",
            'tab_url': tab_url or "",
            'dangerous': bool(danger_type),
            'interrupted': bool(interrupt_reason)
        })
        
        # Download complete event (if completed)
        if end_time and end_time != start_time:
            duration_seconds = (end_us - start_us) / 1000000
            rows.append({
                'timestamp': end_us,
                'datetime': end_iso,
                'timestamp_desc': 'Download Completed',
                'message': f"Download completed: {filename} ({received_bytes or 0} bytes in {duration_seconds:.1f}s)",
                'data_type': 'browser:download:complete',
                'browser': browser_name,
                'download_id': dl_id,
                'filename': filename,
                'file_path': target_path or "",
                'file_size_bytes': received_bytes or 0,
                'mime_type': mime_type or "",
                'download_state': state_name,
                'download_duration_seconds': duration_seconds
            })
        
        # Last access event (if different from completion)
        if last_access_time and last_access_time != end_time and last_access_time != start_time:
            rows.append({
                'timestamp': access_us,
                'datetime': access_iso,
                'timestamp_desc': 'File Accessed',
                'message': f"Downloaded file accessed: {filename}",
                'data_type': 'browser:download:accessed',
                'browser': browser_name,
                'download_id': dl_id,
                'filename': filename,
                'file_path': target_path or ""
            })
    
    return rows


def extract_chromium_search_terms(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract search terms from Chromium database."""
    if not table_exists(conn, 'keyword_search_terms'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        kst.term,
        kst.normalized_term,
        u.url,
        u.title,
        u.last_visit_time
    FROM keyword_search_terms kst
    JOIN urls u ON kst.url_id = u.id
    ORDER BY u.last_visit_time
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        term, normalized_term, url, title, last_visit = row
        
        try:
            unix_microseconds, iso_datetime = convert_chromium_timestamp(last_visit)
        except TimestampValidationError:
            continue
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Search Performed',
            'message': f"Search: {term}",
            'data_type': 'browser:search:query',
            'browser': browser_name,
            'search_term': term,
            'normalized_search_term': normalized_term,
            'search_url': url or "",
            'search_page_title': title or ""
        })
    
    return rows


def extract_chromium_autofill(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract autofill/form data from Chromium database."""
    if not table_exists(conn, 'autofill'):
        return []
    
    cursor = conn.cursor()
    
    # Check which timestamp columns exist
    has_created = column_exists(conn, 'autofill', 'date_created')
    has_last_used = column_exists(conn, 'autofill', 'date_last_used')
    
    if not (has_created or has_last_used):
        return []
    
    # Build query based on available columns
    timestamp_cols = []
    if has_created:
        timestamp_cols.append('date_created')
    if has_last_used:
        timestamp_cols.append('date_last_used')
    
    query = f"""
    SELECT 
        name,
        value,
        {', '.join(timestamp_cols)},
        count
    FROM autofill
    WHERE {' OR '.join([f'{col} > 0' for col in timestamp_cols])}
    ORDER BY {timestamp_cols[0]}
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        name, value, *timestamps, count = row
        date_created = timestamps[0] if has_created else None
        date_last_used = timestamps[1] if has_last_used and len(timestamps) > 1 else timestamps[0] if not has_created else None
        
        # Form field created/first used
        if date_created:
            try:
                created_us, created_iso = convert_chromium_timestamp(date_created)
                rows.append({
                    'timestamp': created_us,
                    'datetime': created_iso,
                    'timestamp_desc': 'Form Field First Used',
                    'message': f"First use of form field: {name}",
                    'data_type': 'browser:form:first_use',
                    'browser': browser_name,
                    'form_field_name': name,
                    'form_field_value': value[:50] + '...' if len(value) > 50 else value,
                    'total_uses': count or 0
                })
            except TimestampValidationError:
                pass
        
        # Form field last used (if different)
        if date_last_used and date_last_used != date_created:
            try:
                last_us, last_iso = convert_chromium_timestamp(date_last_used)
                rows.append({
                    'timestamp': last_us,
                    'datetime': last_iso,
                    'timestamp_desc': 'Form Field Last Used',
                    'message': f"Used form field: {name}",
                    'data_type': 'browser:form:use',
                    'browser': browser_name,
                    'form_field_name': name,
                    'form_field_value': value[:50] + '...' if len(value) > 50 else value,
                    'total_uses': count or 0
                })
            except TimestampValidationError:
                pass
    
    return rows


def extract_chromium_favicons(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract favicon mapping timestamps from Chromium database."""
    if not table_exists(conn, 'icon_mapping'):
        return []
    
    # Check if last_updated column exists (not in all Chromium versions)
    if not column_exists(conn, 'icon_mapping', 'last_updated'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        im.last_updated,
        im.page_url,
        f.url as favicon_url
    FROM icon_mapping im
    LEFT JOIN favicons f ON im.icon_id = f.id
    WHERE im.last_updated > 0
    ORDER BY im.last_updated
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        last_updated, page_url, favicon_url = row
        
        try:
            unix_microseconds, iso_datetime = convert_chromium_timestamp(last_updated)
        except TimestampValidationError:
            continue
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Favicon Updated',
            'message': f"Updated favicon for: {page_url}",
            'data_type': 'browser:favicon:update',
            'browser': browser_name,
            'page_url': page_url or "",
            'favicon_url': favicon_url or ""
        })
    
    return rows


def extract_chromium_media_history(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract media playback history from Chromium database."""
    if not table_exists(conn, 'playback'):
        return []
    
    cursor = conn.cursor()
    
    # Check available columns
    has_last_updated = column_exists(conn, 'playback', 'last_updated_time_s')
    
    if not has_last_updated:
        return []
    
    query = """
    SELECT 
        p.url,
        p.watch_time_s,
        p.has_audio,
        p.has_video,
        p.last_updated_time_s
    FROM playback p
    WHERE p.last_updated_time_s > 0
    ORDER BY p.last_updated_time_s
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        url, watch_time, has_audio, has_video, last_updated = row
        
        # Convert Unix seconds to microseconds for consistency
        unix_microseconds = int(last_updated * 1000000)
        
        try:
            validate_timestamp(unix_microseconds, "Chromium Media")
            dt = datetime.fromtimestamp(last_updated, tz=timezone.utc)
            iso_datetime = dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except TimestampValidationError:
            continue
        
        media_type = []
        if has_audio:
            media_type.append("audio")
        if has_video:
            media_type.append("video")
        media_type_str = "+".join(media_type) if media_type else "unknown"
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Media Playback',
            'message': f"Played {media_type_str}: {url} ({watch_time:.1f}s)",
            'data_type': 'browser:media:playback',
            'browser': browser_name,
            'media_url': url or "",
            'watch_time_seconds': watch_time or 0,
            'has_audio': bool(has_audio),
            'has_video': bool(has_video)
        })
    
    return rows


def extract_chromium_site_engagement(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract site engagement scores from Chromium database."""
    if not table_exists(conn, 'site_engagement'):
        return []
    
    cursor = conn.cursor()
    
    # Check for timestamp column
    has_last_engagement = column_exists(conn, 'site_engagement', 'last_engagement_time')
    
    if not has_last_engagement:
        return []
    
    query = """
    SELECT 
        origin_url,
        score,
        last_engagement_time
    FROM site_engagement
    WHERE last_engagement_time > 0 AND score > 0
    ORDER BY last_engagement_time
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        origin_url, score, last_engagement = row
        
        # Convert internal timestamp format (typically Unix seconds)
        unix_microseconds = int(last_engagement * 1000000)
        
        try:
            validate_timestamp(unix_microseconds, "Chromium Site Engagement")
            dt = datetime.fromtimestamp(last_engagement, tz=timezone.utc)
            iso_datetime = dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except TimestampValidationError:
            continue
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Site Engagement Updated',
            'message': f"Site engagement: {origin_url} (score: {score:.1f})",
            'data_type': 'browser:engagement:update',
            'browser': browser_name,
            'site_url': origin_url or "",
            'engagement_score': score or 0
        })
    
    return rows


# ============================================================================
# GECKO/FIREFOX EXTRACTORS
# ============================================================================

def extract_gecko_visits(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract visit events from Gecko database with resolved foreign keys."""
    cursor = conn.cursor()
    
    query = """
    SELECT 
        v.visit_date,
        p.url,
        p.title,
        p.description,
        v.visit_type,
        v.session,
        p.visit_count,
        p.typed,
        p.frecency,
        p.hidden,
        p.rev_host,
        prev_p.url as from_url,
        prev_p.title as from_title
    FROM moz_historyvisits v
    JOIN moz_places p ON v.place_id = p.id
    LEFT JOIN moz_historyvisits prev_v ON v.from_visit = prev_v.id
    LEFT JOIN moz_places prev_p ON prev_v.place_id = prev_p.id
    ORDER BY v.visit_date
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    visit_types = {
        1: "Link", 2: "Typed", 3: "Bookmark", 4: "Embed",
        5: "Redirect_Permanent", 6: "Redirect_Temporary",
        7: "Download", 8: "Framed_Link", 9: "Reload"
    }
    
    rows = []
    for row in results:
        (timestamp_us, url, title, description, visit_type_id,
         session, visit_count, typed, frecency, hidden, rev_host,
         from_url, from_title) = row
        
        try:
            unix_microseconds, iso_datetime = convert_gecko_timestamp(timestamp_us)
        except TimestampValidationError:
            continue
        
        visit_type_name = visit_types.get(visit_type_id, f"Unknown({visit_type_id})")
        
        message = f"Visited: {title or '(No title)'}"
        if description:
            message += f" - {description}"
        
        # Build row with only useful fields
        row_data = {
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Visit Time',
            'message': message,
            'data_type': 'browser:page:visit',
            'browser': browser_name,
            'url': url or "",
            'title': title or "(No title)",
            'visit_type': visit_type_name,
            'total_visit_count': visit_count or 0,
            'typed_count': typed or 0,
            'frecency_score': frecency,
            'hidden': bool(hidden),
            'domain': rev_host[::-1] if rev_host else ""
        }
        
        # Add optional fields only if present
        if description:
            row_data['description'] = description
        
        # Add navigation chain info if present
        if from_url:
            row_data['from_url'] = from_url
            if from_title:
                row_data['from_title'] = from_title
        
        # Add session ID only if non-zero
        if session and session != 0:
            row_data['session_id'] = session
        
        rows.append(row_data)
    
    return rows


def extract_gecko_bookmarks(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract bookmark events from Gecko database."""
    if not table_exists(conn, 'moz_bookmarks'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        b.id,
        b.type,
        b.title,
        b.dateAdded,
        b.lastModified,
        p.url,
        p.title as page_title,
        b.parent,
        b.position
    FROM moz_bookmarks b
    LEFT JOIN moz_places p ON b.fk = p.id
    WHERE b.dateAdded IS NOT NULL
    ORDER BY b.dateAdded
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    bookmark_types = {
        1: "Bookmark",
        2: "Folder",
        3: "Separator"
    }
    
    rows = []
    for row in results:
        (bm_id, bm_type, title, date_added, last_modified,
         url, page_title, parent, position) = row
        
        try:
            added_us, added_iso = convert_gecko_timestamp(date_added)
        except TimestampValidationError:
            continue
        
        type_name = bookmark_types.get(bm_type, f"Unknown({bm_type})")
        display_title = title or page_title or "(No title)"
        
        # Bookmark added event
        rows.append({
            'timestamp': added_us,
            'datetime': added_iso,
            'timestamp_desc': 'Bookmark Added',
            'message': f"Bookmarked: {display_title}",
            'data_type': 'browser:bookmark:added',
            'browser': browser_name,
            'bookmark_id': bm_id,
            'bookmark_type': type_name,
            'bookmark_title': display_title,
            'url': url or "",
            'parent_folder_id': parent,
            'position': position
        })
        
        # Bookmark modified event (if different from added)
        if last_modified and last_modified != date_added:
            try:
                modified_us, modified_iso = convert_gecko_timestamp(last_modified)
                rows.append({
                    'timestamp': modified_us,
                    'datetime': modified_iso,
                    'timestamp_desc': 'Bookmark Modified',
                    'message': f"Modified bookmark: {display_title}",
                    'data_type': 'browser:bookmark:modified',
                    'browser': browser_name,
                    'bookmark_id': bm_id,
                    'bookmark_title': display_title,
                    'url': url or ""
                })
            except TimestampValidationError:
                pass
    
    return rows


def extract_gecko_downloads(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract downloads from Gecko database (older Firefox versions)."""
    if not table_exists(conn, 'moz_downloads'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        id,
        name,
        source,
        target,
        startTime,
        endTime,
        state,
        referrer,
        currBytes,
        maxBytes,
        mimeType
    FROM moz_downloads
    WHERE startTime IS NOT NULL
    ORDER BY startTime
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    download_states = {
        0: "Downloading",
        1: "Complete",
        2: "Failed",
        3: "Cancelled",
        4: "Paused"
    }
    
    rows = []
    for row in results:
        (dl_id, name, source, target, start_time, end_time, state,
         referrer, curr_bytes, max_bytes, mime_type) = row
        
        try:
            start_us, start_iso = convert_gecko_timestamp(start_time)
        except TimestampValidationError:
            continue
        
        state_name = download_states.get(state, f"Unknown({state})")
        
        # Download start event
        rows.append({
            'timestamp': start_us,
            'datetime': start_iso,
            'timestamp_desc': 'Download Started',
            'message': f"Download started: {name} ({mime_type or 'unknown type'})",
            'data_type': 'browser:download:start',
            'browser': browser_name,
            'download_id': dl_id,
            'filename': name or "",
            'source_url': source or "",
            'target_path': target or "",
            'file_size_bytes': max_bytes or 0,
            'mime_type': mime_type or "",
            'download_state': state_name,
            'referrer_url': referrer or ""
        })
        
        # Download complete event
        if end_time and end_time != start_time:
            try:
                end_us, end_iso = convert_gecko_timestamp(end_time)
                duration_seconds = (end_us - start_us) / 1000000
                rows.append({
                    'timestamp': end_us,
                    'datetime': end_iso,
                    'timestamp_desc': 'Download Completed',
                    'message': f"Download completed: {name} ({curr_bytes or 0} bytes in {duration_seconds:.1f}s)",
                    'data_type': 'browser:download:complete',
                    'browser': browser_name,
                    'download_id': dl_id,
                    'filename': name or "",
                    'file_size_bytes': curr_bytes or 0,
                    'mime_type': mime_type or "",
                    'download_state': state_name,
                    'download_duration_seconds': duration_seconds
                })
            except TimestampValidationError:
                pass
    
    return rows


def extract_gecko_form_history(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract form autofill history from Gecko database."""
    if not table_exists(conn, 'moz_formhistory'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        id,
        fieldname,
        value,
        timesUsed,
        firstUsed,
        lastUsed
    FROM moz_formhistory
    WHERE firstUsed IS NOT NULL
    ORDER BY firstUsed
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        form_id, fieldname, value, times_used, first_used, last_used = row
        
        # First use event
        if first_used:
            try:
                first_us, first_iso = convert_gecko_timestamp(first_used)
                rows.append({
                    'timestamp': first_us,
                    'datetime': first_iso,
                    'timestamp_desc': 'Form Field First Used',
                    'message': f"First use of form field: {fieldname}",
                    'data_type': 'browser:form:first_use',
                    'browser': browser_name,
                    'form_id': form_id,
                    'form_field_name': fieldname,
                    'form_field_value': value[:50] + '...' if len(value) > 50 else value,
                    'total_uses': times_used or 0
                })
            except TimestampValidationError:
                pass
        
        # Last use event (if different)
        if last_used and last_used != first_used:
            try:
                last_us, last_iso = convert_gecko_timestamp(last_used)
                rows.append({
                    'timestamp': last_us,
                    'datetime': last_iso,
                    'timestamp_desc': 'Form Field Last Used',
                    'message': f"Used form field: {fieldname}",
                    'data_type': 'browser:form:use',
                    'browser': browser_name,
                    'form_id': form_id,
                    'form_field_name': fieldname,
                    'form_field_value': value[:50] + '...' if len(value) > 50 else value,
                    'total_uses': times_used or 0
                })
            except TimestampValidationError:
                pass
    
    return rows


def extract_gecko_annotations(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract page and bookmark annotations from Gecko database."""
    rows = []
    
    # Page annotations
    if table_exists(conn, 'moz_annos'):
        cursor = conn.cursor()
        query = """
        SELECT 
            a.id,
            a.place_id,
            a.dateAdded,
            a.lastModified,
            n.name,
            a.content,
            p.url,
            p.title
        FROM moz_annos a
        JOIN moz_anno_attributes n ON a.anno_attribute_id = n.id
        JOIN moz_places p ON a.place_id = p.id
        WHERE a.dateAdded IS NOT NULL
        ORDER BY a.dateAdded
        """
        
        try:
            cursor.execute(query)
            results = cursor.fetchall()
            
            for row in results:
                anno_id, place_id, date_added, last_modified, name, content, url, title = row
                
                # Annotation added
                if date_added:
                    try:
                        added_us, added_iso = convert_gecko_timestamp(date_added)
                        rows.append({
                            'timestamp': added_us,
                            'datetime': added_iso,
                            'timestamp_desc': 'Page Annotation Added',
                            'message': f"Added annotation '{name}' to: {title or url}",
                            'data_type': 'browser:annotation:added',
                            'browser': browser_name,
                            'annotation_id': anno_id,
                            'annotation_name': name,
                            'annotation_content': content[:100] + '...' if content and len(content) > 100 else content,
                            'url': url or "",
                            'title': title or ""
                        })
                    except TimestampValidationError:
                        pass
                
                # Annotation modified (if different)
                if last_modified and last_modified != date_added:
                    try:
                        modified_us, modified_iso = convert_gecko_timestamp(last_modified)
                        rows.append({
                            'timestamp': modified_us,
                            'datetime': modified_iso,
                            'timestamp_desc': 'Page Annotation Modified',
                            'message': f"Modified annotation '{name}' on: {title or url}",
                            'data_type': 'browser:annotation:modified',
                            'browser': browser_name,
                            'annotation_id': anno_id,
                            'annotation_name': name,
                            'url': url or ""
                        })
                    except TimestampValidationError:
                        pass
        except sqlite3.Error:
            pass
    
    # Bookmark annotations
    if table_exists(conn, 'moz_items_annos'):
        cursor = conn.cursor()
        query = """
        SELECT 
            ia.id,
            ia.item_id,
            ia.dateAdded,
            ia.lastModified,
            n.name,
            ia.content,
            b.title
        FROM moz_items_annos ia
        JOIN moz_anno_attributes n ON ia.anno_attribute_id = n.id
        JOIN moz_bookmarks b ON ia.item_id = b.id
        WHERE ia.dateAdded IS NOT NULL
        ORDER BY ia.dateAdded
        """
        
        try:
            cursor.execute(query)
            results = cursor.fetchall()
            
            for row in results:
                anno_id, item_id, date_added, last_modified, name, content, title = row
                
                # Annotation added
                if date_added:
                    try:
                        added_us, added_iso = convert_gecko_timestamp(date_added)
                        rows.append({
                            'timestamp': added_us,
                            'datetime': added_iso,
                            'timestamp_desc': 'Bookmark Annotation Added',
                            'message': f"Added annotation '{name}' to bookmark: {title}",
                            'data_type': 'browser:annotation:added',
                            'browser': browser_name,
                            'annotation_id': anno_id,
                            'annotation_name': name,
                            'annotation_content': content[:100] + '...' if content and len(content) > 100 else content,
                            'bookmark_title': title or ""
                        })
                    except TimestampValidationError:
                        pass
                
                # Annotation modified (if different)
                if last_modified and last_modified != date_added:
                    try:
                        modified_us, modified_iso = convert_gecko_timestamp(last_modified)
                        rows.append({
                            'timestamp': modified_us,
                            'datetime': modified_iso,
                            'timestamp_desc': 'Bookmark Annotation Modified',
                            'message': f"Modified annotation '{name}' on bookmark: {title}",
                            'data_type': 'browser:annotation:modified',
                            'browser': browser_name,
                            'annotation_id': anno_id,
                            'annotation_name': name
                        })
                    except TimestampValidationError:
                        pass
        except sqlite3.Error:
            pass
    
    return rows


def extract_gecko_metadata(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract page metadata/engagement events from Gecko database."""
    if not table_exists(conn, 'moz_places_metadata'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        m.place_id,
        m.created_at,
        m.updated_at,
        m.total_view_time,
        m.typing_time,
        m.key_presses,
        m.scrolling_time,
        m.scrolling_distance,
        m.document_type,
        p.url,
        p.title
    FROM moz_places_metadata m
    JOIN moz_places p ON m.place_id = p.id
    WHERE m.created_at > 0
    ORDER BY m.created_at
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        (place_id, created_at, updated_at, total_view_time, typing_time,
         key_presses, scrolling_time, scrolling_distance, document_type,
         url, title) = row
        
        try:
            created_us, created_iso = convert_gecko_timestamp(created_at)
        except TimestampValidationError:
            continue
        
        # Convert microseconds to seconds for display
        view_seconds = (total_view_time or 0) / 1000000
        typing_seconds = (typing_time or 0) / 1000000
        scrolling_seconds = (scrolling_time or 0) / 1000000
        
        rows.append({
            'timestamp': created_us,
            'datetime': created_iso,
            'timestamp_desc': 'Page Engagement',
            'message': f"Engaged with: {title or '(No title)'} ({view_seconds:.1f}s)",
            'data_type': 'browser:page:engagement',
            'browser': browser_name,
            'url': url or "",
            'title': title or "(No title)",
            'total_view_time_seconds': view_seconds,
            'typing_time_seconds': typing_seconds,
            'key_presses': key_presses or 0,
            'scrolling_time_seconds': scrolling_seconds,
            'scrolling_distance': scrolling_distance or 0,
            'document_type': document_type
        })
    
    return rows


def extract_gecko_input_history(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract address bar input history from Gecko database."""
    if not table_exists(conn, 'moz_inputhistory'):
        return []
    
    cursor = conn.cursor()
    
    query = """
    SELECT 
        ih.place_id,
        ih.input,
        ih.use_count,
        p.url,
        p.title,
        p.last_visit_date
    FROM moz_inputhistory ih
    JOIN moz_places p ON ih.place_id = p.id
    WHERE p.last_visit_date IS NOT NULL
    ORDER BY p.last_visit_date
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        place_id, input_text, use_count, url, title, last_visit = row
        
        try:
            unix_microseconds, iso_datetime = convert_gecko_timestamp(last_visit)
        except TimestampValidationError:
            continue
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Address Bar Input',
            'message': f"Typed in address bar: {input_text}",
            'data_type': 'browser:addressbar:input',
            'browser': browser_name,
            'input_text': input_text or "",
            'matched_url': url or "",
            'matched_title': title or "",
            'use_count': use_count or 0
        })
    
    return rows


def extract_gecko_keywords(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract custom search keywords from Gecko database."""
    if not table_exists(conn, 'moz_keywords'):
        return []
    
    cursor = conn.cursor()
    
    # Check if dateAdded column exists (not in all Firefox versions)
    if not column_exists(conn, 'moz_keywords', 'dateAdded'):
        return []
    
    query = """
    SELECT 
        k.id,
        k.keyword,
        k.dateAdded,
        p.url,
        p.title
    FROM moz_keywords k
    LEFT JOIN moz_places p ON k.place_id = p.id
    WHERE k.dateAdded IS NOT NULL
    ORDER BY k.dateAdded
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        keyword_id, keyword, date_added, url, title = row
        
        try:
            added_us, added_iso = convert_gecko_timestamp(date_added)
        except TimestampValidationError:
            continue
        
        rows.append({
            'timestamp': added_us,
            'datetime': added_iso,
            'timestamp_desc': 'Keyword Added',
            'message': f"Added search keyword: {keyword}",
            'data_type': 'browser:keyword:added',
            'browser': browser_name,
            'keyword_id': keyword_id,
            'keyword': keyword or "",
            'search_url': url or "",
            'title': title or ""
        })
    
    return rows


def extract_gecko_origins(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract origin (domain) tracking data from Gecko database."""
    if not table_exists(conn, 'moz_origins'):
        return []
    
    cursor = conn.cursor()
    
    # Check for last_visit_date column
    if not column_exists(conn, 'moz_origins', 'last_visit_date'):
        return []
    
    query = """
    SELECT 
        id,
        prefix,
        host,
        frecency,
        last_visit_date
    FROM moz_origins
    WHERE last_visit_date IS NOT NULL
    ORDER BY last_visit_date
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        origin_id, prefix, host, frecency, last_visit = row
        
        try:
            unix_microseconds, iso_datetime = convert_gecko_timestamp(last_visit)
        except TimestampValidationError:
            continue
        
        full_origin = f"{prefix}{host}" if prefix else host
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Domain Visited',
            'message': f"Visited domain: {full_origin}",
            'data_type': 'browser:domain:visit',
            'browser': browser_name,
            'origin': full_origin or "",
            'host': host or "",
            'prefix': prefix or "",
            'frecency_score': frecency or 0
        })
    
    return rows


# ============================================================================
# WEBKIT/SAFARI EXTRACTORS
# ============================================================================

def extract_webkit_visits(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract visit events from WebKit database with resolved redirect chains."""
    cursor = conn.cursor()
    
    query = """
    SELECT 
        hv.visit_time,
        hi.url,
        hi.title,
        hv.title as visit_title,
        hv.load_successful,
        hv.http_non_get,
        hi.visit_count,
        redirect_src_items.url as redirect_source_url,
        redirect_dst_items.url as redirect_destination_url
    FROM history_visits hv
    JOIN history_items hi ON hv.history_item = hi.id
    LEFT JOIN history_visits redirect_src ON hv.redirect_source = redirect_src.id
    LEFT JOIN history_items redirect_src_items ON redirect_src.history_item = redirect_src_items.id
    LEFT JOIN history_visits redirect_dst ON hv.redirect_destination = redirect_dst.id
    LEFT JOIN history_items redirect_dst_items ON redirect_dst.history_item = redirect_dst_items.id
    ORDER BY hv.visit_time
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    rows = []
    for row in results:
        (webkit_timestamp, url, title, visit_title,
         load_successful, http_non_get, visit_count,
         redirect_source_url, redirect_destination_url) = row
        
        try:
            unix_microseconds, iso_datetime = convert_webkit_timestamp(webkit_timestamp)
        except TimestampValidationError:
            continue
        
        display_title = title or visit_title or "(No title)"
        
        message = f"Visited: {display_title}"
        if not load_successful:
            message += " [FAILED TO LOAD]"
        if http_non_get:
            message += " [POST/Form]"
        
        # Build row with only useful fields
        row_data = {
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Visit Time',
            'message': message,
            'data_type': 'browser:page:visit',
            'browser': browser_name,
            'url': url or "",
            'title': display_title,
            'load_successful': bool(load_successful),
            'http_post': bool(http_non_get),
            'total_visit_count': visit_count or 0
        }
        
        # Add redirect chain info if present
        if redirect_source_url:
            row_data['redirect_source_url'] = redirect_source_url
        if redirect_destination_url:
            row_data['redirect_destination_url'] = redirect_destination_url
        
        rows.append(row_data)
    
    return rows


def extract_webkit_bookmarks(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract bookmarks from WebKit database."""
    if not table_exists(conn, 'bookmarks'):
        return []
    
    cursor = conn.cursor()
    
    # Check for date_added column
    if not column_exists(conn, 'bookmarks', 'date_added'):
        return []
    
    query = """
    SELECT 
        id,
        title,
        url,
        date_added,
        date_last_modified
    FROM bookmarks
    WHERE date_added > 0
    ORDER BY date_added
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        bm_id, title, url, date_added, date_modified = row
        
        # Bookmark added
        if date_added:
            try:
                added_us, added_iso = convert_webkit_timestamp(date_added)
                rows.append({
                    'timestamp': added_us,
                    'datetime': added_iso,
                    'timestamp_desc': 'Bookmark Added',
                    'message': f"Bookmarked: {title or url}",
                    'data_type': 'browser:bookmark:added',
                    'browser': browser_name,
                    'bookmark_id': bm_id,
                    'bookmark_title': title or "",
                    'url': url or ""
                })
            except TimestampValidationError:
                pass
        
        # Bookmark modified (if different)
        if date_modified and date_modified != date_added:
            try:
                modified_us, modified_iso = convert_webkit_timestamp(date_modified)
                rows.append({
                    'timestamp': modified_us,
                    'datetime': modified_iso,
                    'timestamp_desc': 'Bookmark Modified',
                    'message': f"Modified bookmark: {title or url}",
                    'data_type': 'browser:bookmark:modified',
                    'browser': browser_name,
                    'bookmark_id': bm_id,
                    'bookmark_title': title or "",
                    'url': url or ""
                })
            except TimestampValidationError:
                pass
    
    return rows


def extract_webkit_downloads(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract downloads from WebKit database."""
    if not table_exists(conn, 'downloads'):
        return []
    
    cursor = conn.cursor()
    
    # Check for date_started column
    if not column_exists(conn, 'downloads', 'date_started'):
        return []
    
    query = """
    SELECT 
        id,
        url,
        path,
        mime_type,
        bytes_received,
        total_bytes,
        date_started,
        date_finished
    FROM downloads
    WHERE date_started > 0
    ORDER BY date_started
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        dl_id, url, path, mime_type, bytes_received, total_bytes, date_started, date_finished = row
        
        filename = Path(path).name if path else "(unknown)"
        
        # Download started
        if date_started:
            try:
                started_us, started_iso = convert_webkit_timestamp(date_started)
                rows.append({
                    'timestamp': started_us,
                    'datetime': started_iso,
                    'timestamp_desc': 'Download Started',
                    'message': f"Download started: {filename} ({mime_type or 'unknown type'})",
                    'data_type': 'browser:download:start',
                    'browser': browser_name,
                    'download_id': dl_id,
                    'filename': filename,
                    'source_url': url or "",
                    'file_path': path or "",
                    'file_size_bytes': total_bytes or 0,
                    'mime_type': mime_type or ""
                })
            except TimestampValidationError:
                pass
        
        # Download finished (if different)
        if date_finished and date_finished != date_started:
            try:
                finished_us, finished_iso = convert_webkit_timestamp(date_finished)
                duration_seconds = (finished_us - started_us) / 1000000 if date_started else 0
                rows.append({
                    'timestamp': finished_us,
                    'datetime': finished_iso,
                    'timestamp_desc': 'Download Completed',
                    'message': f"Download completed: {filename} ({bytes_received or 0} bytes in {duration_seconds:.1f}s)",
                    'data_type': 'browser:download:complete',
                    'browser': browser_name,
                    'download_id': dl_id,
                    'filename': filename,
                    'file_path': path or "",
                    'file_size_bytes': bytes_received or 0,
                    'mime_type': mime_type or "",
                    'download_duration_seconds': duration_seconds
                })
            except TimestampValidationError:
                pass
    
    return rows


def extract_webkit_reading_list(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract Reading List items from WebKit database."""
    if not table_exists(conn, 'reading_list'):
        return []
    
    cursor = conn.cursor()
    
    # Check for date_added column
    if not column_exists(conn, 'reading_list', 'date_added'):
        return []
    
    query = """
    SELECT 
        id,
        title,
        url,
        date_added,
        date_last_viewed
    FROM reading_list
    WHERE date_added > 0
    ORDER BY date_added
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        item_id, title, url, date_added, date_viewed = row
        
        # Reading list item added
        if date_added:
            try:
                added_us, added_iso = convert_webkit_timestamp(date_added)
                rows.append({
                    'timestamp': added_us,
                    'datetime': added_iso,
                    'timestamp_desc': 'Reading List Item Added',
                    'message': f"Added to Reading List: {title or url}",
                    'data_type': 'browser:readinglist:added',
                    'browser': browser_name,
                    'reading_list_id': item_id,
                    'title': title or "",
                    'url': url or ""
                })
            except TimestampValidationError:
                pass
        
        # Reading list item viewed (if present)
        if date_viewed and date_viewed > 0:
            try:
                viewed_us, viewed_iso = convert_webkit_timestamp(date_viewed)
                rows.append({
                    'timestamp': viewed_us,
                    'datetime': viewed_iso,
                    'timestamp_desc': 'Reading List Item Viewed',
                    'message': f"Viewed Reading List item: {title or url}",
                    'data_type': 'browser:readinglist:viewed',
                    'browser': browser_name,
                    'reading_list_id': item_id,
                    'title': title or "",
                    'url': url or ""
                })
            except TimestampValidationError:
                pass
    
    return rows


def extract_webkit_top_sites(conn: sqlite3.Connection, browser_name: str) -> List[Dict[str, Any]]:
    """Extract Top Sites data from WebKit database."""
    if not table_exists(conn, 'top_sites'):
        return []
    
    cursor = conn.cursor()
    
    # Check for last_visited column
    if not column_exists(conn, 'top_sites', 'last_visited'):
        return []
    
    query = """
    SELECT 
        id,
        url,
        title,
        visit_count,
        last_visited
    FROM top_sites
    WHERE last_visited > 0
    ORDER BY last_visited
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error:
        return []
    
    rows = []
    for row in results:
        site_id, url, title, visit_count, last_visited = row
        
        try:
            unix_microseconds, iso_datetime = convert_webkit_timestamp(last_visited)
        except TimestampValidationError:
            continue
        
        rows.append({
            'timestamp': unix_microseconds,
            'datetime': iso_datetime,
            'timestamp_desc': 'Top Site Last Visited',
            'message': f"Top site visited: {title or url}",
            'data_type': 'browser:topsite:visit',
            'browser': browser_name,
            'site_id': site_id,
            'url': url or "",
            'title': title or "",
            'visit_count': visit_count or 0
        })
    
    return rows


# ============================================================================
# MAIN EXTRACTION ORCHESTRATION
# ============================================================================

def extract_all_events(db_path: str, browser_type: str, browser_name: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Extract ALL timeline events from browser database.
    
    Returns:
        Tuple of (all_rows, event_counts dictionary)
    """
    if browser_name is None:
        browser_name = {'gecko': 'Firefox', 'chromium': 'Chromium', 'webkit': 'Safari'}[browser_type]
    
    conn = connect_database_readonly(db_path)
    all_rows = []
    event_counts = {}
    
    print(f"Extracting events from {browser_name} database...")
    print("=" * 60)
    
    try:
        if browser_type == 'gecko':
            # Firefox/Gecko - extract all event types
            extractors = [
                ('Page Visits', extract_gecko_visits),
                ('Bookmarks', extract_gecko_bookmarks),
                ('Downloads', extract_gecko_downloads),
                ('Form History', extract_gecko_form_history),
                ('Annotations', extract_gecko_annotations),
                ('Page Engagement', extract_gecko_metadata),
                ('Address Bar Input', extract_gecko_input_history),
                ('Search Keywords', extract_gecko_keywords),
                ('Domain Tracking', extract_gecko_origins),
            ]
            
        elif browser_type == 'chromium':
            # Chromium - extract all event types
            extractors = [
                ('Page Visits', extract_chromium_visits),
                ('Downloads', extract_chromium_downloads),
                ('Search Queries', extract_chromium_search_terms),
                ('Form Autofill', extract_chromium_autofill),
                ('Favicons', extract_chromium_favicons),
                ('Media Playback', extract_chromium_media_history),
                ('Site Engagement', extract_chromium_site_engagement),
            ]
            
        elif browser_type == 'webkit':
            # Safari/WebKit - extract all event types
            extractors = [
                ('Page Visits', extract_webkit_visits),
                ('Bookmarks', extract_webkit_bookmarks),
                ('Downloads', extract_webkit_downloads),
                ('Reading List', extract_webkit_reading_list),
                ('Top Sites', extract_webkit_top_sites),
            ]
        
        # Run all extractors
        for name, extractor_func in extractors:
            try:
                events = extractor_func(conn, browser_name)
                all_rows.extend(events)
                event_counts[name] = len(events)
                print(f"  ✓ {name:25} {len(events):>7,} events")
            except Exception as e:
                print(f"  ✗ {name:25} Error: {e}")
                event_counts[name] = 0
        
    finally:
        conn.close()
    
    # Sort all events by timestamp
    all_rows.sort(key=lambda x: x['timestamp'])
    
    print("=" * 60)
    
    return all_rows, event_counts


def generate_default_output_filename(browser_type: str, input_path: str) -> str:
    """Generate a sensible default output filename based on browser type and input."""
    path_lower = input_path.lower()
    
    browser_names = {
        'firefox': 'firefox', 'chrome': 'chrome', 'edge': 'edge',
        'brave': 'brave', 'opera': 'opera', 'vivaldi': 'vivaldi', 'safari': 'safari',
    }
    
    detected_name = None
    for name_key, name_value in browser_names.items():
        if name_key in path_lower:
            detected_name = name_value
            break
    
    if detected_name:
        return f"{detected_name}_timeline_timesketch.csv"
    else:
        return f"{browser_type}_timeline_timesketch.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Convert ALL browser events to Timesketch CSV format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts ALL timestamped events from browser databases:
  
CHROMIUM (Chrome, Edge, Brave, Opera, Vivaldi):
  - Page visits (with metadata and navigation chains)
  - Downloads (start, completion, access times)
  - Search queries
  - Form autofill data (first use, last use)
  - Favicon updates
  - Media playback history
  - Site engagement scores

GECKO/FIREFOX:
  - Page visits (with metadata and navigation chains)
  - Bookmarks (added, modified)
  - Downloads
  - Form history (first use, last use)
  - Page and bookmark annotations
  - Page engagement metrics (view time, scrolling, typing)
  - Address bar input history
  - Custom search keywords
  - Domain-level tracking data

WEBKIT/SAFARI:
  - Page visits (with redirect chains)
  - Bookmarks (added, modified)
  - Downloads (start, completion)
  - Reading List items (added, viewed)
  - Top Sites tracking

Browser types:
  gecko, firefox      - Gecko-based browsers (Firefox)
  chromium            - Chromium-based browsers (Chrome, Edge, Brave, etc.)
  webkit, safari      - WebKit-based browsers (Safari)
  auto                - Auto-detect browser type (default)

Output Format:
  - Browser-agnostic Timesketch-compatible CSV
  - Consistent event naming across all browsers
  - All timestamps in Unix microseconds + ISO 8601

Example usage:
  # Auto-detect and extract everything
  python browser2timesketch_complete.py -i /path/to/History
  
  # Specify browser and output
  python browser2timesketch_complete.py -b firefox -i places.sqlite -o output.csv
  
  # Custom browser name (e.g., for Brave, Edge)
  python browser2timesketch_complete.py --browser-name "Brave" -i History
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
        help='Output CSV file path (default: auto-generated)'
    )
    
    parser.add_argument(
        '--browser-name',
        help='Custom browser name for the browser field (e.g., "Brave", "Edge")'
    )
    
    args = parser.parse_args()
    
    try:
        # Validate database file
        print(f"Validating database: {args.input}")
        validate_sqlite_database(args.input)
        print("✓ Database is valid SQLite file\n")
        
        # Detect or validate browser type
        browser_type = args.browser.lower()
        
        if browser_type == 'auto':
            print("Auto-detecting browser type...")
            browser_type = detect_browser_type(args.input)
            print(f"✓ Detected browser type: {browser_type}\n")
        else:
            if browser_type == 'firefox':
                browser_type = 'gecko'
            elif browser_type == 'safari':
                browser_type = 'webkit'
            
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
            print(f"Using output filename: {output_csv}\n")
        
        # Extract all events
        all_rows, event_counts = extract_all_events(args.input, browser_type, args.browser_name)
        
        if not all_rows:
            print("\n❌ No events found in database!")
            return 1
        
        # Write to CSV
        print(f"\nWriting {len(all_rows):,} total events to CSV...")
        write_timesketch_csv(output_csv, all_rows)
        
        # Summary
        print("\n" + "=" * 60)
        print("EXTRACTION COMPLETE")
        print("=" * 60)
        print(f"Total events:  {len(all_rows):,}")
        print("\nEvent breakdown:")
        for event_type, count in sorted(event_counts.items()):
            if count > 0:
                print(f"  • {event_type:25} {count:>7,} events")
        print(f"\n✓ Output saved to: {output_csv}")
        print(f"✓ Format: Browser-agnostic Timesketch CSV")
        print("=" * 60)
        
        return 0
        
    except DatabaseValidationError as e:
        print(f"\n❌ Database Validation Error: {e}", file=sys.stderr)
        return 1
    except BrowserDetectionError as e:
        print(f"\n❌ Browser Detection Error: {e}", file=sys.stderr)
        return 1
    except sqlite3.Error as e:
        print(f"\n❌ Database Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())