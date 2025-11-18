"""CDNG to LTFS-friendly TAR GUI utility."""
from __future__ import annotations

import os
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


FORBIDDEN_CHARS = set(':*?"<>|')
MAX_PATH_LENGTH = 200


@dataclass
class PackResult:
    directory: Path
    tar_path: Path


def find_cdng_directories(root: Path) -> List[Path]:
    """Return sub-directories that contain at least one .dng file."""
    directories: List[Path] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        for child in entry.rglob('*.dng'):
            if child.is_file():
                directories.append(entry)
                break
        else:
            for child in entry.rglob('*.DNG'):
                if child.is_file():
                    directories.append(entry)
                    break
    return directories


def ensure_safe_path(path: Path) -> None:
    """Validate path for LTFS compatibility."""
    relative = path.name
    if len(str(path)) > MAX_PATH_LENGTH:
        raise ValueError(f"Path exceeds {MAX_PATH_LENGTH} characters: {path}")
    if relative != relative.strip():
        raise ValueError(f"Path has leading/trailing spaces: {path}")
    if any(char in FORBIDDEN_CHARS for char in relative):
        raise ValueError(f"Path contains forbidden characters: {path}")


class TarPackager(QObject):
    progress = Signal(str)
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, directories: Iterable[Path], output_root: Path) -> None:
        super().__init__()
        self.directories = list(directories)
        self.output_root = output_root

    def run(self) -> None:
        try:
            results = []
            for directory in self.directories:
                message = f"Packing {directory.name}..."
                self.progress.emit(message)
                tar_path = self.output_root / f"{directory.name}.tar"
                self._pack_directory(directory, tar_path)
                self.progress.emit(f"Validating {tar_path.name}...")
                self._validate_tar(tar_path)
                results.append(PackResult(directory=directory, tar_path=tar_path))
                self.progress.emit(f"Completed {tar_path.name}")
            self.completed.emit(results)
        except Exception as exc:  # pragma: no cover - surface via GUI
            self.failed.emit(str(exc))

    def _pack_directory(self, directory: Path, tar_path: Path) -> None:
        with tarfile.open(
            tar_path,
            mode='w',
            format=tarfile.PAX_FORMAT,
            dereference=True,
            bufsize=tarfile.RECORDSIZE * 128,
        ) as tar:
            for path in sorted(directory.rglob('*')):
                if path.is_dir():
                    ensure_safe_path(path)
                    continue
                if path.is_symlink() or not path.is_file():
                    continue
                ensure_safe_path(path)
                arcname = path.relative_to(directory.parent)
                tar.add(path, arcname=str(arcname), recursive=False)

    def _validate_tar(self, tar_path: Path) -> None:
        with tarfile.open(tar_path, mode='r') as tar:
            for member in tar:
                if member.isdir():
                    continue
                if len(member.name) > MAX_PATH_LENGTH:
                    raise ValueError(f"Tar member exceeds path length: {member.name}")


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('CDNG to LTFS TAR packer')
        self.root_label = QLabel('Select a root directory containing CDNG folders.')
        self.list_widget = QListWidget()
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.choose_button = QPushButton('Choose root directory')
        self.choose_button.clicked.connect(self.choose_root)

        self.scan_button = QPushButton('Scan for CDNG folders')
        self.scan_button.clicked.connect(self.scan_directories)

        self.start_button = QPushButton('Start packing')
        self.start_button.clicked.connect(self.start_packing)
        self.start_button.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self.root_label)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.scan_button)
        layout.addWidget(QLabel('Detected CDNG directories:'))
        layout.addWidget(self.list_widget)
        layout.addWidget(self.start_button)
        layout.addWidget(QLabel('Progress log:'))
        layout.addWidget(self.log)
        self.setLayout(layout)

        self.root_path: Path | None = None
        self.pack_thread: QThread | None = None
        self.pack_worker: TarPackager | None = None

    def choose_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, 'Select root directory', os.getcwd())
        if directory:
            self.root_path = Path(directory)
            self.root_label.setText(f'Root: {self.root_path}')
            self.log.append(f'Selected root directory: {self.root_path}')
            self.list_widget.clear()
            self.start_button.setEnabled(False)

    def scan_directories(self) -> None:
        if not self.root_path:
            QMessageBox.warning(self, 'No root directory', 'Please choose a root directory first.')
            return
        self.list_widget.clear()
        directories = find_cdng_directories(self.root_path)
        if not directories:
            QMessageBox.information(self, 'No CDNG directories', 'No CDNG directories found in root.')
            self.start_button.setEnabled(False)
            return
        for directory in directories:
            item = QListWidgetItem(str(directory))
            item.setData(Qt.ItemDataRole.UserRole, str(directory))
            self.list_widget.addItem(item)
        self.start_button.setEnabled(True)
        self.log.append(f'Found {len(directories)} CDNG directories.')

    def start_packing(self) -> None:
        if not self.root_path:
            return
        directories = [
            Path(self.list_widget.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.list_widget.count())
        ]
        if not directories:
            QMessageBox.information(self, 'Nothing to pack', 'No directories to process.')
            return
        self.start_button.setEnabled(False)
        self.pack_thread = QThread()
        self.pack_worker = TarPackager(directories, self.root_path)
        self.pack_worker.moveToThread(self.pack_thread)
        self.pack_thread.started.connect(self.pack_worker.run)
        self.pack_worker.progress.connect(self.log.append)
        self.pack_worker.completed.connect(self._on_completed)
        self.pack_worker.failed.connect(self._on_failed)
        self.pack_worker.completed.connect(lambda _: self.pack_thread.quit())
        self.pack_worker.failed.connect(lambda _: self.pack_thread.quit())
        self.pack_thread.finished.connect(self._cleanup_worker)
        self.pack_thread.start()
        self.log.append('Started packing...')

    def _on_completed(self, results: List[PackResult]) -> None:
        message = '\n'.join(f"Created {result.tar_path}" for result in results)
        QMessageBox.information(self, 'Packing completed', message)
        self.log.append('All directories packed successfully.')
        self.start_button.setEnabled(True)

    def _on_failed(self, error_message: str) -> None:
        QMessageBox.critical(self, 'Packing failed', error_message)
        self.log.append(f'Error: {error_message}')
        self.start_button.setEnabled(True)

    def _cleanup_worker(self) -> None:
        if self.pack_worker:
            self.pack_worker.deleteLater()
            self.pack_worker = None
        if self.pack_thread:
            self.pack_thread.deleteLater()
            self.pack_thread = None


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    app.exec()


if __name__ == '__main__':
    main()
