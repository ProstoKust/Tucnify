import asyncio
import json
import os
from pathlib import Path
import sys
import winreg

import markdown
import nest_asyncio
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from Bot import bot, dp, generate_gemini_response, MESSAGES

nest_asyncio.apply()

class BotThread(QThread):
    error_occurred = pyqtSignal(str)
    
    def __init__(self, telegram_token, gemini_token):
        super().__init__()
        self.telegram_token = telegram_token
        self.gemini_token = gemini_token
        self._is_running = True
        self.loop = None
        self.bot = None
    
    def run(self):
        try:
            import Bot
            
            Bot.API_TOKEN = self.telegram_token
            Bot.GEMINI_API_KEY = self.gemini_token
            Bot.GEMINI_API_URL = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_token}'
            
            self.bot = Bot.Bot(token=self.telegram_token)
            Bot.bot = self.bot
            Bot.dp = Bot.Dispatcher()
            
            @Bot.dp.message(Bot.Command("start"))
            async def cmd_start(message: Bot.types.Message):
                await message.answer(Bot.WELCOME_MESSAGE, parse_mode=Bot.ParseMode.MARKDOWN)

            @Bot.dp.message()
            async def handle_message(message: Bot.types.Message):
                user_input = message.text
                await self.bot.send_chat_action(message.chat.id, 'typing')
                response = await Bot.generate_gemini_response(user_input)
                if len(response) > 4096:
                    response = response[:4090] + "..."
                await message.answer(response, parse_mode=Bot.ParseMode.MARKDOWN)
            
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            while self._is_running:
                try:
                    self.loop.run_until_complete(Bot.dp.start_polling(self.bot))
                except Exception as e:
                    if not self._is_running:
                        break
                    self.error_occurred.emit(str(e))
                    break
            
            if self.bot and hasattr(self.bot, 'session'):
                self.loop.run_until_complete(self.bot.session.close())
            
            Bot.bot = None
            Bot.dp = Bot.Dispatcher()
            self.bot = None
                
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def stop(self):
        self._is_running = False
        if self.bot and hasattr(self.bot, 'session'):
            asyncio.run_coroutine_threadsafe(self.bot.session.close(), self.loop)

class BotConfig:
    def __init__(self, name):
        self.name = name
        self.telegram_token = ""
        self.gemini_token = ""
        self.thread = None
        self.is_active = False

