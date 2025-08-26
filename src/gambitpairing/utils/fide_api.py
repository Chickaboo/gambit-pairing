"""Integrated Player Management Dialog with tabs for manual editing, FIDE import, and tournament players."""

from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal

from gambitpairing.gui.notification import show_notification
from gambitpairing.player import Player
from gambitpairing.utils.api import (
    get_cfc_player_info,
    get_fide_player_info,
    search_fide_players,
)

# FIDE columns with better minimum widths
FIDE_COLUMNS: List[Tuple[str, int]] = [
    ("", 5),  # checkbox - smaller to reduce wasted space
    ("Name", 300),
    ("FIDE ID", 100),
    ("Fed", 80),
    ("Title", 80),
    ("Std", 80),
    ("Rapid", 100),  # Increased for better fit
    ("Blitz", 80),
    ("B-Year", 80),
    ("Gender", 110),  # Increased for better fit
]

# Define CFC columns - adjust these based on actual CFC database structure
CFC_COLUMNS: List[Tuple[str, int]] = [
    ("", 5),  # Checkbox column
    ("CFC ID", 80),  # CFC membership ID
    ("Name", 200),  # Player name
    ("Rating", 80),  # CFC rating
    ("Province", 80),  # Province/Territory
    ("City", 120),  # City
    ("Expiry", 80),  # Membership expiry
    ("Status", 80),  # Active/Inactive status
]

# Tournament players columns
TOURNAMENT_COLUMNS: List[Tuple[str, int]] = [
    ("Name", 200),
    ("Rating", 80),
    ("Age", 60),
    ("Gender", 80),
]


class _FideWorker(QObject):
    finished = pyqtSignal(object, object)  # (result, error)

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._interrupted = False

    def interrupt(self):
        """Mark this worker as interrupted."""
        self._interrupted = True

    @QtCore.pyqtSlot()
    def run(self):
        try:
            # Check if we've been interrupted before starting
            if self._interrupted:
                return

            result = self._fn(*self._args, **self._kwargs)

            # Check if we've been interrupted before emitting
            if not self._interrupted:
                self.finished.emit(result, None)
        except Exception as e:
            # Only emit error if we weren't interrupted
            if not self._interrupted:
                self.finished.emit(None, e)


