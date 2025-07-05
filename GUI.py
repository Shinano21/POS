import tkinter as tk
from tkinter import filedialog, messagebox
import re

class GUIBuilder:
    def __init__(self, root):
        self.root = root
        self.root.title("GUI Builder")
        self.widgets = []  # Store widget data: {id, type, text, x, y, width, height}
        self.selected_widget = None
        self.drag_data = {"x": 0, "y": 0, "item": None}

        # Main frame
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)

        # Toolbar for adding widgets
        self.toolbar = tk.Frame(self.main_frame)
        self.toolbar.pack(side="top", fill="x")
        tk.Button(self.toolbar, text="Add Button", command=self.add_button).pack(side="left", padx=5)
        tk.Button(self.toolbar, text="Add Label", command=self.add_label).pack(side="left", padx=5)
        tk.Button(self.toolbar, text="Load .py", command=self.load_py_file).pack(side="left", padx=5)
        tk.Button(self.toolbar, text="Save .py", command=self.save_py_file).pack(side="left", padx=5)

        # Canvas for designing GUI
        self.canvas = tk.Canvas(self.main_frame, width=600, height=400, bg="white", bd=2, relief="sunken")
        self.canvas.pack(side="left", padx=10, pady=10)
        self.canvas.bind("<Button-1>", self.select_widget)
        self.canvas.bind("<B1-Motion>", self.drag_widget)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)

        # Property editor
        self.prop_frame = tk.Frame(self.main_frame)
        self.prop_frame.pack(side="right", fill="y", padx=10)
        tk.Label(self.prop_frame, text="Properties").pack()
        tk.Label(self.prop_frame, text="Text:").pack()
        self.text_entry = tk.Entry(self.prop_frame)
        self.text_entry.pack()
        tk.Label(self.prop_frame, text="Width:").pack()
        self.width_entry = tk.Entry(self.prop_frame)
        self.width_entry.pack()
        tk.Label(self.prop_frame, text="Height:").pack()
        self.height_entry = tk.Entry(self.prop_frame)
        self.height_entry.pack()
        tk.Button(self.prop_frame, text="Apply", command=self.apply_properties).pack(pady=5)
        self.text_entry.bind("<Return>", lambda e: self.apply_properties())
        self.width_entry.bind("<Return>", lambda e: self.apply_properties())
        self.height_entry.bind("<Return>", lambda e: self.apply_properties())

    def add_button(self):
        widget_id = self.canvas.create_rectangle(50, 50, 150, 100, fill="lightblue", tags="widget")
        self.widgets.append({
            "id": widget_id,
            "type": "Button",
            "text": "Button",
            "x": 50,
            "y": 50,
            "width": 100,
            "height": 50
        })
        self.canvas.create_text(100, 75, text="Button", tags=f"text_{widget_id}")
        self.update_properties(widget_id)

    def add_label(self):
        widget_id = self.canvas.create_rectangle(50, 50, 150, 100, fill="lightgreen", tags="widget")
        self.widgets.append({
            "id": widget_id,
            "type": "Label",
            "text": "Label",
            "x": 50,
            "y": 50,
            "width": 100,
            "height": 50
        })
        self.canvas.create_text(100, 75, text="Label", tags=f"text_{widget_id}")
        self.update_properties(widget_id)

    def select_widget(self, event):
        item = self.canvas.find_closest(event.x, event.y)[0]
        for widget in self.widgets:
            if widget["id"] == item:
                self.selected_widget = widget
                self.drag_data["item"] = item
                self.drag_data["x"] = event.x
                self.drag_data["y"] = event.y
                self.update_properties(item)
                break

    def drag_widget(self, event):
        if self.drag_data["item"]:
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]
            self.canvas.move(self.drag_data["item"], dx, dy)
            self.canvas.move(f"text_{self.drag_data['item']}", dx, dy)
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y
            for widget in self.widgets:
                if widget["id"] == self.drag_data["item"]:
                    widget["x"] += dx
                    widget["y"] += dy
                    break

    def stop_drag(self, event):
        self.drag_data["item"] = None

    def update_properties(self, widget_id):
        for widget in self.widgets:
            if widget["id"] == widget_id:
                self.text_entry.delete(0, tk.END)
                self.text_entry.insert(0, widget["text"])
                self.width_entry.delete(0, tk.END)
                self.width_entry.insert(0, widget["width"])
                self.height_entry.delete(0, tk.END)
                self.height_entry.insert(0, widget["height"])
                self.selected_widget = widget
                break

    def apply_properties(self):
        if not self.selected_widget:
            return
        try:
            text = self.text_entry.get()
            width = int(self.width_entry.get())
            height = int(self.height_entry.get())
            if width <= 0 or height <= 0:
                messagebox.showerror("Error", "Width and Height must be positive.")
                return
            self.selected_widget["text"] = text
            self.selected_widget["width"] = width
            self.selected_widget["height"] = height
            x, y = self.selected_widget["x"], self.selected_widget["y"]
            self.canvas.coords(self.selected_widget["id"], x, y, x + width, y + height)
            self.canvas.itemconfig(f"text_{self.selected_widget['id']}", text=text)
            self.canvas.coords(f"text_{self.selected_widget['id']}", x + width / 2, y + height / 2)
        except ValueError:
            messagebox.showerror("Error", "Width and Height must be integers.")

    def save_py_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python files", "*.py")])
        if not file_path:
            return
        code = [
            "import tkinter as tk\n",
            "root = tk.Tk()\n",
            "root.title('Generated GUI')\n"
        ]
        for widget in self.widgets:
            if widget["type"] == "Button":
                code.append(f"button_{widget['id']} = tk.Button(root, text='{widget['text']}')\n")
                code.append(f"button_{widget['id']}.place(x={widget['x']}, y={widget['y']}, width={widget['width']}, height={widget['height']})\n")
            elif widget["type"] == "Label":
                code.append(f"label_{widget['id']} = tk.Label(root, text='{widget['text']}')\n")
                code.append(f"label_{widget['id']}.place(x={widget['x']}, y={widget['y']}, width={widget['width']}, height={widget['height']})\n")
        code.append("root.mainloop()\n")
        with open(file_path, "w") as f:
            f.writelines(code)
        messagebox.showinfo("Success", f"Saved to {file_path}")

    def load_py_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Python files", "*.py")])
        if not file_path:
            return
        self.widgets.clear()
        self.canvas.delete("all")
        try:
            with open(file_path, "r") as f:
                code = f.read()
            # Simple parsing for tk.Button and tk.Label with .place()
            button_pattern = r"(\w+)\s*=\s*tk\.Button\(.*text\s*=\s*['\"]([^'\"]+)['\"].*\)\s*\n\s*\1\.place\(x\s*=\s*(\d+),\s*y\s*=\s*(\d+),\s*width\s*=\s*(\d+),\s*height\s*=\s*(\d+)\)"
            label_pattern = r"(\w+)\s*=\s*tk\.Label\(.*text\s*=\s*['\"]([^'\"]+)['\"].*\)\s*\n\s*\1\.place\(x\s*=\s*(\d+),\s*y\s*=\s*(\d+),\s*width\s*=\s*(\d+),\s*height\s*=\s*(\d+)\)"
            for match in re.finditer(button_pattern, code):
                name, text, x, y, width, height = match.groups()
                widget_id = self.canvas.create_rectangle(int(x), int(y), int(x) + int(width), int(y) + int(height), fill="lightblue", tags="widget")
                self.widgets.append({
                    "id": widget_id,
                    "type": "Button",
                    "text": text,
                    "x": int(x),
                    "y": int(y),
                    "width": int(width),
                    "height": int(height)
                })
                self.canvas.create_text(int(x) + int(width) / 2, int(y) + int(height) / 2, text=text, tags=f"text_{widget_id}")
            for match in re.finditer(label_pattern, code):
                name, text, x, y, width, height = match.groups()
                widget_id = self.canvas.create_rectangle(int(x), int(y), int(x) + int(width), int(y) + int(height), fill="lightgreen", tags="widget")
                self.widgets.append({
                    "id": widget_id,
                    "type": "Label",
                    "text": text,
                    "x": int(x),
                    "y": int(y),
                    "width": int(width),
                    "height": int(height)
                })
                self.canvas.create_text(int(x) + int(width) / 2, int(y) + int(height) / 2, text=text, tags=f"text_{widget_id}")
            messagebox.showinfo("Success", f"Loaded {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load {file_path}: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = GUIBuilder(root)
    root.mainloop()