class BotTab(QWidget):
    def __init__(self, parent=None, name="New Bot"):
        super().__init__(parent)
        self.name = name
        self.is_active = False
        self.thread = None
        self.has_unsaved_changes = False
        self.bot_messages = dict(MESSAGES)
        self.setup_ui()
        self.save_initial_state()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        settings_layout = QGridLayout()
        
        name_label = QLabel("Bot Name:")
        self.name_input = QLineEdit(self.name)
        self.name_input.textChanged.connect(self.on_settings_changed)
        settings_layout.addWidget(name_label, 0, 0)
        settings_layout.addWidget(self.name_input, 0, 1)
        
        telegram_label = QLabel("Telegram Token:")
        self.telegram_input = QLineEdit()
        self.telegram_input.setPlaceholderText("Enter Telegram Bot Token")
        self.telegram_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.telegram_input.textChanged.connect(self.on_settings_changed)
        settings_layout.addWidget(telegram_label, 1, 0)
        settings_layout.addWidget(self.telegram_input, 1, 1)
        
        show_telegram = QPushButton("Show/Hide")
        show_telegram.setFixedWidth(30)
        show_telegram.clicked.connect(lambda: self.toggle_password_visibility(self.telegram_input))
        settings_layout.addWidget(show_telegram, 1, 2)
        
        gemini_label = QLabel("Gemini Token:")
        self.gemini_input = QLineEdit()
        self.gemini_input.setPlaceholderText("Enter Gemini API Key")
        self.gemini_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_input.textChanged.connect(self.on_settings_changed)
        settings_layout.addWidget(gemini_label, 2, 0)
        settings_layout.addWidget(self.gemini_input, 2, 1)
        
        show_gemini = QPushButton("Show/Hide")
        show_gemini.setFixedWidth(30)
        show_gemini.clicked.connect(lambda: self.toggle_password_visibility(self.gemini_input))
        settings_layout.addWidget(show_gemini, 2, 2)
        
        control_layout = QHBoxLayout()
        
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.setStyleSheet("""
            QLabel {
                background-color: #3c3f44;
                border-radius: 6px;
            }
        """)
        
        self.start_button = QPushButton("Start Bot")
        self.stop_button = QPushButton("Stop Bot")
        self.stop_button.setEnabled(False)
        self.settings_button = QPushButton("More Settings")
        self.settings_button.clicked.connect(self.show_settings)
        self.save_button = QPushButton("Save Settings")
        self.save_button.setEnabled(False)
        
        self.start_button.clicked.connect(self.start_bot)
        self.stop_button.clicked.connect(self.stop_bot)
        self.save_button.clicked.connect(self.save_settings)
        
        control_layout.addWidget(self.status_indicator)
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.settings_button)
        control_layout.addWidget(self.save_button)
        control_layout.addStretch()
        
        layout.addLayout(settings_layout)
        layout.addLayout(control_layout)
        layout.addStretch()

    def save_initial_state(self):
        self.initial_state = {
            "name": self.name_input.text(),
            "telegram": self.telegram_input.text(),
            "gemini": self.gemini_input.text()
        }

    def on_settings_changed(self):
        current_state = {
            "name": self.name_input.text(),
            "telegram": self.telegram_input.text(),
            "gemini": self.gemini_input.text()
        }
        
        self.has_unsaved_changes = current_state != self.initial_state
        self.save_button.setEnabled(self.has_unsaved_changes)
        
        main_window = self.window()
        if isinstance(main_window, ChatWindow):
            main_window.update_input_state()

    def start_bot(self):
        if not self.telegram_input.text().strip():
            QMessageBox.warning(self, "Warning", "Please enter Telegram Bot Token!")
            return
            
        if not self.gemini_input.text().strip():
            QMessageBox.warning(self, "Warning", "Please enter Gemini API Key!")
            return
            
        self.is_active = True
        self.thread = BotThread(
            self.telegram_input.text().strip(),
            self.gemini_input.text().strip()
        )
        self.thread.error_occurred.connect(self.handle_error)
        self.thread.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.telegram_input.setEnabled(False)
        self.gemini_input.setEnabled(False)
        self.status_indicator.setStyleSheet("""
            QLabel {
                background-color: #2ecc71;
                border-radius: 6px;
            }
        """)

    def stop_bot(self):
        if self.thread:
            self.thread.stop()
            self.thread.wait()
            self.thread = None
        
        self.is_active = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.telegram_input.setEnabled(True)
        self.gemini_input.setEnabled(True)
        self.status_indicator.setStyleSheet("""
            QLabel {
                background-color: #3c3f44;
                border-radius: 6px;
            }
        """)

    def handle_error(self, error_message):
        QMessageBox.critical(self, "Error", f"Bot error: {error_message}")
        self.stop_bot()

    def save_settings(self):
        settings = {
            "name": self.name_input.text().strip(),
            "telegram_token": self.telegram_input.text().strip(),
            "gemini_token": self.gemini_input.text().strip(),
            "messages": {
                'welcome': MESSAGES['welcome'],
                'no_api_key': MESSAGES['no_api_key'],
                'api_error': MESSAGES['api_error'],
                'process_error': MESSAGES['process_error']
            }
        }
        
        main_window = self.window()
        if isinstance(main_window, ChatWindow):
            main_window.save_bot_settings(self.parent().indexOf(self), settings)
            
        self.save_initial_state()
        self.has_unsaved_changes = False
        self.save_button.setEnabled(False)

    def show_settings(self):
        dialog = SettingsDialog(self, self.bot_messages)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.bot_messages = dialog.get_settings()
            if self.is_active:
                self.stop_bot()
                self.start_bot()

    def toggle_password_visibility(self, input_field):
        if input_field.echoMode() == QLineEdit.EchoMode.Password:
            input_field.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            input_field.setEchoMode(QLineEdit.EchoMode.Password)