class PlayerManagementDialog(QtWidgets.QDialog):
    """Integrated dialog for player management with tabs for editing, FIDE import, and tournament view."""

    def __init__(self, player: Player, parent=None, tournament=None):
        super().__init__(parent)

        self.player = player
        self.tournament = tournament
        self._thread = None
        self._worker = None
        self._selected_player_data = None
        self._player_data_changed = False  # Track if data has been changed/imported
        self._cleaning_up = False  # Track if we're in cleanup mode

        self.setWindowTitle("Player Management")
        self.setModal(True)
        self.resize(900, 600)

        # Main layout with tabs
        layout = QtWidgets.QVBoxLayout(self)

        self.tab_widget = QtWidgets.QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.details_tab = self._create_details_tab()
        self.tab_widget.addTab(self.details_tab, "Player Details")

        # FIDE tab
        self.fide_tab = self._create_fide_tab()
        self.tab_widget.addTab(self.fide_tab, "Import from FIDE")

        # CFC tab
        self.cfc_tab = self._create_cfc_tab()
        self.tab_widget.addTab(self.cfc_tab, "Import from CFC")

        # US-CF tab TODO
        # self.uscf_tab = self._create_USCF_tab()
        # self.tab_widget.addTab(self.uscf_tab, "Import from US-CF")

        # Tournament players tab (only if tournament provided)
        if self.tournament:
            self.tournament_tab = self._create_tournament_tab()
            self.tab_widget.addTab(
                self.tournament_tab,
                f"Tournament Players ({len(self.tournament.players)})",
            )

        # Dialog buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Install event filter for Enter key handling
        self.installEventFilter(self)

    def _create_details_tab(self):
        """Create the player details editing tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Basic information group
        basic_group = QtWidgets.QGroupBox("Basic Information")
        form = QtWidgets.QFormLayout(basic_group)

        # Name with copy button
        name_layout = QtWidgets.QHBoxLayout()
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setToolTip("Full name of the player")
        self.name_edit.setMaximumHeight(40)
        self.name_edit.textChanged.connect(
            lambda: setattr(self, "_player_data_changed", True)
        )
        name_layout.addWidget(self.name_edit)
        name_layout.addWidget(
            self._create_copy_button("Copy name to clipboard", self.name_edit, "Name")
        )
        form.addRow("Name:", name_layout)

        # Rating with copy button
        rating_layout = QtWidgets.QHBoxLayout()
        self.rating_spin = QtWidgets.QSpinBox()
        self.rating_spin.setRange(0, 3500)
        self.rating_spin.setValue(1000)
        self.rating_spin.setMaximumHeight(40)
        self.rating_spin.setToolTip("Player's rating (0-3500)")
        rating_layout.addWidget(self.rating_spin)
        # Create a dummy QLineEdit for rating copy functionality
        self._rating_copy_helper = QtWidgets.QLineEdit()
        self._rating_copy_helper.setVisible(False)
        rating_copy_btn = self._create_copy_button(
            "Copy rating to clipboard", self._rating_copy_helper, "Rating"
        )
        rating_copy_btn.clicked.disconnect()
        rating_copy_btn.clicked.connect(
            lambda: self._copy_to_clipboard(str(self.rating_spin.value()), "Rating")
        )
        rating_layout.addWidget(rating_copy_btn)
        form.addRow("Rating:", rating_layout)

        # Gender and Date of Birth on same line
        gender_dob_layout = QtWidgets.QHBoxLayout()
        self.gender_combo = QtWidgets.QComboBox()
        self.gender_combo.addItems(["", "Male", "Female"])
        self.gender_combo.setMaximumHeight(40)
        self.gender_combo.setToolTip("Select gender (optional)")
        gender_dob_layout.addWidget(QtWidgets.QLabel("Gender:"))
        gender_dob_layout.addWidget(self.gender_combo)

        self.dob_edit = QtWidgets.QDateEdit()
        self.dob_edit.setCalendarPopup(True)
        self.dob_edit.setDate(QtCore.QDate(2000, 1, 1))
        self.dob_edit.setSpecialValueText("Not set")
        self.dob_edit.setMaximumHeight(40)
        self.dob_edit.setToolTip("Date of birth (optional)")

        gender_dob_layout.addSpacing(10)
        gender_dob_layout.addWidget(QtWidgets.QLabel("Date of Birth:"))
        gender_dob_layout.addWidget(self.dob_edit)
        gender_dob_layout.addStretch()

        form.addRow(gender_dob_layout)

        layout.addWidget(basic_group)

        # Contact information group
        contact_group = QtWidgets.QGroupBox("Contact Information (Optional)")
        contact_form = QtWidgets.QFormLayout(contact_group)

        # Phone with copy button
        phone_layout = QtWidgets.QHBoxLayout()
        self.phone_edit = QtWidgets.QLineEdit()
        self.phone_edit.setMaximumHeight(40)
        self.phone_edit.setToolTip("Phone number (optional)")
        phone_layout.addWidget(self.phone_edit)
        phone_layout.addWidget(
            self._create_copy_button(
                "Copy phone to clipboard", self.phone_edit, "Phone"
            )
        )
        contact_form.addRow("Phone:", phone_layout)

        # Email with copy button
        email_layout = QtWidgets.QHBoxLayout()
        self.email_edit = QtWidgets.QLineEdit()
        self.email_edit.setMaximumHeight(40)
        self.email_edit.setToolTip("Email address (optional)")
        email_layout.addWidget(self.email_edit)
        email_layout.addWidget(
            self._create_copy_button(
                "Copy email to clipboard", self.email_edit, "Email"
            )
        )
        contact_form.addRow("Email:", email_layout)

        # Club with copy button
        club_layout = QtWidgets.QHBoxLayout()
        self.club_edit = QtWidgets.QLineEdit()
        self.club_edit.setMaximumHeight(40)
        self.club_edit.setToolTip("Chess club (optional)")
        club_layout.addWidget(self.club_edit)
        club_layout.addWidget(
            self._create_copy_button("Copy club to clipboard", self.club_edit, "Club")
        )
        contact_form.addRow("Club:", club_layout)

        # Federation with copy button
        federation_layout = QtWidgets.QHBoxLayout()
        self.federation_edit = QtWidgets.QLineEdit()
        self.federation_edit.setMaximumHeight(40)
        self.federation_edit.setToolTip("Federation/Country (optional)")
        federation_layout.addWidget(self.federation_edit)
        federation_layout.addWidget(
            self._create_copy_button(
                "Copy federation to clipboard", self.federation_edit, "Federation"
            )
        )
        contact_form.addRow("Federation:", federation_layout)

        layout.addWidget(contact_group)

        # FIDE metadata (editable with copy buttons)
        self.fide_group = QtWidgets.QGroupBox("FIDE Information")
        self.fide_group.setVisible(False)
        fide_form = QtWidgets.QFormLayout(self.fide_group)

        # FIDE ID with copy button
        fide_id_layout = QtWidgets.QHBoxLayout()
        self.fide_id_edit = QtWidgets.QLineEdit()
        self.fide_id_edit.setMaximumHeight(40)
        self.fide_id_edit.setToolTip("FIDE ID (editable)")
        fide_id_layout.addWidget(self.fide_id_edit)
        fide_id_layout.addWidget(
            self._create_copy_button(
                "Copy FIDE ID to clipboard", self.fide_id_edit, "FIDE ID"
            )
        )
        fide_form.addRow("FIDE ID:", fide_id_layout)

        # Title with copy button
        title_layout = QtWidgets.QHBoxLayout()
        self.fide_title_edit = QtWidgets.QLineEdit()
        self.fide_title_edit.setMaximumHeight(40)
        self.fide_title_edit.setToolTip("FIDE Title (editable)")
        title_layout.addWidget(self.fide_title_edit)
        title_layout.addWidget(
            self._create_copy_button(
                "Copy title to clipboard", self.fide_title_edit, "Title"
            )
        )
        fide_form.addRow("Title:", title_layout)

        # Standard rating with copy button
        std_layout = QtWidgets.QHBoxLayout()
        self.fide_std_edit = QtWidgets.QLineEdit()
        self.fide_std_edit.setMaximumHeight(40)
        self.fide_std_edit.setToolTip("Standard rating (editable)")
        std_layout.addWidget(self.fide_std_edit)
        std_layout.addWidget(
            self._create_copy_button(
                "Copy standard rating to clipboard",
                self.fide_std_edit,
                "Standard Rating",
            )
        )
        fide_form.addRow("Standard:", std_layout)

        # Rapid rating with copy button
        rapid_layout = QtWidgets.QHBoxLayout()
        self.fide_rapid_edit = QtWidgets.QLineEdit()
        self.fide_rapid_edit.setMaximumHeight(40)
        self.fide_rapid_edit.setToolTip("Rapid rating (editable)")
        rapid_layout.addWidget(self.fide_rapid_edit)
        rapid_layout.addWidget(
            self._create_copy_button(
                "Copy rapid rating to clipboard", self.fide_rapid_edit, "Rapid Rating"
            )
        )
        fide_form.addRow("Rapid:", rapid_layout)

        # Blitz rating with copy button
        blitz_layout = QtWidgets.QHBoxLayout()
        self.fide_blitz_edit = QtWidgets.QLineEdit()
        self.fide_blitz_edit.setMaximumHeight(40)
        self.fide_blitz_edit.setToolTip("Blitz rating (editable)")
        blitz_layout.addWidget(self.fide_blitz_edit)
        blitz_layout.addWidget(
            self._create_copy_button(
                "Copy blitz rating to clipboard", self.fide_blitz_edit, "Blitz Rating"
            )
        )
        fide_form.addRow("Blitz:", blitz_layout)

        layout.addWidget(self.fide_group)
        layout.addStretch()

        # Populate if provided
        self._populate_details_form()

        return widget

    def _copy_to_clipboard(self, text: str, field_name: str = "") -> None:
        """Copy text to clipboard with improved feedback using notification."""
        if not text.strip():
            show_notification(
                self,
                (
                    f"Nothing to copy - {field_name} is empty"
                    if field_name
                    else "Nothing to copy"
                ),
                1500,
                "warning",  # Use warning type for empty fields
            )
            return

        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(text.strip())

        # Show success notification
        display_text = text.strip()
        if len(display_text) > 20:
            display_text = display_text[:20] + "..."

        show_notification(
            self,
            (
                f"Copied {field_name}: {display_text}"
                if field_name
                else f"Copied: {display_text}"
            ),
            2000,
            "success",  # Use success type for successful copies
        )

    def _create_copy_button(
        self, tooltip_text: str, connected_widget: QtWidgets.QLineEdit, field_name: str
    ) -> QtWidgets.QPushButton:
        """Create a modern, theme-consistent copy button with clipboard icon and styling."""
        btn = QtWidgets.QPushButton()
        btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        btn.setToolTip(tooltip_text)
        btn.setFixedSize(32, 32)

        # Try to use a system clipboard icon, fallback to Unicode if not available
        icon = None
        try:
            icon = QtGui.QIcon.fromTheme("edit-copy")
        except Exception:
            icon = None
        if not icon or icon.isNull():
            # Fallback: use a simple Unicode clipboard symbol
            btn.setText("⧉")
            btn.setStyleSheet(
                """
                QPushButton {
                    font-size: 16px;
                    color: #444;
                    background: transparent;
                    border: none;
                    border-radius: 6px;
                    padding: 0 4px;
                }
                QPushButton:hover {
                    background: #e0e4ea;
                    color: #222;
                }
                QPushButton:pressed {
                    background: #d0d4da;
                }
            """
            )
        else:
            btn.setIcon(icon)
            btn.setIconSize(QtCore.QSize(18, 18))
            btn.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 6px;
                    padding: 0 4px;
                }
                QPushButton:hover {
                    background: #e0e4ea;
                }
                QPushButton:pressed {
                    background: #d0d4da;
                }
            """
            )
        btn.clicked.connect(
            lambda: self._copy_to_clipboard(connected_widget.text(), field_name)
        )
        return btn

    def _create_fide_tab(self):
        """Create the FIDE import tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Search section with group box
        search_group = QtWidgets.QGroupBox("Search FIDE Database")
        search_layout = QtWidgets.QVBoxLayout(search_group)

        # Unified search controls
        search_bar = QtWidgets.QHBoxLayout()

        # Single unified search field
        search_bar.addWidget(QtWidgets.QLabel("Search:"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setToolTip(
            "Enter player name (e.g., 'Magnus Carlsen') or FIDE ID (e.g., '1503014')"
        )
        self.search_edit.setPlaceholderText("Enter player name or FIDE ID...")
        self.search_edit.installEventFilter(self)
        search_bar.addWidget(self.search_edit)

        self.btn_search = QtWidgets.QPushButton("Search")
        self.btn_search.setToolTip("Search by name or FIDE ID (Ctrl+Enter)")
        self.btn_search.setShortcut("Ctrl+Return")
        self.btn_search.clicked.connect(self._on_search)
        search_bar.addWidget(self.btn_search)

        # Clear button
        self.btn_clear = QtWidgets.QPushButton("Clear Results")
        self.btn_clear.setToolTip("Clear search results and start over (Ctrl+R)")
        self.btn_clear.setShortcut("Ctrl+R")
        self.btn_clear.clicked.connect(self._clear_fide_results)
        self.btn_clear.setEnabled(False)  # Initially disabled
        search_bar.addWidget(self.btn_clear)

        search_layout.addLayout(search_bar)

        # Instructions with examples
        instructions = QtWidgets.QLabel(
            "<b>Search Tips:</b><br>"
            "• <b>Name search:</b> Try 'Magnus Carlsen', 'Carlsen', or 'Magnus'<br>"
            "• <b>FIDE ID search:</b> Enter exact ID like 1503014<br>"
            "• <b>Auto-detection:</b> Numbers are treated as FIDE IDs, text as names<br>"
            "• <b>Right-click</b> on results for copy options<br>"
            "• <b>Double-click</b> any result to import that player"
        )
        instructions.setStyleSheet(
            "color: #444; font-size: 10px; background-color: #f0f0f0; "
            "padding: 8px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px;"
        )
        search_layout.addWidget(instructions)

        layout.addWidget(search_group)

        # Results table with better column widths - make this section much larger
        results_group = QtWidgets.QGroupBox("Search Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)

        self.fide_table = QtWidgets.QTableWidget(0, len(FIDE_COLUMNS))
        self.fide_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.fide_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.fide_table.verticalHeader().setVisible(False)
        self.fide_table.setAlternatingRowColors(True)
        self.fide_table.setMinimumHeight(350)  # Make table much taller

        # Set headers and minimum column widths
        header = self.fide_table.horizontalHeader()
        for i, (title, width) in enumerate(FIDE_COLUMNS):
            self.fide_table.setHorizontalHeaderItem(
                i, QtWidgets.QTableWidgetItem(title)
            )
            self.fide_table.setColumnWidth(i, width)
            # Set minimum width to prevent columns from being too narrow
            header.setMinimumSectionSize(width)

        # Make checkbox column resize to contents (minimum space)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )

        self.fide_table.itemSelectionChanged.connect(self._on_fide_selection_changed)
        self.fide_table.itemDoubleClicked.connect(self._use_selected_fide_player)
        self.fide_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fide_table.customContextMenuRequested.connect(self._show_fide_context_menu)

        results_layout.addWidget(self.fide_table)

        # Results info label
        self.results_info_label = QtWidgets.QLabel(
            "Search for players above to see results here"
        )
        self.results_info_label.setStyleSheet("color: gray; font-style: italic;")
        results_layout.addWidget(self.results_info_label)

        layout.addWidget(results_group, 2)  # Give more space to results section

        # Progress bar and buttons
        controls_layout = QtWidgets.QHBoxLayout()

        self.fide_progress = QtWidgets.QProgressBar()
        self.fide_progress.setVisible(False)
        controls_layout.addWidget(self.fide_progress)

        controls_layout.addStretch()

        self.btn_use_selected = QtWidgets.QPushButton("Import Selected Player")
        self.btn_use_selected.setEnabled(False)
        self.btn_use_selected.setToolTip(
            "Import the selected FIDE player data to the Player Details tab"
        )
        self.btn_use_selected.clicked.connect(self._use_selected_fide_player)
        controls_layout.addWidget(self.btn_use_selected)

        layout.addLayout(controls_layout)

        return widget

    def _create_cfc_tab(self):
        """Create the CFC import tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Search section with group box
        search_group = QtWidgets.QGroupBox("Search CFC Database")
        search_layout = QtWidgets.QVBoxLayout(search_group)

        # Unified search controls
        search_bar = QtWidgets.QHBoxLayout()

        # Single unified search field
        search_bar.addWidget(QtWidgets.QLabel("Search:"))
        self.cfc_search_edit = QtWidgets.QLineEdit()
        self.cfc_search_edit.setToolTip(
            "Enter player name (e.g., 'Kevin Spraggett') or CFC ID (e.g., '100123')"
        )
        self.cfc_search_edit.setPlaceholderText("Enter player name or CFC ID...")
        self.cfc_search_edit.installEventFilter(self)
        search_bar.addWidget(self.cfc_search_edit)

        self.btn_cfc_search = QtWidgets.QPushButton("Search")
        self.btn_cfc_search.setToolTip("Search by name or CFC ID")
        self.btn_cfc_search.clicked.connect(self._on_cfc_search)
        search_bar.addWidget(self.btn_cfc_search)

        # Clear button
        self.btn_cfc_clear = QtWidgets.QPushButton("Clear Results")
        self.btn_cfc_clear.setToolTip("Clear search results and start over (Ctrl+R)")
        self.btn_cfc_clear.setShortcut("Ctrl+R")
        self.btn_cfc_clear.clicked.connect(self._clear_cfc_results)
        self.btn_cfc_clear.setEnabled(False)  # Initially disabled
        search_bar.addWidget(self.btn_cfc_clear)

        search_layout.addLayout(search_bar)

        # Instructions with examples
        instructions = QtWidgets.QLabel(
            "<b>Search Tips:</b><br>"
            "• <b>Name search:</b> Try 'Kevin Spraggett', 'Spraggett', or 'Kevin'<br>"
            "• <b>CFC ID search:</b> Enter exact ID like 100123<br>"
            "• <b>Auto-detection:</b> Numbers are treated as CFC IDs, text as names<br>"
            "• <b>Province filter:</b> Narrow results by selecting a specific province<br>"
            "• <b>Right-click</b> on results for copy options<br>"
            "• <b>Double-click</b> any result to import that player"
        )
        instructions.setStyleSheet(
            "color: #444; font-size: 10px; background-color: #f0f0f0; "
            "padding: 8px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px;"
        )
        search_layout.addWidget(instructions)

        layout.addWidget(search_group)

        # Results table with better column widths - make this section much larger
        results_group = QtWidgets.QGroupBox("Search Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)

        self.cfc_table = QtWidgets.QTableWidget(0, len(CFC_COLUMNS))
        self.cfc_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.cfc_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.cfc_table.verticalHeader().setVisible(False)
        self.cfc_table.setAlternatingRowColors(True)
        self.cfc_table.setMinimumHeight(350)  # Make table much taller

        # Set headers and minimum column widths
        header = self.cfc_table.horizontalHeader()
        for i, (title, width) in enumerate(CFC_COLUMNS):
            self.cfc_table.setHorizontalHeaderItem(i, QtWidgets.QTableWidgetItem(title))
            self.cfc_table.setColumnWidth(i, width)
            # Set minimum width to prevent columns from being too narrow
            header.setMinimumSectionSize(width)

        # Make checkbox column resize to contents (minimum space)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )

        self.cfc_table.itemSelectionChanged.connect(self._on_cfc_selection_changed)
        self.cfc_table.itemDoubleClicked.connect(self._use_selected_cfc_player)
        self.cfc_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cfc_table.customContextMenuRequested.connect(self._show_cfc_context_menu)

        results_layout.addWidget(self.cfc_table)

        # Results info label
        self.cfc_results_info_label = QtWidgets.QLabel(
            "Search for players above to see results here"
        )
        self.cfc_results_info_label.setStyleSheet("color: gray; font-style: italic;")
        results_layout.addWidget(self.cfc_results_info_label)

        layout.addWidget(results_group, 2)  # Give more space to results section

        # Progress bar and buttons
        controls_layout = QtWidgets.QHBoxLayout()

        self.cfc_progress = QtWidgets.QProgressBar()
        self.cfc_progress.setVisible(False)
        controls_layout.addWidget(self.cfc_progress)

        controls_layout.addStretch()

        self.btn_use_selected_cfc = QtWidgets.QPushButton("Import Selected Player")
        self.btn_use_selected_cfc.setEnabled(False)
        self.btn_use_selected_cfc.setToolTip(
            "Import the selected CFC player data to the Player Details tab"
        )
        self.btn_use_selected_cfc.clicked.connect(self._use_selected_cfc_player)
        controls_layout.addWidget(self.btn_use_selected_cfc)

        layout.addLayout(controls_layout)

        return widget

    # Supporting methods for CFC functionality
    def _on_cfc_search(self):
        """Handle CFC search button click."""
        search_term = self.cfc_search_edit.text().strip()
        if not search_term:
            QtWidgets.QMessageBox.information(
                self,
                "Search Required",
                "Please enter a player name or CFC ID to search.",
            )
            return

        self._search_cfc_players(search_term)

    def _search_cfc_players(self, search_term):
        """Search for CFC players."""
        self.cfc_progress.setVisible(True)
        self.cfc_progress.setRange(0, 0)  # Indeterminate progress
        self.btn_cfc_search.setEnabled(False)
        self.cfc_results_info_label.setText("Searching CFC database...")

        try:
            results = get_cfc_player_info(search_term)

            self._populate_cfc_results(results, search_term)

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Search Error", f"Failed to search CFC database:\n{str(e)}"
            )
            self.cfc_results_info_label.setText("Search failed")

        finally:
            self.cfc_progress.setVisible(False)
            self.btn_cfc_search.setEnabled(True)
            self.btn_cfc_clear.setEnabled(True)

    def _populate_cfc_results(self, results, search_term):
        """Populate the CFC results table."""
        self.cfc_table.setRowCount(len(results))

        for row, player in enumerate(results):
            # Checkbox
            checkbox = QtWidgets.QCheckBox()
            self.cfc_table.setCellWidget(row, 0, checkbox)

            # Player data
            items = [
                player.get("cfc_id", ""),
                player.get("name", ""),
                str(player.get("rating", "")),
                player.get("province", ""),
                player.get("city", ""),
                player.get("expiry_date", ""),
                player.get("status", ""),
            ]

            for col, text in enumerate(items, 1):
                item = QtWidgets.QTableWidgetItem(str(text))
                item.setData(Qt.ItemDataRole.UserRole, player)  # Store full player data
                self.cfc_table.setItem(row, col, item)

        # Update results info
        if results:
            self.cfc_results_info_label.setText(
                f"Found {len(results)} player(s) for '{search_term}'"
            )
        else:
            self.cfc_results_info_label.setText(
                f"No players found for '{search_term}'. Try a different search term."
            )

    def _clear_cfc_results(self):
        """Clear CFC search results."""
        self.cfc_table.setRowCount(0)
        self.cfc_search_edit.clear()
        self.cfc_results_info_label.setText(
            "Search for players above to see results here"
        )
        self.btn_cfc_clear.setEnabled(False)
        self.btn_use_selected_cfc.setEnabled(False)

    def _on_cfc_selection_changed(self):
        """Handle CFC table selection change."""
        has_selection = bool(self.cfc_table.selectedItems())
        self.btn_use_selected_cfc.setEnabled(has_selection)

    def _use_selected_cfc_player(self):
        """Import the selected CFC player."""
        current_row = self.cfc_table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.information(
                self, "No Selection", "Please select a player to import."
            )
            return

        # Get player data from the selected row
        item = self.cfc_table.item(current_row, 1)  # CFC ID column
        if item:
            player_data = item.data(Qt.ItemDataRole.UserRole)
            self._import_cfc_player_data(player_data)

    def _import_cfc_player_data(self, player_data):
        """Import CFC player data to the Player Details tab."""
        if not player_data:
            return

        try:
            # Map CFC data to player form fields
            # Adjust field mappings based on your actual form structure

            # Switch to Player Details tab
            self.tab_widget.setCurrentIndex(0)  # Assuming Player Details is first tab

            # Populate form fields - adjust these based on your actual field names
            if hasattr(self, "name_edit"):
                self.name_edit.setText(player_data.get("name", ""))

            if hasattr(self, "cfc_id_edit"):
                self.cfc_id_edit.setText(str(player_data.get("cfc_id", "")))

            if hasattr(self, "rating_edit"):
                self.rating_edit.setText(str(player_data.get("rating", "")))

            if hasattr(self, "province_edit"):
                self.province_edit.setText(player_data.get("province", ""))

            if hasattr(self, "city_edit"):
                self.city_edit.setText(player_data.get("city", ""))

            # Show success message
            QtWidgets.QMessageBox.information(
                self,
                "Import Successful",
                f"Successfully imported CFC player: {player_data.get('name', 'Unknown')}",
            )

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Import Error", f"Failed to import player data:\n{str(e)}"
            )

    def _show_cfc_context_menu(self, position):
        """Show context menu for CFC results table."""
        item = self.cfc_table.itemAt(position)
        if not item:
            return

        menu = QtWidgets.QMenu(self)

        # Copy actions
        copy_name_action = menu.addAction("Copy Name")
        copy_cfc_id_action = menu.addAction("Copy CFC ID")
        copy_rating_action = menu.addAction("Copy Rating")
        menu.addSeparator()
        copy_all_action = menu.addAction("Copy All Data")

        action = menu.exec(self.cfc_table.mapToGlobal(position))

        if action:
            row = item.row()
            clipboard = QtWidgets.QApplication.clipboard()

            if action == copy_name_action:
                clipboard.setText(self.cfc_table.item(row, 2).text())  # Name column
            elif action == copy_cfc_id_action:
                clipboard.setText(self.cfc_table.item(row, 1).text())  # CFC ID column
            elif action == copy_rating_action:
                clipboard.setText(self.cfc_table.item(row, 3).text())  # Rating column
            elif action == copy_all_action:
                # Copy all visible data for the row
                data_parts = []
                for col in range(
                    1, self.cfc_table.columnCount()
                ):  # Skip checkbox column
                    header = self.cfc_table.horizontalHeaderItem(col).text()
                    value = self.cfc_table.item(row, col).text()
                    data_parts.append(f"{header}: {value}")
                clipboard.setText(" | ".join(data_parts))

    def _query_cfc_database(self, search_term, is_id_search):
        """
        Query the CFC database API.

        This is a placeholder method that should be implemented with actual CFC API calls.
        The CFC may have a different API structure than FIDE.

        Parameters
        ----------
            search_term: The search term (name or CFC ID)
            is_id_search: True if searching by CFC ID, False if by name

        Returns
        -------
            List of player dictionaries with CFC data
        """
        # Placeholder - replace with actual CFC API implementation
        # You'll need to research the CFC's available APIs or web scraping methods

        # Example structure of what this might return:
        example_results = [
            {
                "cfc_id": "123456",
                "name": "John Smith",
                "rating": 1850,
                "province": "ON",
                "city": "Toronto",
                "expiry_date": "2024-12-31",
                "status": "Active",
            }
        ]

        # For now, return empty list - implement actual API call here
        return []

    def _create_tournament_tab(self):
        """Create the tournament players tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Check if tournament has players
        if not self.tournament or len(self.tournament.players) == 0:
            # Show empty state with helpful message and navigation
            empty_layout = QtWidgets.QVBoxLayout()
            empty_layout.addStretch()

            # Icon or large text
            no_players_label = QtWidgets.QLabel("🏆")
            no_players_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_players_label.setStyleSheet("font-size: 48pt; margin: 20px;")
            empty_layout.addWidget(no_players_label)

            # Main message
            main_message = QtWidgets.QLabel("No Players in Tournament Yet")
            main_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            main_message.setStyleSheet(
                "font-size: 18pt; font-weight: bold; color: #666; margin: 10px;"
            )
            empty_layout.addWidget(main_message)

            # Sub message
            sub_message = QtWidgets.QLabel("Start by adding players to your tournament")
            sub_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_message.setStyleSheet(
                "font-size: 12pt; color: #999; margin-bottom: 20px;"
            )
            empty_layout.addWidget(sub_message)

            # Navigation buttons
            buttons_layout = QtWidgets.QHBoxLayout()
            buttons_layout.addStretch()

            goto_fide_btn = QtWidgets.QPushButton("Import from FIDE")
            goto_fide_btn.setStyleSheet(
                "padding: 12px 24px; font-size: 12pt; font-weight: bold;"
            )
            goto_fide_btn.clicked.connect(
                lambda: self.tab_widget.setCurrentIndex(1)
            )  # FIDE tab
            buttons_layout.addWidget(goto_fide_btn)

            goto_details_btn = QtWidgets.QPushButton("Add Player Manually")
            goto_details_btn.setStyleSheet(
                "padding: 12px 24px; font-size: 12pt; font-weight: bold;"
            )
            goto_details_btn.clicked.connect(
                lambda: self.tab_widget.setCurrentIndex(0)
            )  # Details tab
            buttons_layout.addWidget(goto_details_btn)

            buttons_layout.addStretch()
            empty_layout.addLayout(buttons_layout)
            empty_layout.addStretch()

            layout.addLayout(empty_layout)
            return widget

        # Instructions
        instructions = QtWidgets.QLabel(
            "Double-click a player to edit, or select and click the button below"
        )
        instructions.setStyleSheet(
            "color: gray; font-style: italic; margin-bottom: 10px;"
        )
        layout.addWidget(instructions)

        # Tournament players table with proper column widths
        self.tournament_table = QtWidgets.QTableWidget(0, len(TOURNAMENT_COLUMNS))
        self.tournament_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tournament_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tournament_table.verticalHeader().setVisible(False)
        self.tournament_table.setAlternatingRowColors(True)

        # Set headers and column widths with proper stretching
        header = self.tournament_table.horizontalHeader()
        for i, (title, width) in enumerate(TOURNAMENT_COLUMNS):
            self.tournament_table.setHorizontalHeaderItem(
                i, QtWidgets.QTableWidgetItem(title)
            )
            self.tournament_table.setColumnWidth(i, width)
            header.setMinimumSectionSize(width)

        # Make the Name column stretch to fill available space
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        # Keep other columns at fixed widths
        for i in range(1, len(TOURNAMENT_COLUMNS)):
            header.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeMode.Fixed)

        self.tournament_table.itemSelectionChanged.connect(
            self._on_tournament_selection_changed
        )
        self.tournament_table.itemDoubleClicked.connect(
            self._edit_selected_tournament_player
        )
        layout.addWidget(self.tournament_table, 1)

        # Controls
        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.addStretch()

        self.btn_edit_tournament_player = QtWidgets.QPushButton("Edit Selected Player")
        self.btn_edit_tournament_player.setEnabled(False)
        self.btn_edit_tournament_player.setToolTip(
            "Edit the selected tournament player"
        )
        self.btn_edit_tournament_player.clicked.connect(
            self._edit_selected_tournament_player
        )
        controls_layout.addWidget(self.btn_edit_tournament_player)

        layout.addLayout(controls_layout)

        # Populate tournament players
        self._populate_tournament_table()

        return widget

    def _populate_details_form(self):
        """Populate the details form with player data."""
        self.name_edit.setText(self.player_data.get("name", ""))

        # Handle gender (sync sex -> gender)
        gender = self.player.gender
        if gender:
            if gender == "M":
                self.gender_combo.setCurrentText("Male")
            elif gender == "F":
                self.gender_combo.setCurrentText("Female")
            else:
                idx = self.gender_combo.findText(gender)
                if idx >= 0:
                    self.gender_combo.setCurrentIndex(idx)
                else:
                    self.gender_combo.setCurrentIndex(idx if idx >= 0 else 0)

        # Date of birth
        dob_str = self.player_data.get("date_of_birth")
        if dob_str:
            try:
                dob_qdate = QtCore.QDate.fromString(dob_str, "yyyy-MM-dd")
                if dob_qdate.isValid():
                    self.dob_edit.setDate(dob_qdate)
            except (ValueError, TypeError):
                pass

        self.phone_edit.setText(self.player.phone or "")
        self.email_edit.setText(self.player.email or "")
        self.club_edit.setText(self.player.club or "")

    def _populate_tournament_table(self):
        """Populate the tournament players table."""
        if not self.tournament:
            return

        self.tournament_table.setRowCount(0)
        for player in self.tournament.players.values():
            self._append_tournament_row(player)

        self.tournament_table.resizeRowsToContents()

    def _append_tournament_row(self, player: Player):
        """Add a player row to the tournament table."""
        row = self.tournament_table.rowCount()
        self.tournament_table.insertRow(row)

        # Name
        name_item = QtWidgets.QTableWidgetItem(player.name)
        name_item.setData(Qt.ItemDataRole.UserRole, player.id)
        self.tournament_table.setItem(row, 0, name_item)

        # Rating
        self.tournament_table.setItem(
            row, 1, QtWidgets.QTableWidgetItem(str(player.rating))
        )

        # Age (handle None case safely)
        age = player.age
        age_str = str(age) if age is not None else ""
        self.tournament_table.setItem(row, 2, QtWidgets.QTableWidgetItem(age_str))

        # Gender
        gender_str = (
            "Male" if player.gender == "M" else "Female" if player.gender == "F" else ""
        )
        gender_item = QtWidgets.QTableWidgetItem(gender_str)
        self.tournament_table.setItem(row, 3, gender_item)

    def eventFilter(self, obj, event):
        """Handle Enter key in search field."""
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                if obj == self.search_edit:
                    self._on_search()
                    return True
        return super().eventFilter(obj, event)

    def _set_fide_busy(self, busy: bool, status_text: str = "") -> None:
        """Set the UI state for FIDE operations with status update."""
        controls = [
            self.search_edit,
            self.btn_search,
            self.btn_use_selected,
        ]

        for control in controls:
            control.setEnabled(not busy)

        self.fide_progress.setVisible(busy)
        if busy:
            self.fide_progress.setRange(0, 0)  # Indeterminate
            if status_text:
                self.results_info_label.setText(status_text)
                self.results_info_label.setStyleSheet(
                    "color: blue; font-style: italic;"
                )
        else:
            self.fide_progress.setVisible(False)

    def _on_search(self) -> None:
        """Unified search for players by name or FIDE ID with auto-detection."""
        # Prevent overlapping searches
        if self._thread and self._thread.isRunning():
            return

        text = self.search_edit.text().strip()
        if not text:
            QtWidgets.QMessageBox.information(
                self,
                "Search Required",
                "Please enter a player name or FIDE ID to search.",
            )
            return

        # Auto-detect search type: if it's all digits, treat as FIDE ID
        if text.isdigit():
            # FIDE ID search
            try:
                fide_id = text

                raise ValueError("FIDE ID must be positive")
            except ValueError:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid FIDE ID",
                    "Please enter a valid FIDE ID (positive number only).\n"
                    "Example: 1503014 for Magnus Carlsen",
                )
                return

            # Set cancellation flag for uniformity
            self._current_search_cancel_flag = {"cancelled": False}
            self._run_async(
                get_fide_player_info(fide_id),
                status_text=f"Looking up FIDE ID {fide_id}...",
            )
        else:
            # Name search
            if len(text) < 2:
                QtWidgets.QMessageBox.information(
                    self,
                    "Search Too Short",
                    "Please enter at least 2 characters for name search.",
                )
                return

            # Prepare cooperative cancellation flag
            self._current_search_cancel_flag = {"cancelled": False}

            def is_cancelled():
                return self._current_search_cancel_flag["cancelled"]

            self._run_async(
                lambda: search_fide_players(name=text, is_cancelled=is_cancelled),
                status_text=f"Searching FIDE database for '{text}'...",
            )

    def _clear_fide_results(self) -> None:
        """Clear the FIDE search results table."""
        self.fide_table.setRowCount(0)
        self.btn_use_selected.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.fide_group.setVisible(False)

        # Reset info label
        self.results_info_label.setText("Search for players above to see results here")
        self.results_info_label.setStyleSheet("color: gray; font-style: italic;")

        # Clear search field
        self.search_edit.clear()

    def _run_async(self, fn: Callable, status_text: str = "Processing...") -> None:
        """Run function in background thread with proper cleanup of previous jobs."""
        # Always abort any existing job before starting a new one
        self._abort_current_job()

        # Set busy state with status
        self._set_fide_busy(True, status_text)

        # Create new worker and thread
        self._worker = _FideWorker(fn)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals with unique connection to prevent multiple connections
        self._worker.finished.connect(
            self._on_fide_finished, QtCore.Qt.ConnectionType.UniqueConnection
        )
        self._thread.started.connect(self._worker.run)
        self._thread.setParent(self)  # ensure dialog owns lifetime

        # Start the thread
        self._thread.start()

    def _on_fide_finished(self, result, error) -> None:
        """Handle completion of FIDE operation."""
        # Check if we've already cleaned up (aborted) - ignore late signals
        if not self._thread or not self._worker or self._cleaning_up:
            return

        if error:
            self.results_info_label.setText(f"Search failed: {error}")
            self.results_info_label.setStyleSheet("color: red; font-weight: bold;")
            QtWidgets.QMessageBox.warning(self, "FIDE Search Error", f"Error: {error}")
        elif result:
            self._display_fide_results(result)
        else:
            self.results_info_label.setText(
                "No players found. Try a different search term."
            )
            self.results_info_label.setStyleSheet("color: orange; font-weight: bold;")
            QtWidgets.QMessageBox.information(self, "No Results", "No players found.")

        self._set_fide_busy(False)
        # Gracefully finalize thread post-finish
        self._finalize_thread()

    def _finalize_thread(self):
        thread = self._thread
        worker = self._worker
        if not thread:
            return
        if worker:
            try:
                worker.finished.disconnect(self._on_fide_finished)
            except (RuntimeError, TypeError):
                pass
        if thread.isRunning():
            thread.quit()
            if not thread.wait(1500):
                thread.terminate()
                thread.wait(200)
        if worker:
            worker.deleteLater()
        self._thread = None
        self._worker = None

    def _display_fide_results(self, players: List[Dict[str, Any]]) -> None:
        self.fide_table.setRowCount(0)
        for p in players:
            self._append_fide_row(p)
        self.fide_table.resizeRowsToContents()

        # Update info label and enable clear button
        player_count = len(players)
        if player_count == 1:
            self.results_info_label.setText(
                "Found 1 player. Double-click or select and click 'Import Selected Player' to use."
            )
        else:
            self.results_info_label.setText(
                f"Found {player_count} players. Double-click or select and click 'Import Selected Player' to use."
            )
        self.results_info_label.setStyleSheet("color: green; font-weight: bold;")
        self.btn_clear.setEnabled(player_count > 0)

    def _append_fide_row(self, p: Dict[str, Any]) -> None:
        row = self.fide_table.rowCount()
        self.fide_table.insertRow(row)

        # Checkbox
        chk = QtWidgets.QTableWidgetItem()
        chk.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        chk.setCheckState(Qt.CheckState.Unchecked)
        self.fide_table.setItem(row, 0, chk)

        # Name
        name_item = QtWidgets.QTableWidgetItem(str(p.get("name") or ""))
        name_item.setData(Qt.ItemDataRole.UserRole, p)  # Store full player data
        self.fide_table.setItem(row, 1, name_item)

        # Other columns
        self.fide_table.setItem(
            row, 2, QtWidgets.QTableWidgetItem(str(p.get("fide_id") or ""))
        )
        self.fide_table.setItem(
            row, 3, QtWidgets.QTableWidgetItem(str(p.get("federation") or ""))
        )
        self.fide_table.setItem(
            row, 4, QtWidgets.QTableWidgetItem(str(p.get("title") or ""))
        )

        def fmt_rating(val):
            return "" if val in (None, 0) else str(val)

        self.fide_table.setItem(
            row, 5, QtWidgets.QTableWidgetItem(fmt_rating(p.get("standard_rating")))
        )
        self.fide_table.setItem(
            row, 6, QtWidgets.QTableWidgetItem(fmt_rating(p.get("rapid_rating")))
        )
        self.fide_table.setItem(
            row, 7, QtWidgets.QTableWidgetItem(fmt_rating(p.get("blitz_rating")))
        )
        self.fide_table.setItem(
            row, 8, QtWidgets.QTableWidgetItem(str(p.get("birth_year") or ""))
        )

        # Convert gender for display
        gender = p.get("gender")
        if not gender and str(p.get("title") or "").upper().startswith("W"):
            gender = "F"
        gender_display = ""
        if gender == "M":
            gender_display = "Male"
        elif gender == "F":
            gender_display = "Female"
        self.fide_table.setItem(row, 9, QtWidgets.QTableWidgetItem(gender_display))

        self.fide_table.setRowHeight(row, 22)

    def _show_fide_context_menu(self, position):
        """Show context menu for FIDE search results."""
        item = self.fide_table.itemAt(position)
        if not item:
            return

        menu = QtWidgets.QMenu()

        # Import action
        import_action = menu.addAction("Import Player")
        import_action.setEnabled(True)
        import_action.triggered.connect(self._use_selected_fide_player)

        # Copy actions for various fields
        menu.addSeparator()

        row = item.row()
        name_item = self.fide_table.item(row, 1)
        if name_item and name_item.text().strip():
            copy_name_action = menu.addAction(f"Copy Name: {name_item.text()}")
            copy_name_action.triggered.connect(
                lambda: self._copy_to_clipboard(name_item.text(), "Name")
            )

        fide_id_item = self.fide_table.item(row, 2)
        if fide_id_item and fide_id_item.text().strip():
            copy_id_action = menu.addAction(f"Copy FIDE ID: {fide_id_item.text()}")
            copy_id_action.triggered.connect(
                lambda: self._copy_to_clipboard(fide_id_item.text(), "FIDE ID")
            )

        # Show menu
        if menu.actions():
            menu.exec(self.fide_table.mapToGlobal(position))

    def _on_fide_selection_changed(self):
        """Handle FIDE table selection change."""
        selected_rows = self.fide_table.selectionModel().selectedRows()
        self.btn_use_selected.setEnabled(len(selected_rows) > 0)

    def _on_tournament_selection_changed(self):
        """Handle tournament table selection change."""
        selected_rows = self.tournament_table.selectionModel().selectedRows()
        self.btn_edit_tournament_player.setEnabled(len(selected_rows) > 0)

    def _use_selected_fide_player(self):
        """Use the selected FIDE player data in the details form."""
        selected_rows = self.fide_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # Get the first selected player
        row = selected_rows[0].row()
        name_item = self.fide_table.item(row, 1)
        if not name_item:
            return

        player_data = name_item.data(Qt.ItemDataRole.UserRole)
        if not player_data:
            return

        # Update details form
        self.name_edit.setText(player_data.get("name", ""))

        # Use standard rating as main rating, fallback to rapid, then blitz
        rating = (
            player_data.get("standard_rating")
            or player_data.get("rapid_rating")
            or player_data.get("blitz_rating")
            or 1000
        )
        self.rating_spin.setValue(rating)

        # Set gender
        gender = player_data.get("gender")
        if not gender and str(player_data.get("title") or "").upper().startswith("W"):
            gender = "F"

        if gender:
            gender_text = "Male" if gender == "M" else "Female" if gender == "F" else ""
            if gender_text:
                idx = self.gender_combo.findText(gender_text)
                if idx >= 0:
                    self.gender_combo.setCurrentIndex(idx)

        self.federation_edit.setText(player_data.get("federation", ""))

        # Set date of birth from birth year if available
        birth_year = player_data.get("birth_year")
        if birth_year:
            try:
                # Set date to January 1st of the birth year
                birth_date = QtCore.QDate(int(birth_year), 1, 1)
                if birth_date.isValid():
                    self.dob_edit.setDate(birth_date)
            except (ValueError, TypeError):
                pass  # Invalid birth year, skip setting DOB

        # Clear other fields that might not be available from FIDE
        self.phone_edit.setText("")
        self.email_edit.setText("")
        self.club_edit.setText("")

        # Show FIDE info (now editable) - Fix the FIDE ID field loading
        self.fide_id_edit.setText(str(player_data.get("fide_id", "") or ""))
        self.fide_title_edit.setText(str(player_data.get("title", "") or ""))
        self.fide_std_edit.setText(str(player_data.get("standard_rating", "") or ""))
        self.fide_rapid_edit.setText(str(player_data.get("rapid_rating", "") or ""))
        self.fide_blitz_edit.setText(str(player_data.get("blitz_rating", "") or ""))

        self.fide_group.setVisible(True)

        # Store the selected player data for later use
        self._selected_player_data = player_data
        self._player_data_changed = True  # Mark that we have new data to save

        # Switch to details tab
        self.tab_widget.setCurrentIndex(0)

        # Show brief success feedback using notification
        show_notification(
            self,
            f"Successfully imported: {player_data.get('name', 'Unknown')}",
            2500,
            "success",
        )

    def _edit_selected_tournament_player(self):
        """Edit the selected tournament player."""
        selected_rows = self.tournament_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        name_item = self.tournament_table.item(row, 0)
        if not name_item:
            return

        player_id = name_item.data(Qt.ItemDataRole.UserRole)
        player = self.tournament.players.get(player_id)
        if not player:
            return

        # Load player data into details form
        self.player_data = {
            "name": player.name,
            "rating": player.rating,
            "gender": player.gender,
            "date_of_birth": player.date_of_birth,
            "phone": player.phone or "",
            "email": player.email or "",
            "club": player.club or "",
            "federation": player.federation or "",
            "fide_id": getattr(player, "fide_id", None),
            "fide_title": getattr(player, "fide_title", None),
            "fide_standard": getattr(player, "fide_standard", None),
            "fide_rapid": getattr(player, "fide_rapid", None),
            "fide_blitz": getattr(player, "fide_blitz", None),
            "birth_year": getattr(player, "birth_year", None),
        }

        self._populate_details_form()

        # Switch to details tab
        self.tab_widget.setCurrentIndex(0)

    def accept(self):
        """Override accept to validate input."""
        # Always validate if we're on Player Details tab OR if we have imported data that needs to be saved
        current_tab = self.tab_widget.currentIndex()
        has_player_data = (
            self._player_data_changed
            or self._selected_player_data
            or bool(self.name_edit.text().strip())
        )

        if (
            current_tab == 0 or has_player_data
        ):  # Player Details tab or has player data to save
            if not self.name_edit.text().strip():
                # If on other tabs but have imported data, switch to details tab first
                if current_tab != 0:
                    self.tab_widget.setCurrentIndex(0)
                QtWidgets.QMessageBox.warning(
                    self, "Validation Error", "Player name cannot be empty."
                )
                self.name_edit.setFocus()
                return

            # Validate rating is reasonable
            rating = self.rating_spin.value()
            if rating < 0 or rating > 3500:
                if current_tab != 0:
                    self.tab_widget.setCurrentIndex(0)
                QtWidgets.QMessageBox.warning(
                    self, "Validation Error", "Rating must be between 0 and 3500."
                )
                self.rating_spin.setFocus()
                return

            # Validate date of birth
            if (
                self.dob_edit.date().isValid()
                and self.dob_edit.date() > QtCore.QDate.currentDate()
            ):
                if current_tab != 0:
                    self.tab_widget.setCurrentIndex(0)
                QtWidgets.QMessageBox.warning(
                    self, "Validation Error", "Date of birth cannot be in the future."
                )
                self.dob_edit.setFocus()
                return

            # Validate age makes sense (not too old or too young)
            dob_date = self.dob_edit.date()
            if dob_date != QtCore.QDate(2000, 1, 1):  # Not default date
                today = QtCore.QDate.currentDate()
                age = today.year() - dob_date.year()
                if age > 150 or age < 0:
                    if current_tab != 0:
                        self.tab_widget.setCurrentIndex(0)
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Validation Error",
                        f"Calculated age ({age}) seems unrealistic. Please check the date of birth.",
                    )
                    self.dob_edit.setFocus()
                    return

            # Validate email format if provided
            email = self.email_edit.text().strip()
            if email and "@" not in email:
                if current_tab != 0:
                    self.tab_widget.setCurrentIndex(0)
                QtWidgets.QMessageBox.warning(
                    self,
                    "Validation Error",
                    "Please enter a valid email address or leave empty.",
                )
                self.email_edit.setFocus()
                return

            # Validate FIDE ID if provided
            fide_id_text = self.fide_id_edit.text().strip()
            if fide_id_text:
                try:
                    fide_id = int(fide_id_text)
                    if fide_id <= 0:
                        raise ValueError("FIDE ID must be positive")
                except ValueError:
                    if current_tab != 0:
                        self.tab_widget.setCurrentIndex(0)
                    QtWidgets.QMessageBox.warning(
                        self, "Validation Error", "FIDE ID must be a positive number."
                    )
                    self.fide_id_edit.setFocus()
                    return

        elif current_tab != 0 and not has_player_data:
            # If we're on other tabs and no data has been imported/entered, ask user to go to details tab
            result = QtWidgets.QMessageBox.question(
                self,
                "Save Player",
                "To save a player, please fill out the details on the Player Details tab.\n\n"
                "Would you like to go to the Player Details tab now?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if result == QtWidgets.QMessageBox.StandardButton.Yes:
                self.tab_widget.setCurrentIndex(0)
                self.name_edit.setFocus()
            return
        super().accept()

    def closeEvent(self, event) -> None:
        """Ensure proper cleanup when dialog is closed."""
        self._abort_current_job()
        super().closeEvent(event)

    def reject(self) -> None:
        """Ensure proper cleanup when dialog is cancelled."""
        self._abort_current_job()
        super().reject()

    def get_player_data(self) -> Dict[str, Any]:
        """Get the player data from the form."""
        dob_qdate = self.dob_edit.date()

        # Get gender from combo box
        gender_text = self.gender_combo.currentText()
        gender = None
        if gender_text == "Male":
            gender = "M"
        elif gender_text == "Female":
            gender = "F"

        if self._selected_player_data:  # From FIDE
            return {
                "name": self.name_edit.text().strip(),
                "rating": self.rating_spin.value(),
                "gender": gender,
                "date_of_birth": (
                    dob_qdate.toString("yyyy-MM-dd")
                    if dob_qdate != QtCore.QDate(2000, 1, 1)
                    else ""
                ),
                "phone": self.phone_edit.text().strip(),
                "email": self.email_edit.text().strip(),
                "club": self.club_edit.text().strip(),
                "federation": self.federation_edit.text().strip(),
                "fide_id": (
                    int(self.fide_id_edit.text())
                    if self.fide_id_edit.text().isdigit()
                    else None
                ),
                "fide_title": self.fide_title_edit.text().strip() or None,
                "fide_standard": (
                    int(self.fide_std_edit.text())
                    if self.fide_std_edit.text().isdigit()
                    else None
                ),
                "fide_rapid": (
                    int(self.fide_rapid_edit.text())
                    if self.fide_rapid_edit.text().isdigit()
                    else None
                ),
                "fide_blitz": (
                    int(self.fide_blitz_edit.text())
                    if self.fide_blitz_edit.text().isdigit()
                    else None
                ),
                "birth_year": self._selected_player_data.get(
                    "birth_year"
                ),  # Keep from original FIDE data
            }
        elif any(
            [
                self.fide_id_edit.text(),
                self.fide_title_edit.text(),
                self.fide_std_edit.text(),
                self.fide_rapid_edit.text(),
                self.fide_blitz_edit.text(),
            ]
        ):  # Existing FIDE data
            return {
                "name": self.name_edit.text().strip(),
                "rating": self.rating_spin.value(),
                "gender": gender,
                "date_of_birth": (
                    dob_qdate.toString("yyyy-MM-dd")
                    if dob_qdate != QtCore.QDate(2000, 1, 1)
                    else ""
                ),
                "phone": self.phone_edit.text().strip(),
                "email": self.email_edit.text().strip(),
                "club": self.club_edit.text().strip(),
                "federation": self.federation_edit.text().strip(),
                "fide_id": (
                    int(self.fide_id_edit.text())
                    if self.fide_id_edit.text().isdigit()
                    else None
                ),
                "fide_title": self.fide_title_edit.text().strip() or None,
                "fide_standard": (
                    int(self.fide_std_edit.text())
                    if self.fide_std_edit.text().isdigit()
                    else None
                ),
                "fide_rapid": (
                    int(self.fide_rapid_edit.text())
                    if self.fide_rapid_edit.text().isdigit()
                    else None
                ),
                "fide_blitz": (
                    int(self.fide_blitz_edit.text())
                    if self.fide_blitz_edit.text().isdigit()
                    else None
                ),
            }
        else:  # Manual entry
            return {
                "name": self.name_edit.text().strip(),
                "rating": self.rating_spin.value(),
                "gender": gender,
                "date_of_birth": (
                    dob_qdate.toString("yyyy-MM-dd")
                    if dob_qdate != QtCore.QDate(2000, 1, 1)
                    else ""
                ),
                "phone": self.phone_edit.text().strip(),
                "email": self.email_edit.text().strip(),
                "club": self.club_edit.text().strip(),
                "federation": self.federation_edit.text().strip(),
            }

    def _abort_current_job(self) -> None:
        """Cooperatively cancel and cleanup the current background job."""
        if not self._thread or self._cleaning_up:
            return

        self._cleaning_up = True
        try:
            # Signal cancellation to search logic if active
            if hasattr(self, "_current_search_cancel_flag"):
                self._current_search_cancel_flag["cancelled"] = True

            # Interrupt worker (prevents emitting results afterwards)
            if self._worker:
                self._worker.interrupt()

            # Give the thread a chance to finish gracefully
            if self._thread.isRunning():
                if not self._thread.wait(500):  # wait 0.5s first
                    if not self._thread.wait(1500):  # total ~2s
                        self._thread.terminate()
                        self._thread.wait(200)

            # Disconnect signal if still connected
            if self._worker:
                try:
                    self._worker.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self._worker.deleteLater()

            # Clear busy UI
            self._set_fide_busy(False)
        finally:
            self._thread = None
            self._worker = None
            self._cleaning_up = False
            if hasattr(self, "_current_search_cancel_flag"):
                del self._current_search_cancel_flag
