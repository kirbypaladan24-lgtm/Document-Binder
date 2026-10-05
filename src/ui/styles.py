"""Gorgeous dark theme (QSS) for the PDF Merger."""

APP_STYLE = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; }
QMainWindow, QWidget#central { background: #0B1220; color: #E2E8F0; }
QWidget#card {
    background: #141E33;
    border: 1px solid #263354;
    border-radius: 16px;
}
QLabel#appTitle { font-size: 22px; font-weight: 800; color: #FFFFFF; }
QLabel#appSub { font-size: 12px; color: #94A3B8; }
QLabel#hint { font-size: 11px; color: #7C8DB0; font-style: italic; }
QLabel#sectionTitle { font-size: 13px; font-weight: 700; color: #CBD5E1;
    letter-spacing: 1px; }
QLabel#badge {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #7C3AED, stop:1 #06B6D4);
    color: white; font-weight: 800; font-size: 12px;
    border-radius: 9px; padding: 5px 10px;
}
QLabel#pill {
    background: #1E293B; border: 1px solid #334155;
    border-radius: 10px; padding: 4px 10px;
    color: #CBD5E1; font-size: 11px; font-weight: 600;
}
QPushButton {
    background: #1E293B; color: #E2E8F0;
    border: 1px solid #334155; border-radius: 10px;
    padding: 9px 14px; font-size: 12px; font-weight: 600;
}
QPushButton:hover { background: #273449; border-color: #475569; }
QPushButton:pressed { background: #0F172A; }
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7C3AED, stop:1 #06B6D4);
    color: white; border: none; font-size: 14px; font-weight: 800;
    padding: 13px; border-radius: 12px;
}
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 #8B5CF6, stop:1 #22D3EE); }
QPushButton#primary:disabled { background: #334155; color: #94A3B8; }
QPushButton#danger { color: #FCA5A5; }
QPushButton#tool {
    background: #0F172A; border: 1px solid #334155;
    border-radius: 8px; padding: 4px 9px; font-size: 13px; font-weight: 700;
}
QPushButton#tool:hover { background: #7C3AED; color: white; border: none; }
QListWidget {
    background: #0F172A; border: 1px solid #263354;
    border-radius: 12px; padding: 6px; outline: none;
}
QListWidget::item { border: none; padding: 3px; background: transparent; }
QListWidget::item:selected { background: transparent; }
QWidget#rowCard {
    background: #1B2742; border: 1px solid #2E3D63;
    border-radius: 12px;
}
QWidget#rowCardSelected { background: #232F52; border: 1px solid #7C3AED;
    border-radius: 12px; }
QLabel#fileName { font-size: 12px; font-weight: 700; color: #F1F5F9; }
QLabel#grip { color: #5B6B8C; font-size: 15px; font-weight: 800;
    letter-spacing: 0px; }
QLabel#fileMeta { font-size: 11px; color: #94A3B8; }
QLabel#pdfNum {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #7C3AED, stop:1 #06B6D4);
    color: white; font-weight: 800; font-size: 13px;
    border-radius: 8px; padding: 6px 4px;
}
QTabWidget::pane { border: 1px solid #263354; border-radius: 12px;
    background: #0F172A; padding: 8px; }
QTabBar::tab {
    background: #1E293B; color: #94A3B8; padding: 9px 18px;
    border-top-left-radius: 10px; border-top-right-radius: 10px;
    font-weight: 700; font-size: 12px; margin-right: 4px;
}
QTabBar::tab:selected { background: #7C3AED; color: white; }
QLineEdit {
    background: #0F172A; border: 1px solid #334155; border-radius: 10px;
    padding: 9px 12px; color: #E2E8F0; font-size: 12px;
}
QProgressBar {
    background: #0F172A; border: 1px solid #263354;
    border-radius: 8px; text-align: center; color: #CBD5E1; height: 18px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7C3AED, stop:1 #06B6D4);
    border-radius: 7px;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #0F172A; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #334155; border-radius: 5px;
    min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #7C3AED; }
QLabel#thumbFrame { background: #FFFFFF; border-radius: 8px;
    border: 1px solid #334155; }
QLabel#mergeArrow { color: #7C3AED; font-size: 18px; font-weight: 800; }
QStatusBar { background: #0B1220; color: #94A3B8; font-size: 11px; }
QMessageBox { background: #141E33; }
"""
