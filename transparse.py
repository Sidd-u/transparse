#!/usr/bin/env python3
"""
transparse — LIC Sub-Ledger TXT Parser
Extracts and reformats transaction data from LIC fixed-width pipe-table reports.
"""

import re
import mmap
import argparse
import sys
import os
import time
import multiprocessing
from pathlib import Path


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

# Regex: Line 1 of a transaction block
# Matches: | <digits> | <date DD/MM/YYYY> | ...
LINE1_RE = re.compile(
    r'^\s*\|\s*(\d+)\s*\|\s*(\d{2}/\d{2}/\d{4})\s*\|'
)

# Regex: Line 2 — Name + Sr/Ag/Pol No
LINE2_RE = re.compile(
    r'\|\s*Name\s*:(.+?)Sr/Ag/Pol No\s*:\s*(\S+)\s*\|',
    re.IGNORECASE
)

# Regex: Page No in header (for incrementing)
PAGENO_RE = re.compile(r'(Page No\s*:)\s*(\d+)', re.IGNORECASE)

# Encoding fallback chain
ENCODINGS = ['utf-8', 'cp1252', 'latin-1']

# Block structure:
# Line 1 → transaction data  (tran_no, date, debit, credit)
# Line 2 → Name + Pol No
# Line 3 → SSS description / reason text
# Line 4 → Remarks/status  ← THIS is what user calls "remarks" (m c paid, fully paid up, S V PAID)
# Line 5 → NEFT details
BLOCK_SIZE = 5


# ─────────────────────────────────────────────
# FILE READING
# ─────────────────────────────────────────────

def detect_encoding(raw: bytes) -> str:
    for enc in ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return 'latin-1'


