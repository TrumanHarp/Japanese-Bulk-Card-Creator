from __future__ import annotations
from typing import Dict, List, Optional
from pathlib import Path
from aqt import mw
from aqt.qt import (
    QAction,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QComboBox,
    QDialogButtonBox,
    QAbstractItemView,
    Qt,
    QGridLayout,
    QPushButton,
    QWidget,
    QSizePolicy,
)
from aqt.utils import qconnect, showInfo
from anki.notes import Note
from .dictionary import Dictionary, DictEntry
from .kana_romaji import kana_to_romaji
from .jisho_audio import ensure_audio_in_media


DICT_DB_PATH = Path(__file__).parent / "user_files" / "jmdict.db"
dictionary = Dictionary(DICT_DB_PATH)

config = mw.addonManager.getConfig(__name__)


class PopupCombo(QComboBox):
    def __init__(self, max_height: int = 300, showVerticalScroll: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._max_height = max_height

        view = self.view()
        if showVerticalScroll:
            view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.setAutoScroll(False)

        view.setStyleSheet(
            """
            QScrollBar::sub-line:vertical,
            QScrollBar::add-line:vertical,
            QScrollBar::up-arrow:vertical,
            QScrollBar::down-arrow:vertical {
                height: 0px;
                width: 0px;
                margin: 0px;
                border: none;
            }
            """
        )

    def showPopup(self) -> None:
        # Let Qt build the popup
        super().showPopup()

        view = self.view()
        if not view:
            return
        popup = view.window()
        if not popup:
            return

        # Anchor the popup directly under the combo
        combo_rect = self.rect()
        bottom_left = self.mapToGlobal(combo_rect.bottomLeft())

        g = popup.geometry()
        height = min(g.height(), self._max_height)

        popup.setGeometry(
            bottom_left.x(),  # x: align left edges
            bottom_left.y(),  # y: directly below the combo
            g.width(),
            height,
        )

CARD_FIELD_OPTIONS: List[str] = [
    "None",
    "Expression",
    "Reading",
    "Romaji",
    "Glossary",
    "Glossary 2 (If Available)",
    "Glossary 3 (If Available)",
    "Audio",
]

class CardFormatDialog(QDialog):
    """
    Dialog to map note-type fields to logical roles (Expression, Reading, etc.).

    - Top: Note type dropdown
    - Middle: 2-column grid: Field | Value (FixedPopupCombo)
    - Bottom: OK / Cancel

    Mappings are stored per note type ID in a dict passed in from outside.
    """

    def __init__(
        self,
        parent: Optional[QDialog],
        mappings_by_notetype: Dict[int, Dict[str, str]],
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Card Format")
        self.resize(500, 400)

        # global font styling
        self.setStyleSheet("""
            QDialog {
                font-size: 11pt;
            }
            QLabel {
                font-size: 11pt;
            }
            QComboBox {
                font-size: 11pt;
            }
            QPushButton {
                font-size: 11pt;
            }
        """)

        self._mappings_by_notetype = mappings_by_notetype
        self._current_ntid: Optional[int] = None
        self._field_combos: Dict[str, PopupCombo] = {}
        self._fields_container: Optional[QWidget] = None
        
        self._main_layout = QVBoxLayout(self)

        # --- Note type selector row ---
        nt_row = QHBoxLayout()
        nt_label = QLabel("Note type:")
        nt_label.setStyleSheet("QLabel { font-weight: bold; }")
        self.nt_combo = PopupCombo(parent=self)  # you renamed this
        self.nt_combo.setMaximumWidth(300)

        nt_row.addWidget(nt_label)
        nt_row.addWidget(self.nt_combo, stretch=1)
        self._main_layout.addLayout(nt_row)

        # Load all note types into the dropdown
        self._models = mw.col.models.all()

        # Placeholder item at the top
        self.nt_combo.addItem("Select note type…", None)

        for m in self._models:
            self.nt_combo.addItem(m["name"], m["id"])

        self.nt_combo.currentIndexChanged.connect(self._on_notetype_changed)

        # Placeholder for fields grid; created when a real note type is chosen
        self._fields_container = None

        # --- Buttons row ---
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        ok_btn = QPushButton("OK", self)
        cancel_btn = QPushButton("Cancel", self)
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn.clicked.connect(self.reject)
        buttons_row.addWidget(ok_btn)
        buttons_row.addWidget(cancel_btn)
        self._main_layout.addLayout(buttons_row)

        # Start with the placeholder selected and no fields
        self.nt_combo.setCurrentIndex(0)
        self._current_ntid = None
        self.adjustSize()


    # --- helpers ---

    def _on_notetype_changed(self, index: int) -> None:
        # Save mapping for previous notetype (if any)
        self._save_current_mapping()

        ntid = self.nt_combo.itemData(index)

        # If placeholder ("Select note type…") is chosen
        if ntid is None:
            self._current_ntid = None

            # Clear any existing fields grid
            if self._fields_container is not None:
                self._main_layout.removeWidget(self._fields_container)
                self._fields_container.deleteLater()
                self._fields_container = None
                self._field_combos.clear()

            self.adjustSize()
            return

        # Real note type selected
        self._current_ntid = int(ntid)
        self._build_fields_for_notetype(self._current_ntid)


    def _save_current_mapping(self) -> None:
        """Save current UI field->role mapping into the shared dict."""
        if self._current_ntid is None or not self._field_combos:
            return

        mapping: Dict[str, str] = {}
        for field_name, combo in self._field_combos.items():
            value = combo.currentText().strip()
            if value:
                mapping[field_name] = value

        self._mappings_by_notetype[self._current_ntid] = mapping

    def _build_fields_for_notetype(self, ntid: int) -> None:
        """Rebuild the Field/Value grid for the given note type."""
        # Remove previous fields container, if any
        if self._fields_container is not None:
            self._main_layout.removeWidget(self._fields_container)
            self._fields_container.deleteLater()
            self._fields_container = None
            self._field_combos.clear()

        # Get notetype
        notetype = mw.col.models.get(ntid)
        if not notetype:
            return

        field_names = [fld["name"] for fld in notetype["flds"]]
        existing = self._mappings_by_notetype.get(ntid, {})

        container = QWidget(self)

        # don't let this container take all extra vertical space
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(10)

        # Header row
        header_field = QLabel("Field", container)
        header_value = QLabel("Value", container)
        header_field.setStyleSheet("QLabel { font-weight: bold; }")
        header_value.setStyleSheet("QLabel { font-weight: bold; }")
        grid.addWidget(header_field, 0, 0)
        grid.addWidget(header_value, 0, 1)

        # Rows: one per note-type field
        for row_idx, fname in enumerate(field_names, start=1):
            name_label = QLabel(fname, container)

            combo = PopupCombo(parent=container)
            for opt in CARD_FIELD_OPTIONS:
                combo.addItem(opt)

            # Restore existing mapping if present
            mapped_value = existing.get(fname)
            if mapped_value is not None:
                try:
                    idx = CARD_FIELD_OPTIONS.index(mapped_value)
                    combo.setCurrentIndex(idx)
                except ValueError:
                    pass

            grid.addWidget(name_label, row_idx, 0)
            grid.addWidget(combo, row_idx, 1)

            self._field_combos[fname] = combo

        self._fields_container = container
        # Layout order: [0] note type row, [1] fields grid, [2] buttons
        self._main_layout.insertWidget(1, container)

        # Let Qt recompute an appropriate dialog size
        self.adjustSize()


    def _on_ok(self) -> None:
        # Save current notetype mapping and close
        self._save_current_mapping()
        self.accept()

    @property
    def selected_notetype_id(self) -> Optional[int]:
        """Return the currently selected note type ID, or None."""
        return self._current_ntid

    @property
    def selected_notetype_name(self) -> Optional[str]:
        """Return the currently selected note type name, or None."""
        if self._current_ntid is None:
            return None
        return self.nt_combo.currentText() or None


class BulkWordsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent or mw)

        self._notetype_field_mappings: Dict[int, Dict[str, str]] = {}
        self._last_selected_notetype_id: Optional[int] = None

        self.setWindowTitle("Japanese Bulk Card Creator")
        self.resize(800, 600)

        main_layout = QVBoxLayout(self)

        # --- Deck selector ---
        deck_row = QHBoxLayout()
        deck_label = QLabel("Select Deck:")
        deck_label.setStyleSheet("QLabel { font-size: 11pt; font-weight: bold; }")

        self.deck_combo = PopupCombo(max_height=300, showVerticalScroll=True, parent=self)

        for deck in mw.col.decks.all():
            did = deck["id"]
            name = deck["name"]
            self.deck_combo.addItem(name, did)

        deck_row.addWidget(deck_label)
        deck_row.addWidget(self.deck_combo, stretch=1)
        main_layout.addLayout(deck_row)

        format_row = QHBoxLayout()

        self.card_format_btn = QPushButton("Card Format…", self)
        self.card_format_btn.setStyleSheet("QPushButton { font-size: 11pt; }")
        self.card_format_btn.clicked.connect(self._open_card_format_dialog)
        self.note_type_label = QLabel("Note Type: (none)", self)
        self.note_type_label.setStyleSheet("QLabel { font-size: 11pt; }")
        format_row.addWidget(self.card_format_btn)
        format_row.addSpacing(12)
        format_row.addWidget(self.note_type_label)
        format_row.addStretch(1)
        main_layout.addLayout(format_row)

        # --- Instructions + Text area ---
        label = QLabel(
            "Enter one word/phrase or kanji per line.\n"
            "Entries will be searched in a dictionary and cards created for matches.\n"
            "If a word is not found, it will be skipped.\n"
            "Note: Internet is required for Audio generation, not for dictionary lookup."
        )
        label.setWordWrap(True)
        label.setStyleSheet("QLabel { font-size: 10pt; }")
        main_layout.addWidget(label)

        self.text_edit = QTextEdit(self)
        self.text_edit.setStyleSheet("QTextEdit { font-size: 12pt; }")
        main_layout.addWidget(self.text_edit, stretch=1)

        # --- Buttons ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )

        # Keep references on self so we can enable/disable later
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)

        self._ok_button.setText("Submit")
        self._cancel_button.setText("Cancel")

        # Start with Submit disabled until Card Format is set
        self._ok_button.setEnabled(False)

        qconnect(buttons.accepted, self._on_submit_clicked)
        qconnect(buttons.rejected, self.reject)
        main_layout.addWidget(buttons)


    def _open_card_format_dialog(self) -> None:
        dlg = CardFormatDialog(self, self._notetype_field_mappings)
        if dlg.exec():
            ntid = dlg.selected_notetype_id
            ntname = dlg.selected_notetype_name

            if ntid is not None and ntname:
                self._last_selected_notetype_id = ntid
                self.note_type_label.setText(f"Note Type: {ntname}")

                # Check that we actually have a non-empty mapping for this note type
                mapping = self._notetype_field_mappings.get(ntid) or {}
                if mapping:
                    # We have at least one field mapped to Expression/Reading/etc.
                    self._ok_button.setEnabled(True)
                else:
                    # User picked a note type but left everything as "None"
                    self._ok_button.setEnabled(False)
            else:
                # No valid note type selected
                self.note_type_label.setText("Note Type: (none)")
                self._last_selected_notetype_id = None
                self._ok_button.setEnabled(False)



    
    def _collect_lines(self) -> List[str]:
        raw = self.text_edit.toPlainText()
        lines = [line.strip() for line in raw.splitlines()]
        return [line for line in lines if line]
    
    def _on_submit_clicked(self) -> None:
        # 1) Deck must be selected
        did = self.deck_combo.currentData()
        if did is None:
            showInfo("Please select a deck.")
            return
        did = int(did)

        # 2) Note type + mapping must be chosen in Card Format
        ntid = getattr(self, "_last_selected_notetype_id", None)
        if ntid is None:
            showInfo("Please configure Card Format and choose a note type first.")
            return

        mapping = self._notetype_field_mappings.get(ntid)
        if not mapping:
            showInfo("No field mapping found for that note type.\n\nOpen Card Format and assign fields.")
            return

        notetype = mw.col.models.get(ntid)
        if not notetype:
            showInfo("Could not load the selected note type.")
            return

        words = self._collect_lines()
        if not words:
            showInfo("No non-empty lines found.")
            return

        # 3) Prepare collection: set current deck + model (good practice)
        mw.col.decks.set_current(did)
        mw.col.models.set_current(notetype)

        created = 0
        not_found: list[str] = []
        lookup_errors: list[str] = []

        mw.checkpoint("Japanese Bulk Card Creator")

        for term in words:
            try:
                entry = dictionary.lookup(term)
            except Exception as e:
                lookup_errors.append(f"{term}: {e}")
                continue

            if entry is None:
                not_found.append(term)
                continue

            # Create a new note of the chosen note type
            note = mw.col.new_note(notetype)

            # Fill fields according to mapping
            for field_name, role in mapping.items():
                # Only set field if it actually exists in the notetype
                if field_name not in note:
                    continue

                value = ""
                if role == "Expression":
                    value = entry.expression
                elif role == "Reading":
                    # fall back to expression if reading is missing
                    value = entry.reading or entry.expression
                elif role == "Glossary":
                    if entry.glosses:
                        value = entry.glosses[0]
                elif role.startswith("Glossary 2"):
                    if len(entry.glosses) > 1:
                        value = entry.glosses[1]
                elif role.startswith("Glossary 3"):
                    if len(entry.glosses) > 2:
                        value = entry.glosses[2]
                elif role == "Romaji":
                    kana = entry.reading or entry.expression
                    use_macrons = config['romaji_use_macrons']
                    use_m_before_bmp = config['romaji_use_m_before_bmp']
                    value = kana_to_romaji(kana, use_macrons=use_macrons, use_m_before_bmp=use_m_before_bmp)
                elif role == "Audio":
                    audio_key = entry.reading or entry.expression
                    if audio_key:
                        fname = ensure_audio_in_media(audio_key)
                        if fname:
                            value = f"[sound:{fname}]"
                        else:
                            value = ""
                    else:
                        value = ""
                else:
                    value = ""

                if value:
                    note[field_name] = value

            # Add note only if it has at least one non-empty field
            if any(note[field] for field in note.keys()):
                mw.col.add_note(note, did)
                created += 1
            else:
                # nothing filled? treat as not-found-ish
                not_found.append(term)

        mw.reset()

        # 4) Show a summary
        msg_lines = [f"Created {created} cards."]
        if not_found:
            msg_lines.append("")
            msg_lines.append("No dictionary entry for:")
            msg_lines.append(", ".join(not_found[:20]))
            if len(not_found) > 20:
                msg_lines.append(f"...and {len(not_found) - 20} more.")

        if lookup_errors:
            msg_lines.append("")
            msg_lines.append("Lookup errors:")
            msg_lines.extend(lookup_errors[:5])
            if len(lookup_errors) > 5:
                msg_lines.append(f"...and {len(lookup_errors) - 5} more.")

        showInfo("\n".join(msg_lines))

        self.accept()



def on_tools_menu_action() -> None:
    dlg = BulkWordsDialog(mw)
    dlg.exec()


action = QAction("Japanese Bulk Card Creator", mw)
qconnect(action.triggered, on_tools_menu_action)
mw.form.menuTools.addAction(action)
