"""Optional local preview and smoke check; closes its own window afterwards."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from app import App, enable_dpi_awareness

enable_dpi_awareness()
root = tk.Tk()
app = App(root)
root.geometry('1180x790+30+30')
app.load_example()
root.update()
assert app.result and not app.result.errors
assert str(app.copy_button['state']) == 'normal'
fixture = Path(__file__).parent / 'fixtures' / 'scripts' / 'qwen35_08b_pipeline.sh'
app.replace_input(fixture.read_text(encoding='utf-8'), fixture)
root.update()
assert app.source_path == fixture
assert app.result and not app.result.errors
assert 'jevforge.train' in app.result.script
app.load_example()
assert app.source_path is None
app.copy()
assert root.clipboard_get() == app.result.script
app.input.insert('end', '\n# a change')
root.update()
assert str(app.copy_button['state']) == 'disabled'
app.run_convert()
app.load_example()
first_step = app.result.script[:app.result.script.index('# Bash line')].count('\n') + 1
app.output.yview(f'{first_step}.0')
root.update()
assert not app.dirty
assert str(app.copy_button['state']) == 'normal'
if '--capture' in sys.argv:
    from PIL import ImageGrab
    root.after(500, lambda: None)
    root.update()
    ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(),
                         root.winfo_rootx() + root.winfo_width(),
                         root.winfo_rooty() + root.winfo_height())).save(Path(__file__).resolve().parents[1] / 'docs' / 'screenshot.png')
root.destroy()
print('GUI smoke check passed.')
