# CDNG to LTFS TAR packer

A small PySide6 desktop utility that scans a root directory for folders of CinemaDNG (CDNG) frames and packages each folder into an LTFS-friendly TAR archive.

## Features

- GUI workflow for selecting the root directory and reviewing detected CDNG folders.
- Sequential TAR creation with deterministic settings (`POSIX` format, 64 KiB blocking factor, no compression) suited for LTFS workflows.
- File-name validation to catch LTFS-incompatible characters or overly long paths before archiving.
- Automatic archive verification immediately after creation.
- Two JPEG screenshots are extracted per CDNG sequence (first and middle frame) and saved in the parent folder above the sequence.
- Progress log inside the GUI for long-running jobs.

## Conda environment

Create the environment (Python 3.11 + PySide6 + raw DNG decode dependencies) with:

```bash
conda env create -f environment.yml
conda activate cdng2tar4ltfs
```

## Running the GUI

```bash
python cdng_tar_gui.py
```

### Workflow

1. Click **"Choose root directory"** and select the parent folder that contains one or more sub-directories of CDNG frames.
2. Click **"Scan for CDNG folders"** to populate the list.
3. Review the directories that will be processed, then click **"Start packing"**.
4. Monitor progress in the log panel; completed TAR files are saved next to their source directories.
5. For each sequence, two screenshots are generated with names like `A001_C001_000001_screenshot1.jpg` and `A001_C001_001024_screenshot2.jpg` in the directory above the CDNG sequence.

## TAR settings implemented

- POSIX/PAX format without compression or GNU extensions.
- 64 KiB (blocking factor 128) buffered writes for smooth tape streaming.
- Symlinks are dereferenced; only real files are stored.
- Forbidden LTFS characters and whitespace issues are detected before archive creation.
- Post-write validation ensures members can be read sequentially.
