from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from gambitpairing.tournament import Tournament


class PlayerManagementDialog(QtWidgets.QDialog):

    FIELD_MAX_HEIGHT = 40

    def __init__(self, parent=None, tournament: Tournament = None):
        self.tournament = tournament
        super().__init__(parent)

    def _mark_player_data_changed(self) -> None:
        self._player_data_changed = True

    def _make_line_edit(self, tooltip: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setToolTip(tooltip)
        edit.setMaximumHeight(self.FIELD_MAX_HEIGHT)
        edit.textChanged.connect(self._mark_player_data_changed)
        return edit

    def _create_copy_button_for_value(
        self, tooltip: str, value_getter, field_name: str
    ) -> QPushButton:
        """Create a copy button that copies the value from a callable (e.g., spinbox.value)."""
        btn = QPushButton()
        btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        btn.setToolTip(tooltip)
        btn.setFixedSize(32, 32)
        icon = None
        try:
            icon = QtGui.QIcon.fromTheme("edit-copy")
        except Exception:
            icon = None
        if not icon or icon.isNull():
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
                QPushButton:hover { background: #e0e4ea; color: #222; }
                QPushButton:pressed { background: #d0d4da; }
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
                QPushButton:hover { background: #e0e4ea; }
                QPushButton:pressed { background: #d0d4da; }
                """
            )
        btn.clicked.connect(
            lambda: self._copy_to_clipboard(str(value_getter()), field_name)
        )
        return btn

    def _create_details_tab(self) -> QtWidgets.QWidget:
        """Create the player details editing tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Basic information group
        basic_group = QtWidgets.QGroupBox("Basic Information")
        form = QtWidgets.QFormLayout(basic_group)

        # Name with copy button
        name_layout = QtWidgets.QHBoxLayout()
        self.name_edit = self._make_line_edit("Full name of the player")
        name_layout.addWidget(self.name_edit)
        name_layout.addWidget(
            self._create_copy_button("Copy name to clipboard", self.name_edit, "Name")
        )
        form.addRow("Name:", name_layout)

        # Rating with copy button (no hidden QLineEdit hack)
        rating_layout = QtWidgets.QHBoxLayout()
        self.rating_spin = QtWidgets.QSpinBox()
        self.rating_spin.setRange(0, 3500)
        self.rating_spin.setValue(1000)
        self.rating_spin.setMaximumHeight(self.FIELD_MAX_HEIGHT)
        self.rating_spin.setToolTip("Player's rating (0-3500)")
        rating_layout.addWidget(self.rating_spin)
        rating_layout.addWidget(
            self._create_copy_button_for_value(
                "Copy rating to clipboard", lambda: self.rating_spin.value(), "Rating"
            )
        )
        form.addRow("Rating:", rating_layout)

        # Gender and Age on the same line
        gender_age_layout = QtWidgets.QHBoxLayout()
        self.gender_combo = QtWidgets.QComboBox()
        self.gender_combo.addItems(["", "Male", "Female"])
        self.gender_combo.setMaximumHeight(self.FIELD_MAX_HEIGHT)
        self.gender_combo.setToolTip("Select gender (optional)")
        gender_age_layout.addWidget(QtWidgets.QLabel("Gender:"))
        gender_age_layout.addWidget(self.gender_combo)

        # Removed unused self.age_label
        self.age_spin_box = QSpinBox()
        self.age_spin_box.setRange(0, 120)  # typical human age range
        self.age_spin_box.setValue(25)  # default value
        gender_age_layout.addSpacing(10)
        gender_age_layout.addWidget(QtWidgets.QLabel("Age:"))
        gender_age_layout.addWidget(self.age_spin_box)
        gender_age_layout.addStretch()
        form.addRow(gender_age_layout)

        layout.addWidget(basic_group)

        # Contact information group
        contact_group = QtWidgets.QGroupBox("Contact Information (Optional)")
        contact_form = QtWidgets.QFormLayout(contact_group)

        # Phone with copy button
        phone_layout = QtWidgets.QHBoxLayout()
        self.phone_edit = self._make_line_edit("Phone number (optional)")
        phone_layout.addWidget(self.phone_edit)
        phone_layout.addWidget(
            self._create_copy_button(
                "Copy phone to clipboard", self.phone_edit, "Phone"
            )
        )
        contact_form.addRow("Phone:", phone_layout)

        # Email with copy button
        email_layout = QtWidgets.QHBoxLayout()
        self.email_edit = self._make_line_edit("Email address (optional)")
        email_layout.addWidget(self.email_edit)
        email_layout.addWidget(
            self._create_copy_button(
                "Copy email to clipboard", self.email_edit, "Email"
            )
        )
        contact_form.addRow("Email:", email_layout)

        # Club with copy button
        club_layout = QtWidgets.QHBoxLayout()
        self.club_edit = self._make_line_edit("Chess club (optional)")
        club_layout.addWidget(self.club_edit)
        club_layout.addWidget(
            self._create_copy_button("Copy club to clipboard", self.club_edit, "Club")
        )
        contact_form.addRow("Club:", club_layout)

        # Federation with copy button
        federation_layout = QtWidgets.QHBoxLayout()
        self.federation_edit = self._make_line_edit("Federation/Country (optional)")
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
        self.fide_id_edit = self._make_line_edit("FIDE ID (editable)")
        fide_id_layout.addWidget(self.fide_id_edit)
        fide_id_layout.addWidget(
            self._create_copy_button(
                "Copy FIDE ID to clipboard", self.fide_id_edit, "FIDE ID"
            )
        )
        fide_form.addRow("FIDE ID:", fide_id_layout)

        # Title with copy button
        title_layout = QtWidgets.QHBoxLayout()
        self.fide_title_edit = self._make_line_edit("FIDE Title (editable)")
        title_layout.addWidget(self.fide_title_edit)
        title_layout.addWidget(
            self._create_copy_button(
                "Copy title to clipboard", self.fide_title_edit, "Title"
            )
        )
        fide_form.addRow("Title:", title_layout)

        # Standard rating with copy button
        std_layout = QtWidgets.QHBoxLayout()
        self.fide_std_edit = self._make_line_edit("Standard rating (editable)")
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
        self.fide_rapid_edit = self._make_line_edit("Rapid rating (editable)")
        rapid_layout.addWidget(self.fide_rapid_edit)
        rapid_layout.addWidget(
            self._create_copy_button(
                "Copy rapid rating to clipboard", self.fide_rapid_edit, "Rapid Rating"
            )
        )
        fide_form.addRow("Rapid:", rapid_layout)

        # Blitz rating with copy button
        blitz_layout = QtWidgets.QHBoxLayout()
        self.fide_blitz_edit = self._make_line_edit("Blitz rating (editable)")
        blitz_layout.addWidget(self.fide_blitz_edit)
        blitz_layout.addWidget(
            self._create_copy_button(
                "Copy blitz rating to clipboard", self.fide_blitz_edit, "Blitz Rating"
            )
        )
        fide_form.addRow("Blitz:", blitz_layout)

        layout.addWidget(self.fide_group)
        layout.addStretch()

        # does not populate with data yet
        return widget
