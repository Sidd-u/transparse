# transparse

A fast, lightweight CLI tool for parsing Sub-Ledger `.txt` reports.
Extracts key transaction fields, filters zero-debit entries, sorts by transaction number, and outputs a clean paginated pipe-table report — saved directly to your Desktop.

---

## Installation

Open your terminal and run:

```sh
for curl:
sh <(curl -fsSL https://raw.githubusercontent.com/Sidd-u/transparse/main/install.sh)

for wget:
sh <(wget -qO- https://raw.githubusercontent.com/Sidd-u/transparse/main/install.sh)
```

The installer will:
- Check if Python 3 is installed — installs it automatically if not
- Download `transparse` from GitHub
- Place it in `/usr/local/bin` so it works from anywhere
- Confirm the tool is ready to use

After installation, the `install.sh` file is no longer needed.

---

## Usage

```sh
transparse /path/to/file.txt
```

With custom page size:

```sh
transparse /path/to/file.txt --lines 50
```

| Argument | Description |
|----------|-------------|
| `file.txt` | Path to the input LIC sub-ledger `.txt` file |
| `--lines N` | Transactions per page in the output (default: 30) |

---

## Output

The output file is saved automatically to your **Desktop** as:

```
filename_parsed.txt
```

For example, if your input is `ledger_may2026.txt`, the output will be:

```
~/Desktop/ledger_may2026_parsed.txt
```

---

## What the Parser Does

### Input
A `.txt` file exported from the LIC Sub-Ledger system — a fixed-width pipe-table report that looks like this:

```
                                        LIFE INSURANCE CORPORATION OF INDIA
 Office Code :69J                                           Sub Ledger as on: 25-05-2026
 A/C Code : 11126500  Deposit SSS - Government Schemes     Page No:1
 ==========================================================================================
 | Tran no |  Tran Date | Dept|Book Code|Voucher No.| Chq No. |Voucher Date | Debit | Credit |
 ==========================================================================================
 |     2414| 29/04/2025 |   SS|    D    |      1041 |       0 |  30/04/2025 |  243.00|   0.00|
 |      Name : YANDAVA.VIJAYA KUMARI          Sr/Ag/Pol No :  692371580 |             |
 |                    SSS Deposit Refund for Policy number :692371580                   |
 |                                                              m c paid                |
 | for NEFT-SBIN0021256-62315439393    -YANDAVA.VIJAYA KUMARI                           |
```

Each transaction spans **5 lines** in the input.

### What Gets Extracted

From each transaction block, the parser reads:

| Field | Source | Rule |
|-------|--------|------|
| Tran No | Line 1 | Always included |
| Tran Date | Line 1 | Always included |
| Sr/Ag/Pol No | Line 2 | Always included |
| Remarks | Line 4 | Status text: `m c paid`, `fully paid up`, `S V PAID` etc. |
| Debit | Line 1 | **Row skipped if Debit = 0.00** |

### What the Output Looks Like

```
                                        LIFE INSURANCE CORPORATION OF INDIA
 Office Code :69J                                           Sub Ledger as on: 25-05-2026
 A/C Code : 11126500  Deposit SSS - Government Schemes     Page No:1
 ================================================================
 | Tran No  | Tran Date    | Sr/Ag/Pol No   | Remarks              | Debit            |
 ================================================================
 | 2414      | 29/04/2025   | 692371580      | m c paid             | 243.00           |
 | 2415      | 29/04/2025   | 692372485      | m c paid             | 147.00           |
 ...
```

### Processing Pipeline

```
Read file (mmap)
    │
    ├── Detect encoding (utf-8 → cp1252 → latin-1)
    ├── Normalize line endings (\r\n → \n)
    ├── Extract header block
    ├── Detect column positions dynamically from header row
    │
    └── Split into chunks (one per CPU core)
              │
              ├── Worker 1 → parse transactions
              ├── Worker 2 → parse transactions
              └── Worker N → parse transactions
                        │
                        └── Merge → Filter (Debit=0) → Sort by Tran No → Paginate → Write
```

### Key Behaviors

- **Debit = 0.00** → entire transaction row is skipped
- **Sorted ascending** by Transaction Number in output
- **Page header repeats** every N transactions with incrementing Page No
- **Column widths adapt** dynamically — works even if input line widths vary between files
- **Encoding auto-detected** — handles files saved from different systems
- **Large files supported** — uses memory mapping and parallel processing, safe for 6.5M+ character files

---

## Requirements

- Linux
- Python 3.8 or higher (auto-installed if missing)

---

## Project Structure

```
transparse/
├── transparse.py       ← the parser tool
├── install.sh          ← one-command installer
└── README.md           ← this file
```

---

## Uninstall

```sh
sudo rm /usr/local/bin/transparse
```