class SettingsDialog(QDialog):
    def __init__(self, parent=None, messages=None):
        super().__init__(parent)
        self.setWindowTitle("Bot Settings")
        self.setMinimumWidth(500)
        
        if messages is None:
            messages = MESSAGES
        
        layout = QVBoxLayout(self)
        
        welcome_group = QGroupBox("Messages")
        welcome_layout = QVBoxLayout()
        
        welcome_label = QLabel("Welcome Message:")
        self.welcome_input = QTextEdit()
        self.welcome_input.setPlaceholderText("Enter welcome message")
        self.welcome_input.setText(messages['welcome'])
        
        no_key_label = QLabel("No API Key Error:")
        self.no_key_input = QLineEdit()
        self.no_key_input.setText(messages['no_api_key'])
        
        api_error_label = QLabel("API Error:")
        self.api_error_input = QLineEdit()
        self.api_error_input.setText(messages['api_error'])
        
        process_error_label = QLabel("Process Error:")
        self.process_error_input = QLineEdit()
        self.process_error_input.setText(messages['process_error'])
        
        welcome_layout.addWidget(welcome_label)
        welcome_layout.addWidget(self.welcome_input)
        welcome_layout.addWidget(no_key_label)
        welcome_layout.addWidget(self.no_key_input)
        welcome_layout.addWidget(api_error_label)
        welcome_layout.addWidget(self.api_error_input)
        welcome_layout.addWidget(process_error_label)
        welcome_layout.addWidget(self.process_error_input)
        welcome_group.setLayout(welcome_layout)
        
        buttons = QHBoxLayout()
        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")
        
        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        
        layout.addWidget(welcome_group)
        layout.addLayout(buttons)
    
    def get_settings(self):
        return {
            'welcome': self.welcome_input.toPlainText(),
            'no_api_key': self.no_key_input.text(),
            'api_error': self.api_error_input.text(),
            'process_error': self.process_error_input.text()
        }

class ChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tucnify")
        self.setMinimumSize(900, 600)
        
        app_icon = QIcon("resources/app.png")
        self.setWindowIcon(app_icon)
        QApplication.setWindowIcon(app_icon)
        
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #141417;
            }
            QFrame {
                background-color: #18191D;
                border-radius: 8px;
            }
            QLineEdit {
                background-color: #202126;
                border: 2px solid #202126;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
                font-size: 13px;
                selection-background-color: #575AFD;
            }
            QLineEdit:focus {
                background-color: #292a30;
                border: 2px solid #575AFD;
            }
            QPushButton {
                background-color: #575AFD;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7783FF;
            }
            QPushButton:disabled {
                background-color: #202126;
                color: #72767d;
            }
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
            }
            QTextEdit {
                selection-background-color: #575AFD;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background: #202126;
                color: #dcddde;
                padding: 8px 12px;
                border: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #292a30;
            }
            QTabBar::tab:hover {
                background: #383942;
            }
        """)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        self.tab_widget.setCornerWidget(self.create_corner_buttons(), Qt.Corner.TopRightCorner)
        
        self.add_bot_tab()
        
        main_layout.addWidget(self.tab_widget)
        
        chat_frame = QFrame()
        chat_layout = QVBoxLayout(chat_frame)
        
        tucnify_frame = QFrame()
        tucnify_layout = QVBoxLayout(tucnify_frame)
        tucnify_layout.setContentsMargins(15, 15, 15, 15)
        tucnify_layout.setSpacing(8)
        
        tucnify_header = QHBoxLayout()
        tucnify_avatar = QLabel()
        tucnify_pixmap = QPixmap("resources/tucnify.png")
        rounded_tucnify = self.get_rounded_pixmap(tucnify_pixmap, 32)
        tucnify_avatar.setPixmap(rounded_tucnify)
        tucnify_avatar.setStyleSheet("""
            QLabel {
                min-width: 32px;
                min-height: 32px;
                max-width: 32px;
                max-height: 32px;
            }
        """)
        self.tucnify_name = QLabel("Tucnify")
        self.tucnify_name.setStyleSheet("color: #7783FF; font-weight: bold; font-size: 15px;")
        tucnify_header.addWidget(tucnify_avatar)
        tucnify_header.addWidget(self.tucnify_name)
        tucnify_header.addStretch()
        tucnify_layout.addLayout(tucnify_header)
        
        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        self.response_area.setMinimumHeight(350)
        self.response_area.setStyleSheet("""
            QTextEdit {
                background-color: #18191D;
                color: #dcddde;
                border: none;
                border-radius: 4px;
                padding: 16px;
                font-size: 14px;
                margin-bottom: 8px;
                selection-background-color: #575AFD;
            }
            QTextEdit pre {
                background-color: #1E1F22;
                border-radius: 4px;
                padding: 12px;
                font-family: monospace;
                font-size: 13px;
                line-height: 1.4;
                margin: 8px 0;
                white-space: pre-wrap;
                word-wrap: break-word;
                border-left: 3px solid #7783FF;
            }
            QScrollBar:vertical {
                background-color: #202126;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #292a30;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        tucnify_layout.addWidget(self.response_area)
        
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        
        user_avatar = QLabel()
        avatar_path = self.get_user_avatar()
        pixmap = QPixmap(avatar_path)
        rounded_pixmap = self.get_rounded_pixmap(pixmap, 32)
        user_avatar.setPixmap(rounded_pixmap)
        user_avatar.setStyleSheet("""
            QLabel {
                min-width: 32px;
                min-height: 32px;
                max-width: 32px;
                max-height: 32px;
            }
        """)
        input_layout.addWidget(user_avatar)
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type your message here")
        self.message_input.setEnabled(False)
        
        self.send_button = QPushButton("Send")
        self.send_button.setEnabled(False)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        tucnify_layout.addLayout(input_layout)
        
        chat_layout.addWidget(tucnify_frame)
        
        main_layout.addWidget(chat_frame)
        
        self.send_button.clicked.connect(self.send_message)
        self.message_input.returnPressed.connect(self.send_message)

        self.tab_widget.currentChanged.connect(self.update_input_state)

        self.load_settings()

    def create_corner_buttons(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        add_button = self.create_add_tab_button()
        about_button = self.create_about_button()
        
        layout.addWidget(add_button)
        layout.addWidget(about_button)
        
        return widget
    
    def create_add_tab_button(self):
        button = QPushButton("+")
        button.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 5px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        button.clicked.connect(self.add_bot_tab)
        return button
    
    def create_about_button(self):
        button = QPushButton("i")
        button.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 5px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        button.clicked.connect(self.show_about)
        return button
    
    def show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def add_bot_tab(self):
        tab = BotTab(self.tab_widget, f"Bot {self.tab_widget.count() + 1}")
        self.tab_widget.addTab(tab, tab.name)
        self.tab_widget.setCurrentWidget(tab)

    def close_tab(self, index):
        if self.tab_widget.count() > 1:
            tab = self.tab_widget.widget(index)
            
            if tab.is_active:
                reply = QMessageBox.question(
                    self,
                    "Confirm Close",
                    "This bot is currently running. Are you sure you want to close it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
                tab.stop_bot()
            
            if tab.has_unsaved_changes:
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "There are unsaved changes. Do you want to save them before closing?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                if reply == QMessageBox.StandardButton.Yes:
                    tab.save_settings()
            
            config_file = "Bot.settings"
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    settings = json.load(f)
                
                if index < len(settings):
                    settings.pop(index)
                    with open(config_file, 'w') as f:
                        json.dump(settings, f, indent=4)
            
            self.tab_widget.removeTab(index)
        else:
            QMessageBox.warning(self, "Warning", "Cannot close the last tab!")

    def update_input_state(self):
        current_tab = self.tab_widget.currentWidget()
        if current_tab:
            has_gemini_token = bool(current_tab.gemini_input.text().strip())
            self.message_input.setEnabled(has_gemini_token)
            self.send_button.setEnabled(has_gemini_token)
            if has_gemini_token:
                self.message_input.setPlaceholderText("Type your message here")
            else:
                self.message_input.setPlaceholderText("Enter Gemini API key in the settings above to start chatting")
            
            bot_name = current_tab.name_input.text().strip() or "Unnamed Bot"
            self.setWindowTitle(f"Tucnify ({bot_name})")
            self.tucnify_name.setText(f"Tucnify ({bot_name})")

    def send_message(self):
        current_tab = self.tab_widget.currentWidget()
        gemini_token = current_tab.gemini_input.text().strip()
        
        if not gemini_token:
            QMessageBox.warning(self, "Warning", "Please enter Gemini API key first!")
            return
            
        message = self.message_input.text().strip()
        if not message:
            return
        
        self.message_input.clear()
        self.send_button.setEnabled(False)
        self.message_input.setEnabled(False)
        self.response_area.setText("Waiting for response...")
        
        import Bot
        Bot.GEMINI_API_KEY = gemini_token
        
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(generate_gemini_response(message))
        
        html = markdown.markdown(
            response,
            extensions=[
                'markdown.extensions.fenced_code',
                'markdown.extensions.tables',
                'markdown.extensions.nl2br',
                'markdown.extensions.sane_lists'
            ]
        )
        
        styled_html = f"""
        <style>
            code {{
                background-color: #1E1F22;
                padding: 2px 4px;
                border-radius: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
            }}
            pre {{
                background-color: #1E1F22;
                border-radius: 4px;
                padding: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.4;
                margin: 8px 0;
                white-space: pre-wrap;
                word-wrap: break-word;
                border-left: 3px solid #7783FF;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
            }}
            blockquote {{
                border-left: 3px solid #7783FF;
                margin: 8px 0;
                padding-left: 12px;
                color: #a0a0a0;
            }}
            table {{
                border-collapse: collapse;
                margin: 8px 0;
                width: 100%;
            }}
            th, td {{
                border: 1px solid #404040;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #1E1F22;
            }}
            a {{
                color: #7783FF;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            ul, ol {{
                margin: 8px 0;
                padding-left: 24px;
            }}
            hr {{
                border: none;
                border-top: 1px solid #404040;
                margin: 16px 0;
            }}
        </style>
        {html}
        """
        
        self.response_area.setHtml(styled_html)
        self.send_button.setEnabled(True)
        self.message_input.setEnabled(True)
        self.message_input.setFocus()

    def get_user_avatar(self):
        print("Looking for avatar in Windows...")
        
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\AccountPicture\Users") as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    sid = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, sid) as user_key:
                        try:
                            image_path = winreg.QueryValueEx(user_key, "Image96")[0]
                            if os.path.exists(image_path):
                                print(f"Found avatar in registry: {image_path}")
                                return image_path
                        except:
                            pass
        except Exception as e:
            print(f"Registry error: {e}")

        paths = [
            os.path.expandvars(r'%USERPROFILE%\AppData\Local\Temp\AccountPictures'),
            os.path.expandvars(r'%USERPROFILE%\AppData\Roaming\Microsoft\Windows\AccountPictures'),
            os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Windows\AccountPictures'),
            os.path.expandvars(r'%APPDATA%\Microsoft\Windows\AccountPictures')
        ]

        print("Checking standard paths...")
        for path in paths:
            print(f"Checking path: {path}")
            if os.path.exists(path):
                print(f"Path exists: {path}")
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.bmp']:
                    try:
                        files = list(Path(path).glob(ext))
                        if files:
                            print(f"Found avatar: {files[0]}")
                            return str(files[0])
                    except Exception as e:
                        print(f"Error while searching in {path}: {e}")
        
        print("No avatar found, using default")
        return "resources/user.png"

    def get_rounded_pixmap(self, pixmap, size):
        rounded = QPixmap(size, size)
        rounded.fill(Qt.GlobalColor.transparent)
        
        mask = QPainter(rounded)
        mask.setRenderHint(QPainter.RenderHint.Antialiasing)
        mask.setBrush(Qt.GlobalColor.white)
        mask.setPen(Qt.PenStyle.NoPen)
        mask.drawEllipse(0, 0, size, size)
        mask.end()
        
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(0, 0, rounded)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.drawPixmap(0, 0, pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        painter.end()
        
        return result

    def save_bot_settings(self, index, settings):
        config_file = "Bot.settings"
        all_settings = []
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                try:
                    all_settings = json.load(f)
                except:
                    pass
        
        while len(all_settings) <= index:
            all_settings.append({})
        all_settings[index] = settings
        
        with open(config_file, 'w') as f:
            json.dump(all_settings, f, indent=4)
        
        QMessageBox.information(self, "Success", "Settings saved successfully!")

    def load_settings(self):
        config_file = "Bot.settings"
        if not os.path.exists(config_file):
            return
        
        with open(config_file, 'r') as f:
            try:
                settings = json.load(f)
                self.tab_widget.clear()
                
                for bot_settings in settings:
                    if bot_settings:
                        tab = BotTab(self.tab_widget, bot_settings.get("name", "New Bot"))
                        tab.name_input.setText(bot_settings.get("name", ""))
                        tab.telegram_input.setText(bot_settings.get("telegram_token", ""))
                        tab.gemini_input.setText(bot_settings.get("gemini_token", ""))
                        
                        if "messages" in bot_settings:
                            tab.bot_messages = bot_settings["messages"]
                        
                        self.tab_widget.addTab(tab, tab.name)
                        tab.save_initial_state()
                        tab.has_unsaved_changes = False
                        tab.save_button.setEnabled(False)
                
                if self.tab_widget.count() == 0:
                    self.add_bot_tab()
            except:
                self.add_bot_tab()

    def closeEvent(self, event):
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab.is_active:
                tab.stop_bot()
        event.accept()

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Tucnify")
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        logo_label = QLabel()
        logo = QPixmap("resources/app.png")
        logo_scaled = logo.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(logo_scaled)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title = QLabel("Tucnify")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #FFFFFF;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        version = QLabel("Version 1.0")
        version.setStyleSheet("color: #a0a0a0;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        description = QLabel(
            "Tucnify is an AI-powered chat bot that combines "
            "Telegram Bot API and Google's Gemini AI technology.\n"
            "Created by ProstoSoftware"
        )
        description.setStyleSheet("color: #FFFFFF;")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        
        links = QLabel(
            '<a style="color: #7783FF;" href="https://prostokust.com/">Website</a>'
            '<span style="color: #a0a0a0;"> | </span>'
            '<a style="color: #7783FF;" href="https://t.me/ProstoSoftware/">Telegram</a>'
            '<span style="color: #a0a0a0;"> | </span>'
            '<a style="color: #7783FF;" href="https://github.com/ProstoKust/Tucnify/">GitHub</a>'
        )
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        close_button = QPushButton("Close")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #7783FF;
                border: none;
                border-radius: 4px;
                color: white;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #5865F2;
            }
        """)
        close_button.clicked.connect(self.accept)
        
        layout.addWidget(logo_label)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(description)
        layout.addWidget(links)
        layout.addWidget(close_button)
        layout.addStretch()
        
        self.setStyleSheet("""
            QDialog {
                background-color: #18191D;
            }
            QLabel {
                color: #FFFFFF;
            }
        """)

def main():
    app = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
