import sys
from PySide6.QtWidgets import QApplication
from ui.windows.my_characters_page import MyCharactersPage
from core.character_manager import CharacterManager

def test():
    app = QApplication(sys.argv)
    cm = CharacterManager()
    page = MyCharactersPage(cm)
    
    # Just run it so we can verify the code doesn't crash
    print("Page instantiated successfully!")
    print(f"Characters loaded: {len(page._characters)}")
    
test()
