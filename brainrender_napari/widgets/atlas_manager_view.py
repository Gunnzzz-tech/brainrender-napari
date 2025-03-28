"""The purpose of this file is to provide interactive table view to download
and update atlases. Users interacting with the table can request to
* download an atlas (double-click on row of a not-yet downloaded atlas)
* update an atlas (double-click on row of outdated local atlas)
They can also hover over an up-to-date local atlas and see that
it's up to date.

It is designed to be agnostic from the viewer framework by emitting signals
that any interested observers can connect to.
"""

from typing import Callable

from brainglobe_atlasapi.list_atlases import (
    get_all_atlases_lastversions,
    get_atlases_lastversions,
    get_downloaded_atlases,
)
from brainglobe_atlasapi.update_atlases import install_atlas, update_atlas
from napari.qt import thread_worker
from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QTableView,
    QWidget,
)

from brainrender_napari.data_models.atlas_table_model import AtlasTableModel
from brainrender_napari.utils.formatting import format_atlas_name
from brainrender_napari.widgets.atlas_manager_dialog import AtlasManagerDialog


class AtlasManagerView(QTableView):
    download_atlas_confirmed = Signal(str)
    update_atlas_confirmed = Signal(str)
    progress_updated = Signal(
        int, int, str, object
    )  # completed, total, atlas_name, operation_type

    def __init__(self, parent: QWidget = None):
        """Initialises an atlas table view with latest atlas versions.

        Also responsible for appearance, behaviour on selection, and
        setting up signal-slot connections.
        """
        super().__init__(parent)

        self.setModel(AtlasTableModel(AtlasManagerView))
        self.setEnabled(True)
        self.verticalHeader().hide()
        self.resizeColumnsToContents()

        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)

        self.doubleClicked.connect(self._on_row_double_clicked)
        self.hideColumn(
            self.model().column_headers.index("Raw name")
        )  # hide raw name

    def _on_row_double_clicked(self):
        atlas_name = self.selected_atlas_name()
        if atlas_name in self.cached_downloaded_atlases:  # Use cached version
            up_to_date = self.cached_atlas_versions[atlas_name]["updated"]
            if not up_to_date:
                update_dialog = AtlasManagerDialog(atlas_name, "Update")
                update_dialog.ok_button.clicked.connect(
                    self._on_update_atlas_confirmed
                )
                update_dialog.open()  # Use .open() instead of .exec()
        else:
            download_dialog = AtlasManagerDialog(atlas_name, "Download")
            download_dialog.ok_button.clicked.connect(
                self._on_download_atlas_confirmed
            )
            download_dialog.open()  # Use .open() instead of .exec()

    def _start_worker(
        self,
        operation: Callable,
        atlas_name: str,
        signal: Signal,
        operation_type: str,
    ):
        """
        Helper function that connects the `progress_updated` signal to
        the underlying atlas API progress update function, and then starts
        a download/update operation in separate thread,
        ensuring it returns `signal` when the thread operation finishes.
        """

        def update_fn(completed, total):
            self.progress_updated.emit(
                completed, total, atlas_name, operation_type
            )

        worker = self._apply_in_thread(
            operation, atlas_name, fn_update=update_fn
        )
        worker.returned.connect(lambda result: signal.emit(result))
        worker.start()

    def _on_download_atlas_confirmed(self):
        atlas_name = self.selected_atlas_name()
        self._start_worker(
            install_atlas,
            atlas_name,
            self.download_atlas_confirmed,
            "Downloading",
        )
        self._refresh_cached_atlases()

    def _on_update_atlas_confirmed(self):
        atlas_name = self.selected_atlas_name()
        self._start_worker(
            update_atlas,
            atlas_name,
            self.update_atlas_confirmed,
            "Updating",
        )
        self._refresh_cached_atlases()

    def _refresh_cached_atlases(self):
        self.cached_downloaded_atlases = get_downloaded_atlases()
        self.cached_atlas_versions = get_atlases_lastversions()

    def selected_atlas_name(self) -> str:
        """A single place to get a valid selected atlas name."""
        selected_index = self.selectionModel().currentIndex()
        assert selected_index.isValid()
        selected_atlas_name_index = selected_index.siblingAtColumn(0)
        selected_atlas_name = self.model().data(selected_atlas_name_index)
        return selected_atlas_name

    @thread_worker
    def _apply_in_thread(self, apply: Callable, *args, **kwargs):
        """Helper function that executes the specified function
        in a separate thread."""
        return apply(*args, **kwargs)

    @classmethod
    def get_tooltip_text(cls, atlas_name: str):
        """Returns the atlas name as a formatted string,
        as well as instructions on how to interact with the atlas."""
        if atlas_name in get_downloaded_atlases():
            is_up_to_date = get_atlases_lastversions()[atlas_name]["updated"]
            if is_up_to_date:
                tooltip_text = f"{format_atlas_name(atlas_name)} is up-to-date"
            else:  # needs updating
                tooltip_text = (
                    f"{format_atlas_name(atlas_name)} (double-click to update)"
                )
        elif atlas_name in get_all_atlases_lastversions().keys():
            tooltip_text = (
                f"{format_atlas_name(atlas_name)} (double-click to download)"
            )
        else:
            raise ValueError("Tooltip text called with invalid atlas name.")
        return tooltip_text