def read_file(filepath: str) -> list:
    """Read file using mmap, detect encoding, return clean lines."""
    # FIX 1: handle empty file — mmap crashes on 0-byte files
    if os.path.getsize(filepath) == 0:
        return []
    with open(filepath, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        raw = bytes(mm)
        mm.close()
    enc = detect_encoding(raw)
    text = raw.decode(enc, errors='replace')
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.splitlines()


# ─────────────────────────────────────────────
# HEADER EXTRACTION
# ─────────────────────────────────────────────

def extract_header(lines: list) -> tuple:
    """
    Split lines into:
      - header_block : lines before the first separator (title, office code, etc.)
      - data_lines   : lines after the second separator
      - col_map      : {col_name: (start, end)} built from header pipe positions
    """
    sep_count = 0
    header_block = []
    col_header_line = None
    data_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('=') and stripped.endswith('=') and len(stripped) > 10:
            sep_count += 1
            if sep_count == 2:
                data_start = i + 1
                break
        elif sep_count == 1 and col_header_line is None and '|' in line and 'Tran' in line:
            col_header_line = line
            # Do NOT add to header_block — replaced with our own 5-col header
        elif sep_count == 0:
            header_block.append(line)

    # FIX 2: if no second separator found, data_start stays 0
    # return empty data_lines instead of returning all lines as data
    if sep_count < 2:
        data_lines = []
    else:
        data_lines = lines[data_start:]

    # Build column map from header pipe positions
    col_map = {}
    if col_header_line:
        pipes = [i for i, c in enumerate(col_header_line) if c == '|']
        col_names_raw = []
        for i in range(len(pipes) - 1):
            name = col_header_line[pipes[i]+1:pipes[i+1]].strip().lower()
            col_names_raw.append((name, pipes[i], pipes[i+1]))

        for name, s, e in col_names_raw:
            if 'tran' in name and 'no' in name:
                col_map['tran_no'] = (s+1, e)
            elif 'tran' in name and 'date' in name:
                col_map['tran_date'] = (s+1, e)
            elif 'debit' in name:
                col_map['debit'] = (s+1, e)
            elif 'credit' in name:
                col_map['credit'] = (s+1, e)

    return header_block, data_lines, col_map


# ─────────────────────────────────────────────
# TRANSACTION PARSER (runs per chunk in worker)
# ─────────────────────────────────────────────

def parse_chunk(args):
    """
    Parse a chunk of lines into transaction dicts.
    Returns list of dicts with keys:
      tran_no (int), tran_date, pol_no, remarks, debit (float)
    """
    lines, col_map = args
    transactions = []
    current = None

    for raw_line in lines:
        m1 = LINE1_RE.match(raw_line)
        if m1:
            # Save previous block before starting new one
            if current:
                t = finalize_block(current, col_map)
                if t:
                    transactions.append(t)
            current = {'lines': [raw_line], 'count': 1}
            continue

        if current is not None:
            current['lines'].append(raw_line)
            current['count'] += 1
            if current['count'] >= BLOCK_SIZE:
                t = finalize_block(current, col_map)
                if t:
                    transactions.append(t)
                current = None

    # FIX 3: flush last block even if it has fewer than BLOCK_SIZE lines
    # (last block in file or chunk may be incomplete)
    if current and current['count'] >= 2:
        t = finalize_block(current, col_map)
        if t:
            transactions.append(t)

    return transactions


def finalize_block(block: dict, col_map: dict):
    """Extract fields from a transaction block. Returns dict or None."""
    lines = block['lines']
    if not lines:
        return None

    l1 = lines[0]

    # Extract Tran No
    try:
        s, e = col_map.get('tran_no', (16, 25))
        tran_no = int(l1[s:e].strip())
    except (ValueError, IndexError):
        return None

    # Extract Tran Date
    try:
        s, e = col_map.get('tran_date', (26, 38))
        tran_date = l1[s:e].strip()
    except IndexError:
        tran_date = ''

    # Extract Debit
    try:
        s, e = col_map.get('debit', (91, 107))
        debit = float(l1[s:e].strip())
    except (ValueError, IndexError):
        return None

    # Filter: skip entire row if debit is 0.00
    if debit == 0.0:
        return None

    # Extract Pol No from Line 2
    pol_no = ''
    if len(lines) > 1:
        m2 = LINE2_RE.search(lines[1])
        if m2:
            pol_no = m2.group(2).strip()

    # Extract Remarks from Line 4 (m c paid / fully paid up / S V PAID etc.)
    # Line index 3 = 4th line of block (0-indexed)
    remarks = ''
    if len(lines) > 3:
        inner = lines[3].strip()
        if inner.startswith('|'):
            inner = inner[1:]
        if inner.endswith('|'):
            inner = inner[:-1]
        remarks = inner.strip()

    return {
        'tran_no':   tran_no,
        'tran_date': tran_date,
        'pol_no':    pol_no,
        'remarks':   remarks,
        'debit':     debit,
    }


# ─────────────────────────────────────────────
# PARALLEL PROCESSING
# ─────────────────────────────────────────────

def split_chunks(lines: list, n_workers: int) -> list:
    """Split lines into n_workers chunks. Never splits mid-block."""
    total = len(lines)
    if total == 0:
        return []
    chunk_size = max(total // n_workers, 100)
    chunks = []
    i = 0
    while i < total:
        end = min(i + chunk_size, total)
        # Snap end to next Line1 boundary to avoid splitting a block
        if end < total:
            lookahead = end
            while lookahead < total and not LINE1_RE.match(lines[lookahead]):
                lookahead += 1
            end = lookahead
        chunks.append(lines[i:end])
        i = end
    return chunks


def parse_all(data_lines: list, col_map: dict) -> list:
    """Parse all data lines using multiprocessing."""
    n_workers = max(1, multiprocessing.cpu_count())
    chunks = split_chunks(data_lines, n_workers)

    if not chunks:
        return []

    args = [(chunk, col_map) for chunk in chunks]

    with multiprocessing.Pool(processes=n_workers) as pool:
        results = pool.map(parse_chunk, args)

    all_transactions = []
    for batch in results:
        all_transactions.extend(batch)

    return all_transactions


# ─────────────────────────────────────────────
# OUTPUT FORMATTING
# ─────────────────────────────────────────────

# Output column widths (characters inside pipes)
COL_WIDTHS = {
    'tran_no':   9,
    'tran_date': 12,
    'pol_no':    14,
    'remarks':   20,
    'debit':     16,
}

def make_separator() -> str:
    total = sum(COL_WIDTHS.values()) + len(COL_WIDTHS) + 1
    return '               ' + '=' * (total+10)

def make_col_header() -> str:
    return ('               '
            '| {:<{}} | {:<{}} | {:<{}} | {:<{}} | {:<{}} |'.format(
                'Tran No',      COL_WIDTHS['tran_no'],
                'Tran Date',    COL_WIDTHS['tran_date'],
                'Sr/Ag/Pol No', COL_WIDTHS['pol_no'],
                'Remarks',      COL_WIDTHS['remarks'],
                'Debit',        COL_WIDTHS['debit'],
            ))

def make_data_row(t: dict) -> str:
    debit_str = f"{t['debit']:.2f}"
    remarks = t['remarks'][:COL_WIDTHS['remarks']]
    return ('               '
            '| {:<{}} | {:<{}} | {:<{}} | {:<{}} | {:<{}} |'.format(
                str(t['tran_no']), COL_WIDTHS['tran_no'],
                t['tran_date'],    COL_WIDTHS['tran_date'],
                t['pol_no'],       COL_WIDTHS['pol_no'],
                remarks,           COL_WIDTHS['remarks'],
                debit_str,         COL_WIDTHS['debit'],
            ))

def make_page_header(header_block: list, page_no: int) -> list:
    """Return header block lines with Page No replaced by page_no."""
    result = []
    for line in header_block:
        if PAGENO_RE.search(line):
            line = PAGENO_RE.sub(lambda m: m.group(1) + str(page_no), line)
        result.append(line)
    return result


# ─────────────────────────────────────────────
# WRITER
# ─────────────────────────────────────────────

def write_output(out_path: str, header_block: list,
                 transactions: list, lines_per_page: int):
    sep = make_separator()
    col_hdr = make_col_header()
    page_no = 1
    count = 0

    with open(out_path, 'w', encoding='utf-8') as f:

        def write_page_header():
            for line in make_page_header(header_block, page_no):
                f.write(line + '\n')
            f.write(sep + '\n')
            f.write(col_hdr + '\n')
            f.write(sep + '\n')

        write_page_header()

        for t in transactions:
            if count > 0 and count % lines_per_page == 0:
                page_no += 1
                f.write('\n')
                write_page_header()
            f.write(make_data_row(t) + '\n')
            count += 1


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='transparse',
        description='LIC Sub-Ledger TXT Parser — extracts and reformats transaction data.'
    )
    parser.add_argument('input', help='Path to input .txt file')
    parser.add_argument('--lines', type=int, default=30,
                        help='Transactions per page (default: 30)')
    args = parser.parse_args()

    input_path = args.input
    lines_per_page = args.lines

    if not os.path.isfile(input_path):
        print(f'ERROR: File not found: {input_path}')
        sys.exit(1)

    if lines_per_page < 1:
        print('ERROR: --lines must be at least 1')
        sys.exit(1)

    input_name = Path(input_path).stem
    desktop = Path.home() / 'Desktop'
    if not desktop.exists():
        desktop = Path.home()
    desktop.mkdir(parents=True, exist_ok=True)
    out_path = str(desktop / f'{input_name}_parsed.txt')

    print(f'transparse — processing: {input_path}')
    print(f'Lines per page         : {lines_per_page}')
    print()

    t0 = time.time()

    lines = read_file(input_path)

    if not lines:
        print('ERROR: Input file is empty.')
        sys.exit(1)

    header_block, data_lines, col_map = extract_header(lines)

    if not col_map:
        print('ERROR: Could not detect column positions from header row.')
        print('       Make sure the file contains the standard LIC pipe-table header.')
        sys.exit(1)

    all_transactions = parse_all(data_lines, col_map)
    total_found = len(all_transactions)

    if total_found == 0:
        print('WARNING: No valid transactions with non-zero Debit found.')
        print('         Output file will not be created.')
        sys.exit(0)

    all_transactions.sort(key=lambda t: t['tran_no'])

    write_output(out_path, header_block, all_transactions, lines_per_page)

    elapsed = time.time() - t0
    pages = (total_found + lines_per_page - 1) // lines_per_page

    print(f'Transactions found     : {total_found}')
    print(f'Pages written          : {pages}')
    print(f'Processing time        : {elapsed:.2f}s')
    print(f'Output saved to        : {out_path}')


if __name__ == '__main__':
    main()