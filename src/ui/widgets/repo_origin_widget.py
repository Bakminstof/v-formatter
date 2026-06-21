from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from core.models import AppInfoModel
from ui.i18n import I18n


class RepoOriginWidget(QWidget):
    def __init__(
        self,
        app_info: AppInfoModel,
        i18n: I18n,
        origin_icon_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_info = app_info
        self._i18n = i18n
        self._origin_icon_path = origin_icon_path

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        button_style = """
            QPushButton {
                color: #4a9eff;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #2a7fff;
                text-decoration: underline;
            }
        """

        if self._app_info.orign_url:
            btn_github = QPushButton(self._i18n.t("origin.repo"))
            btn_github.setFlat(True)
            btn_github.setCursor(Qt.PointingHandCursor)
            btn_github.setStyleSheet(button_style)
            btn_github.setToolTip(self._i18n.t("origin.repo_tooltip"))
            btn_github.clicked.connect(lambda: webbrowser.open(self._app_info.orign_url))

            if self._origin_icon_path:
                icon_path = Path(self._origin_icon_path)
                if icon_path.exists():
                    btn_github.setIcon(QIcon(icon_path.as_posix()))
                    btn_github.setIconSize(
                        btn_github.fontMetrics().size(Qt.TextSingleLine, "X") * 1.5
                    )

            layout.addWidget(btn_github)

        if self._app_info.orign_url and self._app_info.feedback_url:
            separator = QLabel("|")
            separator.setStyleSheet("color: #888; font-size: 14px;")
            separator.setFixedWidth(12)
            separator.setAlignment(Qt.AlignCenter)
            layout.addWidget(separator)

        if self._app_info.feedback_url:
            btn_feedback = QPushButton(self._i18n.t("origin.feedback"))
            btn_feedback.setFlat(True)
            btn_feedback.setCursor(Qt.PointingHandCursor)
            btn_feedback.setStyleSheet(button_style)
            btn_feedback.setToolTip(self._i18n.t("origin.feedback_tooltip"))
            btn_feedback.clicked.connect(lambda: webbrowser.open(self._app_info.feedback_url))
            layout.addWidget(btn_feedback)

        self.setLayout(layout)


class RepoOriginManager:
    def __init__(
        self,
        app_info: AppInfoModel,
        i18n: I18n,
        origin_icon_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.widget = RepoOriginWidget(app_info, i18n, origin_icon_path, parent)
